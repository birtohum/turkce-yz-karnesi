"""Modelleri tek tek, yerel Ollama üzerinden çalıştırır. Kaldığı yerden devam eder.

Kullanım: python -m karne.run qwen3:8b [--split public|heldout|all] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

from .grade import grade

ROOT = Path(__file__).resolve().parent.parent
OLLAMA = "http://127.0.0.1:11434/api/chat"

SYSTEM = ("Türkiye hakkında bilgi sorularını yanıtlıyorsun. Çoktan seçmeli sorularda yalnızca "
          "doğru seçeneğin harfini yaz (A, B, C veya D). Sayı istenen sorularda yalnızca sayıyı yaz. "
          "Açıklama yapma.")


def gpu_state() -> tuple[int, int]:
    """(boş VRAM MiB, kullanım %)"""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
        free, util = [int(x) for x in out.strip().split(",")]
        return free, util
    except Exception:
        return 99999, 0


def load_items(split: str) -> list[dict]:
    items = []
    for s in (["public", "heldout"] if split == "all" else [split]):
        items += json.loads((ROOT / "data" / f"questions_{s}.json").read_text("utf-8"))
    return items


def ask(model: str, prompt: str, think_flag: bool | None) -> tuple[str, float]:
    body = {"model": model, "stream": False, "keep_alive": "5m",
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_predict": 16, "num_ctx": 1024, "seed": 0}}
    if think_flag is not None:
        body["think"] = think_flag
    t = time.time()
    r = requests.post(OLLAMA, json=body, timeout=300)
    if r.status_code == 400 and "think" in r.text and think_flag is not None:
        raise ValueError("nothink")
    r.raise_for_status()
    return r.json()["message"]["content"], time.time() - t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--split", default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-free-mib", type=int, default=0,
                    help="bu kadar boş VRAM yoksa beklemek için (oyun vb. açıkken)")
    a = ap.parse_args()

    items = load_items(a.split)
    if a.limit:
        items = items[: a.limit]
    out = ROOT / "results" / "raw" / (a.model.replace(":", "_").replace("/", "_") + ".jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text("utf-8").splitlines():
            done.add(json.loads(line)["vid"])

    while a.min_free_mib and gpu_state()[0] < a.min_free_mib:
        print("GPU meşgul, bekleniyor...", gpu_state(), flush=True)
        time.sleep(60)

    think_flag: bool | None = False
    n = 0
    t0 = time.time()
    with out.open("a", encoding="utf-8") as f:
        for it in items:
            for v in it["variants"]:
                if v["vid"] in done:
                    continue
                try:
                    text, dt = ask(a.model, v["prompt"], think_flag)
                except ValueError:
                    think_flag = None
                    text, dt = ask(a.model, v["prompt"], think_flag)
                g = grade(v, it["kind"], text)
                f.write(json.dumps({"vid": v["vid"], "id": it["id"], "out": text, "sec": round(dt, 3), **g},
                                   ensure_ascii=False) + "\n")
                n += 1
                if n % 200 == 0:
                    f.flush()
                    print(f"{a.model}: {n} yanıt, {(time.time() - t0) / n:.2f} sn/yanıt", flush=True)
    print(f"{a.model}: bitti, {n} yeni yanıt", flush=True)


if __name__ == "__main__":
    sys.exit(main())
