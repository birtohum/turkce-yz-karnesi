"""Ham yanıtlardan site verisini üretir: site/data/results.json, samples.json, quiz.json.

Sıralama tüm modeller için aynı soru kümesinde, yani AÇIK bölümde hesaplanır (Meta API
modellerine saklı bölüm gönderilmedi). Saklı bölüm yalnızca yerel modellerde açık/saklı
karşılaştırması için kullanılır.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .generate import CATEGORIES
from .stats import significant, bootstrap_ci, stratified_macro

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
OUT = ROOT / "site" / "data"

LOCAL_DATE = "5 Kasım 2026"
META_DATE = "5 Kasım 2026"

# dosya adı -> (görünen ad, kaynak, tam model kimliği, not)
MODELS = {
    "llama3.2_3b": ("Llama 3.2 3B", "ollama", "llama3.2:3b", "Meta, açık ağırlık"),
    "gemma3_4b": ("Gemma 3 4B", "ollama", "gemma3:4b", "Google, açık ağırlık"),
    "qwen3_8b": ("Qwen3 8B", "ollama", "qwen3:8b", "Alibaba, açık ağırlık; düşünme kapalı"),
    "qwen3_14b": ("Qwen3 14B", "ollama", "qwen3:14b", "Alibaba, açık ağırlık; düşünme kapalı"),
    "tohum-8b_latest": ("Tohum 8B", "ollama", "tohum-8b:latest",
                        "Qwen3 8B üstüne Türkçe talimat ince ayarı (bu hesabın önceki projesi)"),
    "tohum-14b-v2_latest": ("Tohum 14B v2", "ollama", "tohum-14b-v2:latest",
                            "Qwen3 14B üstüne Türkçe talimat ince ayarı (bu hesabın önceki projesi)"),
    "meta_muse-spark-1.3": ("Muse Spark 1.3", "meta", "muse-spark-1.3", "Meta, kapalı; varsayılan akıl yürütme"),
    "meta_muse-spark-1.3-contributor": ("Muse Spark 1.3 (c)", "meta", "muse-spark-1.3-contributor",
                                        "Meta, kapalı; “contributor” (veri paylaşımlı, ucuz) katmanı"),
    "meta_muse-spark-1.2": ("Muse Spark 1.2", "meta", "muse-spark-1.2", "Meta, kapalı"),
    "meta_muse-spark-1.2-contributor": ("Muse Spark 1.2 (c)", "meta", "muse-spark-1.2-contributor",
                                        "Meta, kapalı; “contributor” katmanı"),
    "meta_muse-spark-1.1": ("Muse Spark 1.1", "meta", "muse-spark-1.1", "Meta, kapalı"),
    "meta_muse-wonder-1.0": ("Muse Wonder 1.0", "meta", "muse-wonder-1.0", "Meta, kapalı"),
}
SOURCE = {"ollama": "Yerel (Ollama, RTX 3060)", "meta": "Meta Model API"}


def load_items() -> list[dict]:
    items = []
    for s in ("public", "heldout"):
        p = ROOT / "data" / f"questions_{s}.json"
        if p.exists():
            items += json.loads(p.read_text("utf-8"))
    return items


def guess_rate(it: dict) -> float:
    if it["kind"] == "exact":
        return 1 / 81
    return 1 / len(it["variants"][0]["choices"])


def load_raw(name: str) -> dict[str, dict]:
    rows = {}
    for line in (RAW / f"{name}.jsonl").read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rows[r["vid"]] = r
    return rows


def r3(x: float) -> float:
    return round(float(x), 4)


def main() -> None:
    all_items = load_items()
    items = [i for i in all_items if i["split"] == "public"]  # sıralama kümesi
    held = [i for i in all_items if i["split"] == "heldout"]
    cats = list(CATEGORIES)
    pub_vids = [v["vid"] for it in items for v in it["variants"]]

    raw = {}
    for m in MODELS:
        if not (RAW / f"{m}.jsonl").exists():
            continue
        rows = load_raw(m)
        have = sum(v in rows for v in pub_vids)
        if have < len(pub_vids):
            print(f"{m}: eksik ({have}/{len(pub_vids)}), atlandı")
            continue
        raw[m] = rows
    models = list(raw)

    def item_score(rows, it, variant=None):
        vs = it["variants"] if variant is None else [it["variants"][variant]]
        return float(np.mean([rows[v["vid"]]["status"] == "correct" for v in vs]))

    def cat_arrays(rows, its=None, variant=None):
        g = defaultdict(list)
        for it in (items if its is None else its):
            g[it["category"]].append(item_score(rows, it, variant))
        return {c: np.array(g[c]) for c in cats}

    baseline = {c: float(np.mean([guess_rate(i) for i in items if i["category"] == c])) for c in cats}
    baseline_macro = float(np.mean(list(baseline.values())))

    res = []
    for m in models:
        rows = raw[m]
        g = cat_arrays(rows)
        macro = stratified_macro(g)
        per_cat = {}
        for c in cats:
            mean, lo, hi = bootstrap_ci(g[c], seed=1)
            per_cat[c] = {"acc": r3(mean), "lo": r3(lo), "hi": r3(hi), "n": int(len(g[c]))}
        st = Counter(rows[v]["status"] for v in pub_vids)
        n = len(pub_vids)
        sc = [item_score(rows, i) for i in items]
        preds, by_pos, two = Counter(), defaultdict(list), []
        for it in items:
            if it["kind"] != "mc":
                continue
            for v in it["variants"]:
                r = rows[v["vid"]]
                if len(v["choices"]) == 4:
                    if r["pred"]:
                        preds[r["pred"]] += 1
                    by_pos[v["answer"]].append(r["status"] == "correct")
                elif r["pred"]:
                    two.append(r["pred"])
        tot = sum(preds.values()) or 1
        g0, g1 = cat_arrays(rows, variant=0), cat_arrays(rows, variant=1)
        dv = stratified_macro({c: g0[c] - g1[c] for c in cats}, seed=2)
        name, src, mid, note = MODELS[m]
        entry = {
            "id": m, "name": name, "source": src, "source_label": SOURCE[src], "model_id": mid, "note": note,
            "date": LOCAL_DATE if src == "ollama" else META_DATE,
            "macro": {"acc": r3(macro[0]), "lo": r3(macro[1]), "hi": r3(macro[2])},
            "cats": per_cat,
            "status": {k: r3(st[k] / n) for k in ("correct", "wrong", "refusal", "format")},
            "consistency": {"both": r3(np.mean([s == 1 for s in sc])), "one": r3(np.mean([s == 0.5 for s in sc]))},
            "letters4": {k: r3(preds[k] / tot) for k in "ABCD"},
            "pos_acc4": {k: r3(np.mean(by_pos[k])) for k in "ABCD"},
            "pickA2": r3(sum(p == "A" for p in two) / max(len(two), 1)),
            "wording": {"v0": r3(stratified_macro(g0)[0]), "v1": r3(stratified_macro(g1)[0]),
                        "diff": r3(dv[0]), "lo": r3(dv[1]), "hi": r3(dv[2]), "sig": significant(dv[1], dv[2])},
            "median_sec": r3(np.median([rows[v]["sec"] for v in pub_vids])),
        }
        # saklı bölüm (yalnızca yerel modeller; Meta'ya gönderilmedi)
        if held and all(v["vid"] in rows for it in held for v in it["variants"]):
            h = stratified_macro(cat_arrays(rows, its=held))
            entry["heldout"] = {"acc": r3(h[0]), "lo": r3(h[1]), "hi": r3(h[2])}
        # ikinci tekrar varsa: tekrarlar arası fark ve yanıt uyumu
        p2 = RAW / f"{m}_r2.jsonl"
        if p2.exists():
            r2 = load_raw(m + "_r2")
            if all(v in r2 for v in pub_vids):
                g2 = cat_arrays(r2)
                d = stratified_macro({c: g[c] - g2[c] for c in cats}, seed=4)
                agree = np.mean([rows[v]["pred"] == r2[v]["pred"] for v in pub_vids])
                entry["repeat"] = {"acc2": r3(stratified_macro(g2)[0]), "diff": r3(d[0]), "lo": r3(d[1]),
                                   "hi": r3(d[2]), "sig": significant(d[1], d[2]), "agree": r3(agree)}
        if src == "meta":
            entry["mean_ctok"] = r3(np.mean([rows[v].get("ctok", 0) for v in pub_vids]))
        res.append(entry)
    res.sort(key=lambda x: -x["macro"]["acc"])
    # Tohum ince ayarları çoğunlukla harf yerine yeni bir soru üretti; bilgi ölçümü sayılamaz.
    aux = [x for x in res if x["id"].startswith("tohum")]
    res = [x for x in res if not x["id"].startswith("tohum")]
    main_ids = [x["id"] for x in res]

    pairs = []
    for i, a in enumerate(res):
        for b in res[i + 1:]:
            ga, gb = cat_arrays(raw[a["id"]]), cat_arrays(raw[b["id"]])
            d = stratified_macro({c: ga[c] - gb[c] for c in cats}, seed=3)
            pairs.append({"a": a["id"], "b": b["id"], "diff": r3(d[0]), "lo": r3(d[1]), "hi": r3(d[2]),
                          "sig": significant(d[1], d[2])})

    # tartışmalı sorular: API modellerinin en az yarısının iki ifadede de "yanlış" bildiği sorular.
    # Bunlar Wikidata hatası ya da ad belirsizliği adayıdır; elle incelenmeli.
    api = [m for m in main_ids if MODELS[m][1] == "meta"]
    disputed = []
    if api:
        for it in items:
            wrong = [m for m in api if item_score(raw[m], it) == 0]
            if len(wrong) * 2 >= len(api):
                v = it["variants"][0]
                ch = v.get("choices")
                gold = ch["ABCD".index(v["answer"])] if ch else v["answer"]
                said = Counter()
                for m in wrong:
                    r = raw[m][v["vid"]]
                    said[(ch["ABCD".index(r["pred"])] if (ch and r["pred"]) else (r["pred"] or "yanıt yok"))] += 1
                disputed.append({"cat": it["category"], "q": v["prompt"].split("\nA) ")[0] + (" (" + " / ".join(ch) + ")" if ch else ""),
                                 "gold": gold,
                                 "api_said": said.most_common(1)[0][0], "n_wrong": len(wrong), "n_api": len(api)})

    spend = None
    sp = ROOT / "results" / "meta_harcama.jsonl"
    if sp.exists():
        rows = [json.loads(l) for l in sp.read_text("utf-8").splitlines() if l.strip()]
        spend = {"usd": round(sum(r["usd"] for r in rows), 2), "calls": len(rows)}

    OUT.mkdir(parents=True, exist_ok=True)
    counts = Counter((i["category"], i["split"]) for i in all_items)
    meta = {
        "n_items": len(items), "n_variants": len(pub_vids), "n_heldout": len(held),
        "categories": {c: {"label": CATEGORIES[c], "baseline": r3(baseline[c]),
                           "public": counts[(c, "public")], "heldout": counts[(c, "heldout")]} for c in cats},
        "baseline_macro": r3(baseline_macro),
        "heldout_sha256": (ROOT / "data" / "heldout.sha256").read_text().split()[0],
        "meta_spend": spend,
    }
    (OUT / "results.json").write_text(json.dumps({"meta": meta, "models": res, "aux": aux, "pairs": pairs, "disputed": disputed},
                                                 ensure_ascii=False, indent=1), "utf-8")

    rng = random.Random(5)
    samples = []
    for c in cats:
        pool = [i for i in items if i["category"] == c]
        for it in rng.sample(pool, min(3, len(pool))):
            v = it["variants"][0]
            samples.append({"cat": c, "prompt": v["prompt"], "answer": v["answer"], "choices": v.get("choices"),
                            "models": {m: {"out": raw[m][v["vid"]]["out"].strip()[:80],
                                           "status": raw[m][v["vid"]]["status"]} for m in main_ids}})
    (OUT / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=1), "utf-8")

    quiz = []
    for it in items:
        if it["kind"] != "mc":
            continue
        v = it["variants"][0]
        quiz.append({"c": it["category"], "q": v["prompt"].split("\nA) ")[0], "o": v["choices"],
                     "a": "ABCD".index(v["answer"]),
                     "m": [int(raw[m][v["vid"]]["status"] == "correct") for m in main_ids]})
    (OUT / "quiz.json").write_text(json.dumps({"models": main_ids, "items": quiz},
                                              ensure_ascii=False, separators=(",", ":")), "utf-8")

    pubdir = ROOT / "results" / "public_raw"
    pubdir.mkdir(parents=True, exist_ok=True)
    pub_set = set(pub_vids)
    for m in list(raw) + [p.stem for p in RAW.glob("*_r2.jsonl")]:
        rows = load_raw(m)
        keep = [r for v, r in rows.items() if v in pub_set]
        (pubdir / f"{m}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), "utf-8")

    for x in res + aux:
        extra = f' tekrar2={x["repeat"]["acc2"]:.3f} uyum={x["repeat"]["agree"]:.3f}' if "repeat" in x else ""
        print(f'{x["name"]:30s} {x["macro"]["acc"]:.3f} [{x["macro"]["lo"]:.3f},{x["macro"]["hi"]:.3f}] '
              + " ".join(f'{c}={x["cats"][c]["acc"]:.2f}' for c in cats)
              + f' biçim={x["status"]["format"]:.3f} A4={x["letters4"]["A"]:.2f}' + extra)
    print("şans tabanı", round(baseline_macro, 4), "harcama", spend)


if __name__ == "__main__":
    main()
