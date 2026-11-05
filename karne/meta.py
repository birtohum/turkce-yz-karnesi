"""Meta Model API istemcisi (OpenAI uyumlu) — harcama defteri, sert bütçe sınırı ve hız sınırıyla.

Anahtar yalnızca ortam değişkeninden ya da ~/.pflow-anahtarlar.env dosyasından kodda okunur;
hiçbir yere yazılmaz, basılmaz. Contributor modunda gönderilen içerik Meta tarafından
kullanılabileceği için bu modellere yalnızca AÇIK bölüm soruları gönderilir (saklı bölüm değil).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests

BASE = "https://api.meta.ai/v1"
# 1M token başına USD (girdi, çıktı); bilinmeyen model için en pahalı bilinen fiyat varsayılır
FIYAT = {"muse-spark-1.3-contributor": (0.10, 0.20), "muse-spark-1.3": (1.25, 4.25)}
VARSAYILAN_FIYAT = (1.25, 4.25)  # fiyatı bilinmeyen modelde temkinli (yüksek) varsayım
SINIR_USD = 120.0
ROOT = Path(__file__).resolve().parent.parent
DEFTER = ROOT / "results" / "meta_harcama.jsonl"
ANAHTAR_DOSYASI = Path.home() / ".pflow-anahtarlar.env"
_kilit = threading.Lock()


class ButceAsildi(RuntimeError):
    pass


def _anahtar() -> str:
    if os.environ.get("META_MODEL_API_KEY"):
        return os.environ["META_MODEL_API_KEY"]
    for satir in ANAHTAR_DOSYASI.read_text(encoding="utf-8").splitlines():
        if satir.startswith("META_MODEL_API_KEY="):
            return satir.split("=", 1)[1].strip()
    raise RuntimeError("META_MODEL_API_KEY bulunamadı")


def harcama() -> float:
    if not DEFTER.exists():
        return 0.0
    tot = 0.0
    for s in DEFTER.read_text(encoding="utf-8").splitlines():
        try:
            tot += json.loads(s)["usd"]
        except (ValueError, KeyError):
            pass
    return tot


def _kaydet(model: str, usage: dict) -> float:
    gf, cf = FIYAT.get(model, VARSAYILAN_FIYAT)
    g, c = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    usd = g / 1e6 * gf + c / 1e6 * cf
    with _kilit:
        DEFTER.parent.mkdir(parents=True, exist_ok=True)
        with DEFTER.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"usd": usd, "g": g, "c": c, "m": model, "t": round(time.time())}) + "\n")
    return usd


class _Hiz:
    def __init__(self, rpm: int):
        self.rpm, self.z, self.k = rpm, [], threading.Lock()

    def bekle(self):
        while True:
            with self.k:
                now = time.time()
                self.z = [t for t in self.z if now - t < 60]
                if len(self.z) < self.rpm:
                    self.z.append(now)
                    return
                w = 60 - (now - self.z[0]) + 0.05
            time.sleep(w)


_hiz = _Hiz(int(os.environ.get("KARNE_RPM", "120")))
_toplam = [None]


def modeller() -> list[str]:
    r = requests.get(f"{BASE}/models", headers={"Authorization": f"Bearer {_anahtar()}"}, timeout=60)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


def sohbet(model: str, messages: list, max_tokens: int, temperature: float = 0.0) -> tuple[str, dict, str]:
    with _kilit:
        if _toplam[0] is None:
            _toplam[0] = harcama()
        if _toplam[0] >= SINIR_USD:
            raise ButceAsildi(f"bütçe sınırı {SINIR_USD} $ doldu")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    hdr = {"Authorization": f"Bearer {_anahtar()}"}
    for i in range(8):
        _hiz.bekle()
        try:
            r = requests.post(f"{BASE}/chat/completions", headers=hdr, json=body, timeout=300)
        except requests.RequestException:
            time.sleep(min(60, 3 * 2 ** i))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 3 * 2 ** i))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        try:
            d = r.json()
        except ValueError:
            time.sleep(3 * 2 ** i)
            continue
        usage = d.get("usage") or {}
        usd = _kaydet(model, usage)
        with _kilit:
            _toplam[0] += usd
        ch = d["choices"][0]
        return ch["message"].get("content") or "", usage, ch.get("finish_reason") or ""
    raise RuntimeError("Meta isteği başarısız")


if __name__ == "__main__":
    print(modeller())
    print(f"defterdeki harcama: {harcama():.4f} $")
