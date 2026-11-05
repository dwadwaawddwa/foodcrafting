"""Moteur economique: cout de craft recursif, return rate, taxes marche,
profit et meilleure route achat/vente.

Modele des prix marche:
  ACHETER un ingredient
     - instantane (mode "instant") : on paie le sell_price_min (ordre de vente le + bas)
     - ordre d'achat (mode "order") : on paie ~ buy_price_max
  VENDRE le produit
     - instantane (mode "instant") : on recoit le buy_price_max (ordre d'achat le + haut)
     - ordre de vente (mode "order") : on recoit le sell_price_min, moins frais de mise en vente

Taxes marche (bien definies dans le jeu):
  - Taxe de vente : 4% (premium) ou 8% (non premium)
  - Frais de mise en vente (ordre de vente) : 1.5% du prix affiche
Le return rate (taux de retour de ressources) reduit la conso nette d'ingredients.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


RECIPES: List[dict] = _load("recipes.json")
ITEMS: Dict[str, dict] = _load("items.json")
CITIES: List[str] = _load("cities.json")

# Index: id_de_base -> liste de recettes (une seule sauf fishchops / enchant)
RECIPES_BY_RESULT: Dict[str, List[dict]] = {}
RECIPES_BY_PRODUCT: Dict[str, List[dict]] = {}
for _r in RECIPES:
    RECIPES_BY_RESULT.setdefault(_r["result_id"], []).append(_r)
    RECIPES_BY_PRODUCT.setdefault(_r["product_id"], []).append(_r)


def render_url(item_id: str, size: int = 64) -> str:
    return f"https://render.albiononline.com/v1/item/{item_id}.png?size={size}"


def item_name(item_id: str, lang: str = "fr") -> str:
    m = ITEMS.get(item_id) or ITEMS.get(item_id.split("@")[0])
    if not m:
        return item_id
    return m.get("name_fr" if lang == "fr" else "name_en", item_id)


# --------------------------------------------------------------------------- #
# Parametres de calcul
# --------------------------------------------------------------------------- #
# Taux de retour ressources (RRR) pour la CUISINE. Formule: RRR = b/(1+b).
#   base ville (+18%)                     -> 15.2%   (toute ville royale, pas de bonus food)
#   base + focus (+59%)                   -> 43.5%
#   Caerleon bonus food (+15%)            -> 24.8%   (seule ville qui bonus la food)
#   Caerleon + focus                      -> 47.9%
#   Caerleon + focus + gold day (+20%)    -> 52.8%
# La specialisation n'ajoute PAS de RRR (elle reduit le cout en focus).
RRR_PRESETS = {
    "royal": 0.152, "royal_focus": 0.435,
    "caerleon": 0.248, "caerleon_focus": 0.479, "caerleon_focus_gold": 0.528,
}


@dataclass
class Params:
    buy_mode: str = "instant"      # instant | order | avg14  (achat des ingredients)
    sell_mode: str = "instant"     # instant | order  (vente du produit)
    return_rate: float = 0.152     # 0..0.6
    sell_tax: float = 0.04         # 0.04 premium / 0.08 non premium
    setup_fee: float = 0.015       # frais de mise en vente (ordre de vente)
    station_fee: float = 0.0       # silver par craft (frais d'utilisation station)
    craft_intermediates: bool = True  # crafter fish sauce/bread/butter... ou les acheter
    avg_discount: float = 0.05     # achat = moyenne 14j - x% (mode avg14)
    spec_level: int = 0            # niveau de spe du plat (0-100) -> 250 FCE / niveau
    extra_fce: float = 0.0         # FCE additionnel (mutuel autres plats, maitrise)
    focus_price: float = 0.0       # valeur d'1 point de focus en silver (0 = ignore)


def effective_focus(base_focus: int, p: "Params") -> float:
    """Focus reellement depense selon la spe. FCE halve le cout tous les 10000.

    focus = base * 0.5^(FCE/10000),  FCE = niveau_spe*250 + extra_fce.
    """
    fce = p.spec_level * 250 + p.extra_fce
    return base_focus * (0.5 ** (fce / 10000.0))


@dataclass
class PriceBook:
    """Resolveur de prix: fusionne l'API AODP (courant + historique) et le manuel."""
    prices: Dict[Tuple[str, str], dict] = field(default_factory=dict)
    manual: Dict[str, dict] = field(default_factory=dict)  # {id: {"buy": n, "sell": n}}
    history: Dict[Tuple[str, str], float] = field(default_factory=dict)  # moyenne 14j
    avg_discount: float = 0.05

    def _api(self, item_id, city, key):
        rec = self.prices.get((item_id, city))
        if not rec:
            return 0
        return rec.get(key) or 0

    def buy_cost(self, item_id: str, city: str, mode: str) -> int:
        """Prix pour ACHETER 1 unite. 0 si inconnu."""
        man = self.manual.get(item_id)
        if man and man.get("buy"):
            return int(man["buy"])
        if mode == "avg14":
            avg = self.history.get((item_id, city)) or 0
            if avg > 0:
                return int(round(avg * (1.0 - self.avg_discount)))
            # repli: pas d'historique -> prix instantane
            return self._api(item_id, city, "sell_price_min")
        if mode == "order":
            return self._api(item_id, city, "buy_price_max")
        return self._api(item_id, city, "sell_price_min")

    def sell_revenue(self, item_id: str, city: str, mode: str) -> int:
        """Prix brut pour VENDRE 1 unite. 0 si inconnu."""
        man = self.manual.get(item_id)
        if man and man.get("sell"):
            return int(man["sell"])
        if mode == "order":
            return self._api(item_id, city, "sell_price_min")
        return self._api(item_id, city, "buy_price_max")


