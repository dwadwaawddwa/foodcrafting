"""API FastAPI — Calculateur de craft food Albion Online.

Pages statiques servies depuis /static, API sous /api.
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import aodp, calc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")
MANUAL_PATH = os.path.join(ROOT, "data", "manual_prices.json")

app = FastAPI(title="Albion Food Crafting")


# --------------------------------------------------------------------------- #
# Prix manuels (persistes sur disque)
# --------------------------------------------------------------------------- #
def load_manual() -> dict:
    if os.path.exists(MANUAL_PATH):
        with open(MANUAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manual(d: dict) -> None:
    with open(MANUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- #
# Modeles de requete
# --------------------------------------------------------------------------- #
class ParamsIn(BaseModel):
    buy_mode: str = "instant"
    sell_mode: str = "instant"
    return_rate: float = 0.152
    sell_tax: float = 0.04
    setup_fee: float = 0.015
    station_fee: float = 0.0
    craft_intermediates: bool = True
    avg_discount: float = 0.05
    spec_level: int = 0
    extra_fce: float = 0.0
    focus_price: float = 0.0
    server: str = "west"

    def to_params(self) -> calc.Params:
        return calc.Params(
            buy_mode=self.buy_mode, sell_mode=self.sell_mode,
            return_rate=self.return_rate, sell_tax=self.sell_tax,
            setup_fee=self.setup_fee, station_fee=self.station_fee,
            craft_intermediates=self.craft_intermediates,
            avg_discount=self.avg_discount, spec_level=self.spec_level,
            extra_fce=self.extra_fce, focus_price=self.focus_price,
        )


def build_pricebook(ids, cities, pin: "ParamsIn") -> calc.PriceBook:
    """Recupere prix courants (+ historique 14j si mode avg14) et fusionne le manuel."""
    ids = list(ids)
    prices = aodp.fetch_prices(ids, cities, server=pin.server)
    history = {}
    if pin.buy_mode == "avg14":
        history = aodp.fetch_history_avg(ids, cities, server=pin.server, days=14)
    return calc.PriceBook(prices=prices, manual=load_manual(),
                          history=history, avg_discount=pin.avg_discount)


class CalcIn(BaseModel):
    product_id: str
    enchant: int = 0
    cities: Optional[List[str]] = None
    params: ParamsIn = ParamsIn()


class RankIn(BaseModel):
    tiers: Optional[List[int]] = None
    enchants: Optional[List[int]] = None
    families: Optional[List[str]] = None
    category: str = "meal"       # meal | sauce | refined | all
    cities: Optional[List[str]] = None
    sort: str = "profit"          # profit | roi | profit_per_focus | profit_per_nutrition
    params: ParamsIn = ParamsIn()


class ManualIn(BaseModel):
    item_id: str
    buy: Optional[float] = None
    sell: Optional[float] = None


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #
@app.get("/api/meta")
def meta():
    products = {}
    for r in calc.RECIPES:
        pid = r["product_id"]
        entry = products.setdefault(pid, {
            "product_id": pid,
            "name": calc.item_name(pid),
            "name_en": calc.item_name(pid, "en"),
            "tier": r["tier"],
            "category": r["category"],
            "family": r["family"],
            "img": calc.render_url(pid, 64),
            "enchants": set(),
        })
        entry["enchants"].add(r["enchant"])
    plist = []
    for e in products.values():
        e["enchants"] = sorted(e["enchants"])
        plist.append(e)
    plist.sort(key=lambda x: (x["category"], x["tier"], x["family"]))
    return {
        "cities": calc.CITIES,
        "families": sorted(set(r["family"] for r in calc.RECIPES)),
        "tiers": sorted(set(r["tier"] for r in calc.RECIPES)),
        "products": plist,
    }


# --------------------------------------------------------------------------- #
# Calcul d'une recette
# --------------------------------------------------------------------------- #
@app.post("/api/calc")
def api_calc(body: CalcIn):
    cities = body.cities or calc.CITIES
    p = body.params.to_params()
    # ids a tarifer (produit + ingredients recursifs de toutes les candidates)
    ids = set()
    cands = calc.candidate_recipes(body.product_id, body.enchant)
    for r in cands:
        calc.collect_ids(r, ids)
    pb = build_pricebook(ids, cities, body.params)
    rec = calc.best_recipe(body.product_id, body.enchant, cities, pb, p)
    if rec is None:
        if not cands:
            return JSONResponse({"error": "recette introuvable"}, status_code=404)
        rec = cands[0]
    return calc.evaluate(rec, cities, pb, p)


# --------------------------------------------------------------------------- #
# Classement de rentabilite
# --------------------------------------------------------------------------- #
@app.post("/api/rankings")
def api_rankings(body: RankIn):
    cities = body.cities or calc.CITIES
    p = body.params.to_params()

    # selection des recettes
    seen = set()
    recs = []
    for r in calc.RECIPES:
        if body.category != "all" and r["category"] != body.category:
            continue
        if body.tiers and r["tier"] not in body.tiers:
            continue
        if body.enchants is not None and r["enchant"] not in body.enchants:
            continue
        if body.families and r["family"] not in body.families:
            continue
        key = (r["product_id"], r["enchant"])
        if key in seen:
            continue
        seen.add(key)
        recs.append(r)

    ids = set()
    for r in recs:
        for rr in calc.candidate_recipes(r["product_id"], r["enchant"]):
            calc.collect_ids(rr, ids)
    pb = build_pricebook(ids, cities, body.params)

    rows = []
    for r in recs:
        rec = calc.best_recipe(r["product_id"], r["enchant"], cities, pb, p)
        if rec is None:
            continue
        route = calc.best_route(rec, cities, pb, p)
        if route is None:
            continue
        rows.append({
            "product_id": rec["product_id"],
            "result_id": rec["result_id"],
            "name": calc.item_name(rec["result_id"]),
            "tier": rec["tier"],
            "enchant": rec["enchant"],
            "family": rec["family"],
            "category": rec["category"],
            "nutrition": rec["nutrition"],
            "item_power": rec["item_power"],
            "focus": rec["focus"],
            "img": calc.render_url(rec["result_id"], 64),
            **route,
        })

    key = body.sort
    rows.sort(key=lambda x: (x.get(key) is None, -(x.get(key) or 0)))
    return {"rows": rows, "count": len(rows)}


# --------------------------------------------------------------------------- #
# Prix manuels
# --------------------------------------------------------------------------- #
@app.get("/api/manual")
def get_manual():
    m = load_manual()
    out = []
    for iid, v in m.items():
        out.append({
            "item_id": iid,
            "name": calc.item_name(iid),
            "img": calc.render_url(iid),
            "buy": v.get("buy"),
            "sell": v.get("sell"),
        })
    out.sort(key=lambda x: x["item_id"])
    return {"manual": out}


@app.post("/api/manual")
def set_manual(body: ManualIn):
    m = load_manual()
    if not body.buy and not body.sell:
        m.pop(body.item_id, None)
    else:
        m[body.item_id] = {"buy": body.buy, "sell": body.sell}
    save_manual(m)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Recherche d'items (pour la page prix manuels / autocomplete)
# --------------------------------------------------------------------------- #
@app.get("/api/items")
def search_items(q: str = "", limit: int = 40):
    q = q.strip().lower()
    out = []
    for iid, m in calc.ITEMS.items():
        if q and q not in iid.lower() and q not in m["name_fr"].lower() \
                and q not in m["name_en"].lower():
            continue
        out.append({
            "item_id": iid, "name": m["name_fr"], "name_en": m["name_en"],
            "tier": m["tier"], "craftable": m["craftable"],
            "img": calc.render_url(iid),
        })
        if len(out) >= limit:
            break
    return {"items": out}


# --------------------------------------------------------------------------- #
# Proxy prix brut (page prix)
# --------------------------------------------------------------------------- #
@app.get("/api/prices")
def api_prices(ids: str, cities: str = "", server: str = "west"):
    id_list = [i for i in ids.split(",") if i]
    city_list = [c for c in cities.split(",") if c] or calc.CITIES
    prices = aodp.fetch_prices(id_list, city_list, server=server)
    out = []
    for (iid, city), rec in prices.items():
        out.append({"item_id": iid, "city": city, **rec})
    return {"prices": out}


# --------------------------------------------------------------------------- #
# Statique
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
