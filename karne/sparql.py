"""Wikidata SPARQL istemcisi (önbellekli, IPv4'e zorlanmış)."""
from __future__ import annotations

import hashlib
import json
import socket
import time
from pathlib import Path

import requests
import urllib3.util.connection as _conn

# Bu makinede IPv6 bazı Wikimedia isteklerinde takılıyor; IPv4'e zorla.
_conn.allowed_gai_family = lambda: socket.AF_INET

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "turkce-yz-karnesi/0.1 (https://github.com/birtohum/turkce-yz-karnesi)"
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"


def query(q: str, use_cache: bool = True) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(q.encode("utf-8")).hexdigest()[:16]
    f = CACHE / f"{key}.json"
    if use_cache and f.exists():
        return json.loads(f.read_text("utf-8"))
    for attempt in range(4):
        r = requests.get(ENDPOINT, params={"query": q, "format": "json"},
                         headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
                         timeout=120)
        if r.status_code == 200:
            rows = [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
            f.write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
            time.sleep(1)
            return rows
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    return []
