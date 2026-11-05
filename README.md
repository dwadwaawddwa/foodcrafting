# 🍲 Albion Food Craft — Calculateur de craft & routes de profit

Outil local pour le craft de **nourriture (food)** dans Albion Online :
prix live via l'API **Albion Free Market / Albion Online Data Project (AODP)**,
prix manuels, calcul de **coût de craft** (return rate, taxes, focus), et
recherche de la **meilleure route achat → vente** entre les villes.

## Fonctions

- **Calculateur** : choisis une recette + enchantement → coût des ingrédients,
  revenu net, profit/craft, ROI, et la route « acheter à X, vendre à Y ».
  Les intermédiaires (fish sauce, pain, beurre, farine, alcool, morceaux de
  poisson) sont soit achetés soit craftés récursivement (le moins cher gagne).
- **Classement rentabilité** : toutes les foods triées par profit / ROI /
  profit-par-focus / profit-par-nutrition, avec **filtres** (catégorie, tier,
  enchantement, famille) et **images** des plats.
- **Prix manuels & Fish Sauce** : entre tes propres prix (prioritaires sur
  l'API) et calcule le prix de revient des sauces de poisson (poisson + algue).

Ordres **buy order** et **sell order** gérés pour l'achat comme pour la vente,
sur les 6 marchés royaux + Caerleon + Brecilien, serveurs west / europe / east.

## Données

`data/recipes.json` et `data/items.json` sont générés depuis les dumps officiels
du jeu (ao-bin-dumps). Pour les régénérer après un patch :

```bash
python scripts/build_data.py
```

## Installation & lancement

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Puis ouvre http://localhost:8010

## Modèle économique

- **Achat ingrédients** : 3 modes —
  - *Instantané* = `sell_price_min` (ordre de vente le plus bas),
  - *Ordre d'achat* = `buy_price_max`,
  - *Moyenne 14 jours − x %* = prix moyen 14 j de la ville (endpoint history AODP,
    pondéré par le volume) moins une décote (défaut 5 %). Repli sur l'instantané
    si pas d'historique.
- **Vente produit** : instantané = `buy_price_max` (ordre d'achat le plus haut)
  ou ordre de vente = `sell_price_min` (− frais de mise en vente 1,5 %).
- **Taxe de vente** : 4 % (premium) / 8 % (non-premium).
- **Return rate (RRR) — cuisine** (formule `RRR = b/(1+b)`, la spé ne change PAS le RRR) :

  | Cas | Bonus | RRR |
  |---|---|---|
  | Ville royale, sans focus | +18 % | **15,2 %** |
  | Ville royale + focus | +77 % | **43,5 %** |
  | Caerleon (seule ville bonus food), sans focus | +33 % | **24,8 %** |
  | Caerleon + focus | +92 % | **47,9 %** |
  | Caerleon + focus + gold day | +112 % | **52,8 %** |

- **Achat éclaté** : la liste d'achat indique, pour **chaque ingrédient**, la ville
  la moins chère, et compare le coût éclaté au coût mono-ville.
- **Frais de station** : silver par craft, paramétrable.

> Les prix viennent de données crowd-sourcées (AODP) : elles peuvent être
> anciennes ou absentes sur certains items/villes. Utilise les prix manuels
> pour combler les trous.
