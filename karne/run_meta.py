"""Meta Model API modellerini AÇIK bölüm üzerinde çalıştırır (saklı bölüm Meta'ya gönderilmez).

Kullanım: python -m karne.run_meta muse-spark-1.3 [--rep 1] [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .grade import grade
from .meta import ButceAsildi, harcama, sohbet
from .run import ROOT, SYSTEM, load_items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    items = load_items("public")
    suffix = "" if a.rep == 1 else f"_r{a.rep}"
    out = ROOT / "results" / "raw" / f"meta_{a.model}{suffix}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(l)["vid"] for l in out.read_text("utf-8").splitlines() if l.strip()}
    todo = [(it, v) for it in items for v in it["variants"] if v["vid"] not in done]
    lock = threading.Lock()
    f = out.open("a", encoding="utf-8")
    n = [0]
    t0 = time.time()

    def one(pair):
        it, v = pair
        t = time.time()
        text, usage, fin = sohbet(a.model, [{"role": "system", "content": SYSTEM},
                                            {"role": "user", "content": v["prompt"]}], max_tokens=4096)
        g = grade(v, it["kind"], text)
        row = {"vid": v["vid"], "id": it["id"], "out": text, "sec": round(time.time() - t, 3), **g,
               "finish": fin, "ctok": usage.get("completion_tokens", 0)}
        with lock:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            n[0] += 1
            if n[0] % 200 == 0:
                print(f"{a.model} r{a.rep}: {n[0]}/{len(todo)}, toplam harcama {harcama():.3f} $, "
                      f"{(time.time() - t0) / 60:.1f} dk", flush=True)

    try:
        with ThreadPoolExecutor(a.workers) as ex:
            for _ in ex.map(one, todo):
                pass
    except ButceAsildi as e:
        print("DURDU:", e, flush=True)
    f.close()
    print(f"{a.model} r{a.rep}: bitti, {n[0]} yeni yanıt, toplam harcama {harcama():.3f} $", flush=True)


if __name__ == "__main__":
    main()
