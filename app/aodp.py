"""Client de prix Albion Online Data Project (AODP) + cache memoire.

API publique: https://west|east|europe.albion-online-data.com
Endpoint prix courant:
  /api/v2/stats/prices/{ids}.json?locations={villes}&qualities={q}

Champs renvoyes par item/ville/qualite:
  sell_price_min  -> meilleur ordre de VENTE (prix pour acheter en instantane)
  buy_price_max   -> meilleur ordre d'ACHAT (prix pour vendre en instantane)
  *_date          -> fraicheur de la donnee
"""
from __future__ import annotations

import datetime
import time
from typing import Dict, Iterable, List, Tuple

import httpx

SERVERS = {
    "west": "https://west.albion-online-data.com",
    "east": "https://east.albion-online-data.com",
    "europe": "https://europe.albion-online-data.com",
}

_CACHE: Dict[str, Tuple[float, dict]] = {}
_TTL = 300  # secondes


def _chunk(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_prices(
    item_ids: List[str],
    cities: List[str],
    server: str = "west",
    qualities: str = "1",
) -> Dict[Tuple[str, str], dict]:
    """Retourne {(item_id, city): record}. Utilise un cache TTL en memoire.

    record = {sell_price_min, buy_price_max, sell_price_min_date, buy_price_max_date, quality}
    """
    base = SERVERS.get(server, SERVERS["west"])
    item_ids = sorted(set(i for i in item_ids if i))
    out: Dict[Tuple[str, str], dict] = {}
    to_fetch: List[str] = []
    now = time.time()
    loc = ",".join(cities)

    for iid in item_ids:
        ck = f"{server}|{loc}|{qualities}|{iid}"
        hit = _CACHE.get(ck)
        if hit and now - hit[0] < _TTL:
            for city, rec in hit[1].items():
                out[(iid, city)] = rec
        else:
            to_fetch.append(iid)

    # Requetes par paquets (limite de longueur d'URL)
    with httpx.Client(timeout=30.0, headers={"User-Agent": "foodcrafting/1.0"}) as client:
        for group in _chunk(to_fetch, 60):
            url = f"{base}/api/v2/stats/prices/{','.join(group)}.json"
            try:
                r = client.get(url, params={"locations": loc, "qualities": qualities})
                r.raise_for_status()
                rows = r.json()
            except Exception:
                rows = []
            # regrouper par item pour peupler le cache
            by_item: Dict[str, Dict[str, dict]] = {i: {} for i in group}
            for row in rows:
                iid = row.get("item_id")
                city = row.get("city")
                if iid is None or city is None:
                    continue
                rec = {
                    "sell_price_min": row.get("sell_price_min") or 0,
                    "sell_price_min_date": row.get("sell_price_min_date"),
                    "buy_price_max": row.get("buy_price_max") or 0,
                    "buy_price_max_date": row.get("buy_price_max_date"),
                    "quality": row.get("quality"),
                }
                by_item.setdefault(iid, {})[city] = rec
                out[(iid, city)] = rec
            for iid, cmap in by_item.items():
                ck = f"{server}|{loc}|{qualities}|{iid}"
                _CACHE[ck] = (now, cmap)
    return out


_HCACHE: Dict[str, Tuple[float, dict]] = {}
_HTTL = 3600  # historique: cache 1h


def fetch_history_avg(
    item_ids: List[str],
    cities: List[str],
    server: str = "west",
    days: int = 14,
    qualities: str = "1",
) -> Dict[Tuple[str, str], float]:
    """Prix moyen sur `days` jours par (item, ville), pondere par le volume.

    Utilise l'endpoint history d'AODP (avg_price + item_count par jour).
    """
    base = SERVERS.get(server, SERVERS["west"])
    item_ids = sorted(set(i for i in item_ids if i))
    loc = ",".join(cities)
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    dfmt = f"{start.month}-{start.day}-{start.year}"
    efmt = f"{end.month}-{end.day}-{end.year}"

    out: Dict[Tuple[str, str], float] = {}
    to_fetch: List[str] = []
    now = time.time()
    for iid in item_ids:
        ck = f"{server}|{loc}|{days}|{iid}"
        hit = _HCACHE.get(ck)
        if hit and now - hit[0] < _HTTL:
            for city, avg in hit[1].items():
                out[(iid, city)] = avg
        else:
            to_fetch.append(iid)

    with httpx.Client(timeout=40.0, headers={"User-Agent": "foodcrafting/1.0"}) as client:
        for group in _chunk(to_fetch, 40):
            url = f"{base}/api/v2/stats/history/{','.join(group)}.json"
            try:
                r = client.get(url, params={
                    "locations": loc, "qualities": qualities,
                    "time-scale": 24, "date": dfmt, "end_date": efmt,
                })
                r.raise_for_status()
                series = r.json()
            except Exception:
                series = []
            by_item: Dict[str, Dict[str, float]] = {i: {} for i in group}
            for s in series:
                iid = s.get("item_id")
                city = s.get("location")
                data = s.get("data") or []
                if not iid or not city or not data:
                    continue
                num = sum((pt.get("avg_price") or 0) * (pt.get("item_count") or 0) for pt in data)
                den = sum(pt.get("item_count") or 0 for pt in data)
                if den <= 0:
                    continue
                avg = num / den
                by_item.setdefault(iid, {})[city] = avg
                out[(iid, city)] = avg
            for iid, cmap in by_item.items():
                ck = f"{server}|{loc}|{days}|{iid}"
                _HCACHE[ck] = (now, cmap)
    return out


def clear_cache() -> None:
    _CACHE.clear()
    _HCACHE.clear()
