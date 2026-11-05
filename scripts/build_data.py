"""
build_data.py — Genere data/recipes.json et data/items.json a partir des dumps
officiels du jeu (ao-bin-dumps). A relancer quand le jeu ajoute du contenu.

Sortie:
  data/recipes.json : liste de recettes food craftables (repas, sauces, raffines)
  data/items.json   : metadonnees {id: {name_en, name_fr, tier, enchant, craftable,
                       category, family}} pour tous les produits + ingredients.
  data/cities.json  : villes / marches valides pour l'API AODP.

Usage: python scripts/build_data.py
"""
import json
import os
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/ao-data/ao-bin-dumps/master"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
os.makedirs(DATA, exist_ok=True)

# Villes marchandes (marches royaux + Caerleon + Brecilien).
CITIES = [
    "Thetford", "Fort Sterling", "Lymhurst", "Bridgewatch",
    "Martlock", "Caerleon", "Brecilien",
]


def fetch_json(path, cache):
    local = os.path.join(HERE, cache)
    if os.path.exists(local):
        print(f"  (cache) {cache}")
        with open(local, "r", encoding="utf-8") as f:
            return json.load(f)
    url = f"{RAW}/{path}"
    print(f"  download {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "foodcrafting-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8")
    with open(local, "w", encoding="utf-8") as f:
        f.write(raw)
    return json.loads(raw)


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def all_items(items_root):
    for _, v in items_root.items():
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and "@uniquename" in it:
                    yield it
        elif isinstance(v, dict) and "@uniquename" in v:
            yield v


def tier_of(uid):
    if uid and uid[0] == "T" and uid[1:2].isdigit():
        return int(uid[1])
    return 0


def resources_from_req(req):
    """Retourne (ingredients, focus, amount, silver) pour une craftingrequirements."""
    res = []
    for cr in as_list(req.get("craftresource")):
        res.append({"id": cr["@uniquename"], "count": int(cr["@count"])})
    focus = int(req.get("@craftingfocus", 0) or 0)
    amount = int(req.get("@amountcrafted", 1) or 1)
    silver = int(req.get("@silver", 0) or 0)
    return res, focus, amount, silver


def family_of(uid):
    parts = uid.split("_")
    if "MEAL" in parts:
        i = parts.index("MEAL")
        return "_".join(parts[i + 1:]) or "MEAL"
    if "FISHSAUCE" in uid:
        return "FISHSAUCE"
    if "FISHCHOPS" in uid:
        return "FISHCHOPS"
    for key in ("FLOUR", "BREAD", "BUTTER", "ALCOHOL"):
        if key in uid:
            return key
    return "OTHER"


def category_of(uid):
    if "MEAL" in uid.split("_"):
        return "meal"
    if "FISHSAUCE" in uid:
        return "sauce"
    return "refined"


def main():
    print("Chargement des dumps...")
    items_root = fetch_json("items.json", "_items.json")["items"]
    fmt = fetch_json("formatted/items.json", "_items_fmt.json")

    # Table des noms localises EN/FR
    names = {}
    for x in fmt:
        uid = x.get("UniqueName")
        loc = x.get("LocalizedNames") or {}
        if uid:
            names[uid] = {
                "en": (loc or {}).get("EN-US", uid),
                "fr": (loc or {}).get("FR-FR", (loc or {}).get("EN-US", uid)),
            }

    recipes = []
    craftable_ids = set()
    referenced_ids = set()

    def add_recipe(product_id, result_id, enchant, tier, category, family,
                   nutrition, item_power, req):
        res, focus, amount, silver = resources_from_req(req)
        if not res:
            return
        for r in res:
            referenced_ids.add(r["id"])
        referenced_ids.add(result_id)
        craftable_ids.add(result_id)
        recipes.append({
            "product_id": product_id,      # id de base (sans @ench)
            "result_id": result_id,        # id price/render (avec @1..@3)
            "enchant": enchant,
            "tier": tier,
            "category": category,          # meal | sauce | refined
            "family": family,
            "nutrition": nutrition,
            "item_power": item_power,
            "focus": focus,
            "amount_crafted": amount,
            "silver": silver,
            "ingredients": res,
        })

    for it in all_items(items_root):
        uid = it["@uniquename"]
        cc = it.get("@craftingcategory")
        is_food = cc == "food"
        is_sauce = "FISHSAUCE" in uid
        is_chops = "FISHCHOPS" in uid
        if not (is_food or is_sauce or is_chops):
            continue
        req = it.get("craftingrequirements")
        if not req:
            continue
        tier = tier_of(uid)
        category = category_of(uid)
        family = family_of(uid)

        # FISHCHOPS = multi-recette (une par palier de poisson) -> chaque variante
        if isinstance(req, list):
            for idx, sub in enumerate(req):
                add_recipe(uid, uid, 0, tier, category, family,
                           int(it.get("@nutrition", 0) or 0),
                           int(it.get("@dummyitempower", 0) or 0), sub)
            continue

        nutrition = int(it.get("@nutrition", 0) or 0)
        item_power = int(it.get("@dummyitempower", 0) or 0)
        # Recette de base (enchant 0)
        add_recipe(uid, uid, 0, tier, category, family, nutrition, item_power, req)

        # Variantes enchantees (repas surtout)
        ench_root = it.get("enchantments")
        if ench_root:
            for e in as_list(ench_root.get("enchantment")):
                lvl = int(e.get("@enchantmentlevel", 0) or 0)
                if lvl <= 0:
                    continue
                ereq = e.get("craftingrequirements")
                if not ereq:
                    continue
                add_recipe(
                    uid, f"{uid}@{lvl}", lvl, tier, category, family, nutrition,
                    int(e.get("@dummyitempower", item_power) or item_power), ereq,
                )

    # Metadonnees items (produits + ingredients feuilles)
    all_ids = set(referenced_ids)
    # inclure aussi la base sans @ pour l'affichage
    meta = {}
    for uid in sorted(all_ids):
        base = uid.split("@")[0]
        nm = names.get(base, {"en": base, "fr": base})
        ench = int(uid.split("@")[1]) if "@" in uid else 0
        meta[uid] = {
            "name_en": nm["en"],
            "name_fr": nm["fr"],
            "tier": tier_of(base),
            "enchant": ench,
            "craftable": uid in craftable_ids,
            "category": category_of(base) if uid in craftable_ids else "resource",
            "family": family_of(base) if "MEAL" in base or "FISH" in base else "",
        }

    with open(os.path.join(DATA, "recipes.json"), "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "items.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "cities.json"), "w", encoding="utf-8") as f:
        json.dump(CITIES, f, ensure_ascii=False, indent=1)

    n_meal = sum(1 for r in recipes if r["category"] == "meal")
    n_sauce = sum(1 for r in recipes if r["category"] == "sauce")
    n_ref = sum(1 for r in recipes if r["category"] == "refined")
    print(f"OK -> {len(recipes)} recettes ({n_meal} repas, {n_sauce} sauces, "
          f"{n_ref} raffines), {len(meta)} items, {len(CITIES)} villes")


if __name__ == "__main__":
    sys.exit(main())