# --------------------------------------------------------------------------- #
# Cout d'obtention recursif d'un ingredient
# --------------------------------------------------------------------------- #
def unit_cost(item_id: str, city: str, pb: PriceBook, p: Params,
              path: Optional[set] = None) -> Optional[float]:
    """Cout min pour obtenir 1 unite de item_id dans `city` (achat ou craft)."""
    path = path or set()
    options: List[float] = []

    buy = pb.buy_cost(item_id, city, p.buy_mode)
    if buy > 0:
        options.append(float(buy))

    if p.craft_intermediates and item_id not in path:
        for rec in RECIPES_BY_RESULT.get(item_id, []):
            c = craft_unit_cost(rec, city, pb, p, path | {item_id})
            if c is not None:
                options.append(c)

    return min(options) if options else None


def craft_unit_cost(rec: dict, city: str, pb: PriceBook, p: Params,
                    path: set) -> Optional[float]:
    total = 0.0
    for ing in rec["ingredients"]:
        u = unit_cost(ing["id"], city, pb, p, path)
        if u is None:
            return None
        total += u * ing["count"]
    total *= (1.0 - p.return_rate)
    return total / max(1, rec["amount_crafted"])


# --------------------------------------------------------------------------- #
# Evaluation d'une recette produit sur (ville_achat, ville_vente)
# --------------------------------------------------------------------------- #
def ingredient_breakdown(rec: dict, city: str, pb: PriceBook, p: Params):
    lines = []
    total = 0.0
    missing = False
    for ing in rec["ingredients"]:
        u = unit_cost(ing["id"], city, pb, p)
        line = None if u is None else round(u * ing["count"])
        if u is None:
            missing = True
        else:
            total += u * ing["count"]
        crafted = p.craft_intermediates and bool(RECIPES_BY_RESULT.get(ing["id"]))
        lines.append({
            "id": ing["id"],
            "name": item_name(ing["id"]),
            "count": ing["count"],
            "unit": None if u is None else round(u),
            "line": line,
            "crafted": crafted and (pb.buy_cost(ing["id"], city, p.buy_mode) == 0
                                    or u < pb.buy_cost(ing["id"], city, p.buy_mode)),
            "img": render_url(ing["id"]),
        })
    return lines, total, missing


def shopping_list(rec: dict, cities: List[str], pb: PriceBook, p: Params):
    """Pour CHAQUE ingredient, la ville la moins chere (achat eclate).

    Retourne (rows, total_avant_retour, total_apres_retour, missing).
    Chaque ingredient est source la ou son cout unitaire est minimal.
    """
    rows = []
    total = 0.0
    missing = False
    for ing in rec["ingredients"]:
        best_city, best_u = None, None
        per_city = []
        for c in cities:
            u = unit_cost(ing["id"], c, pb, p)
            if u is None:
                continue
            per_city.append((c, u))
            if best_u is None or u < best_u:
                best_city, best_u = c, u
        if best_u is None:
            missing = True
            rows.append({
                "id": ing["id"], "name": item_name(ing["id"]), "count": ing["count"],
                "city": None, "unit": None, "line": None, "crafted": False,
                "img": render_url(ing["id"]),
            })
            continue
        total += best_u * ing["count"]
        market_buy = pb.buy_cost(ing["id"], best_city, p.buy_mode)
        crafted = (p.craft_intermediates and bool(RECIPES_BY_RESULT.get(ing["id"]))
                   and (market_buy == 0 or best_u < market_buy))
        rows.append({
            "id": ing["id"], "name": item_name(ing["id"]), "count": ing["count"],
            "city": best_city, "unit": round(best_u), "line": round(best_u * ing["count"]),
            "crafted": crafted, "img": render_url(ing["id"]),
            "cities": sorted([{"city": c, "unit": round(u)} for c, u in per_city],
                             key=lambda x: x["unit"]),
        })
    return rows, round(total), round(total * (1.0 - p.return_rate)), missing


def craft_cost_in_city(rec: dict, city: str, pb: PriceBook, p: Params):
    """Cout total d'ingredients (apres return rate) dans une ville. None si manquant."""
    total = 0.0
    for ing in rec["ingredients"]:
        u = unit_cost(ing["id"], city, pb, p)
        if u is None:
            return None
        total += u * ing["count"]
    return total * (1.0 - p.return_rate)


def sell_net(rec: dict, city: str, pb: PriceBook, p: Params):
    """Revenu net de la vente (apres taxes) dans une ville. None si pas de prix."""
    gross_unit = pb.sell_revenue(rec["result_id"], city, p.sell_mode)
    if gross_unit <= 0:
        return None, 0
    gross = gross_unit * rec["amount_crafted"]
    tax = gross * p.sell_tax
    if p.sell_mode == "order":
        tax += gross * p.setup_fee
    return gross - tax, gross_unit


def best_route(rec: dict, cities: List[str], pb: PriceBook, p: Params):
    """Meilleure ville d'achat (cout min) et de vente (revenu net max)."""
    buy_opts = []
    for c in cities:
        cost = craft_cost_in_city(rec, c, pb, p)
        if cost is not None:
            buy_opts.append((c, cost))
    sell_opts = []
    for c in cities:
        net, unit = sell_net(rec, c, pb, p)
        if net is not None:
            sell_opts.append((c, net, unit))

    if not buy_opts or not sell_opts:
        return None

    buy_city, buy_cost = min(buy_opts, key=lambda x: x[1])
    sell_city, sell_net_v, sell_unit = max(sell_opts, key=lambda x: x[1])
    eff_focus = effective_focus(rec["focus"], p)
    focus_cost = eff_focus * p.focus_price
    cost = buy_cost + p.station_fee + focus_cost
    profit = sell_net_v - cost
    roi = (profit / cost * 100.0) if cost > 0 else 0.0
    nut = rec["nutrition"] * rec["amount_crafted"]
    return {
        "buy_city": buy_city,
        "buy_cost": round(buy_cost),
        "station_fee": round(p.station_fee),
        "base_focus": rec["focus"],
        "eff_focus": round(eff_focus),
        "focus_cost": round(focus_cost),
        "total_cost": round(cost),
        "sell_city": sell_city,
        "sell_unit": round(sell_unit),
        "sell_net": round(sell_net_v),
        "amount": rec["amount_crafted"],
        "profit": round(profit),
        "profit_per_item": round(profit / max(1, rec["amount_crafted"])),
        "roi": round(roi, 1),
        "profit_per_focus": round(profit / eff_focus, 2) if eff_focus else None,
        "profit_per_nutrition": round(profit / nut, 3) if nut else None,
        "buy_table": [{"city": c, "cost": round(v)} for c, v in sorted(buy_opts, key=lambda x: x[1])],
        "sell_table": [{"city": c, "net": round(v), "unit": round(u)}
                       for c, v, u in sorted(sell_opts, key=lambda x: -x[1])],
    }


def collect_ids(rec: dict, acc: set) -> None:
    """Tous les ids necessaires au prix (produit + ingredients recursifs)."""
    acc.add(rec["result_id"])
    for ing in rec["ingredients"]:
        if ing["id"] in acc:
            continue
        acc.add(ing["id"])
        for sub in RECIPES_BY_RESULT.get(ing["id"], []):
            collect_ids(sub, acc)


def candidate_recipes(product_id: str, enchant: int) -> List[dict]:
    return [r for r in RECIPES_BY_PRODUCT.get(product_id, []) if r["enchant"] == enchant]


def best_recipe(product_id: str, enchant: int, cities: List[str],
                pb: PriceBook, p: Params) -> Optional[dict]:
    """Parmi les recettes candidates (ex: fishchops multi-recette), la + rentable."""
    best, best_rec = None, None
    for rec in candidate_recipes(product_id, enchant):
        route = best_route(rec, cities, pb, p)
        if route is None:
            continue
        if best is None or route["profit"] > best["profit"]:
            best, best_rec = route, rec
    return best_rec


def evaluate(rec: dict, cities: List[str], pb: PriceBook, p: Params):
    """Detail complet pour la page calculateur."""
    route = best_route(rec, cities, pb, p)
    lines, _, missing = ingredient_breakdown(
        rec, route["buy_city"] if route else cities[0], pb, p)
    shop_rows, shop_total, shop_after, shop_missing = shopping_list(rec, cities, pb, p)
    shopping = {
        "rows": shop_rows,
        "total": shop_total,
        "total_after_return": shop_after,
        "station_fee": round(p.station_fee),
        "cost_with_fee": round(shop_after + p.station_fee),
        "missing": shop_missing,
    }
    if route and not shop_missing:
        shopping["saving_vs_single"] = round(route["buy_cost"] - shop_after)
    return {
        "product_id": rec["product_id"],
        "result_id": rec["result_id"],
        "name": item_name(rec["result_id"]),
        "name_en": item_name(rec["result_id"], "en"),
        "tier": rec["tier"],
        "enchant": rec["enchant"],
        "family": rec["family"],
        "category": rec["category"],
        "nutrition": rec["nutrition"],
        "item_power": rec["item_power"],
        "focus": rec["focus"],
        "img": render_url(rec["result_id"], 128),
        "ingredients": lines,
        "shopping": shopping,
        "route": route,
    }
