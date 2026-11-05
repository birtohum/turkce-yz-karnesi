"""Ham yanıtlardan site verisini üretir: site/data/results.json, samples.json, quiz.json."""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .generate import CATEGORIES
from .stats import bootstrap_ci, significant, stratified_macro

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
OUT = ROOT / "site" / "data"

MODELS = {  # dosya adı -> (görünen ad, not)
    "llama3.2_3b": ("Llama 3.2 3B", "Meta, açık ağırlık"),
    "gemma3_4b": ("Gemma 3 4B", "Google, açık ağırlık"),
    "qwen3_8b": ("Qwen3 8B", "Alibaba, açık ağırlık; düşünme kapalı"),
    "tohum-8b_latest": ("Tohum 8B", "Qwen3 8B üstüne Türkçe talimat ince ayarı (bu hesabın önceki projesi)"),
    "qwen3_14b": ("Qwen3 14B", "Alibaba, açık ağırlık; düşünme kapalı"),
    "tohum-14b-v2_latest": ("Tohum 14B v2", "Qwen3 14B üstüne Türkçe talimat ince ayarı (bu hesabın önceki projesi)"),
}


def load_items() -> list[dict]:
    items = []
    for s in ("public", "heldout"):
        items += json.loads((ROOT / "data" / f"questions_{s}.json").read_text("utf-8"))
    return items


def guess_rate(it: dict) -> float:
    if it["kind"] == "exact":
        return 1 / 81
    return 1 / len(it["variants"][0]["choices"])


def load_raw(name: str) -> dict[str, dict]:
    p = RAW / f"{name}.jsonl"
    rows = {}
    for line in p.read_text("utf-8").splitlines():
        r = json.loads(line)
        rows[r["vid"]] = r
    return rows


def r3(x: float) -> float:
    return round(float(x), 4)


def main() -> None:
    items = load_items()
    by_id = {i["id"]: i for i in items}
    cats = list(CATEGORIES)
    models = [m for m in MODELS if (RAW / f"{m}.jsonl").exists()]
    vids = [v["vid"] for it in items for v in it["variants"]]

    raw, score = {}, {}
    for m in models:
        rows = load_raw(m)
        if not all(v in rows for v in vids):
            print(f"{m}: eksik ({sum(v in rows for v in vids)}/{len(vids)}), atlandı")
            continue
        raw[m] = rows
    models = list(raw)

    # soru puanı = iki varyantın ortalaması
    for m in models:
        score[m] = {it["id"]: np.mean([raw[m][v["vid"]]["status"] == "correct" for v in it["variants"]])
                    for it in items}

    def cat_arrays(m, split=None, variant=None):
        g = defaultdict(list)
        for it in items:
            if split and it["split"] != split:
                continue
            if variant is None:
                s = score[m][it["id"]]
            else:
                s = float(raw[m][it["variants"][variant]["vid"]]["status"] == "correct")
            g[it["category"]].append(s)
        return {c: np.array(g[c]) for c in cats}

    baseline = {c: float(np.mean([guess_rate(i) for i in items if i["category"] == c])) for c in cats}
    baseline_macro = float(np.mean(list(baseline.values())))

    res_models = []
    for m in models:
        g = cat_arrays(m)
        macro = stratified_macro(g)
        per_cat = {}
        for c in cats:
            mean, lo, hi = bootstrap_ci(g[c], seed=1)
            per_cat[c] = {"acc": r3(mean), "lo": r3(lo), "hi": r3(hi), "n": int(len(g[c]))}
        st = Counter(r["status"] for r in raw[m].values())
        n = sum(st.values())
        # tutarlılık: iki varyant da doğru / yalnız biri doğru
        both = np.mean([score[m][i["id"]] == 1 for i in items])
        one = np.mean([score[m][i["id"]] == 0.5 for i in items])
        # konum yanlılığı: 4 seçenekli sorularda tahmin edilen harf dağılımı ve doğru harfe göre başarı
        preds = Counter()
        by_pos = defaultdict(list)
        for it in items:
            if it["kind"] != "mc" or len(it["variants"][0]["choices"]) != 4:
                continue
            for v in it["variants"]:
                r = raw[m][v["vid"]]
                if r["pred"]:
                    preds[r["pred"]] += 1
                by_pos[v["answer"]].append(r["status"] == "correct")
        tot = sum(preds.values()) or 1
        pos_acc = {k: r3(np.mean(by_pos[k])) for k in "ABCD"}
        # iki seçenekli sorular: A'yı seçme oranı (doğru cevap dengeli dağıtıldı, beklenen ~%50)
        two = [raw[m][v["vid"]]["pred"] for it in items if it["kind"] == "mc"
               and len(it["variants"][0]["choices"]) == 2 for v in it["variants"]]
        two = [p for p in two if p]
        # ifade etkisi: v0 - v1 (v1 yeniden ifade ya da ters soru)
        v0 = stratified_macro(cat_arrays(m, variant=0))[0]
        v1 = stratified_macro(cat_arrays(m, variant=1))[0]
        dv = stratified_macro({c: cat_arrays(m, variant=0)[c] - cat_arrays(m, variant=1)[c] for c in cats}, seed=2)
        pub = stratified_macro(cat_arrays(m, split="public"))
        held = stratified_macro(cat_arrays(m, split="heldout"))
        res_models.append({
            "id": m, "name": MODELS[m][0], "note": MODELS[m][1],
            "macro": {"acc": r3(macro[0]), "lo": r3(macro[1]), "hi": r3(macro[2])},
            "cats": per_cat,
            "status": {k: r3(st[k] / n) for k in ("correct", "wrong", "refusal", "format")},
            "consistency": {"both": r3(both), "one": r3(one)},
            "letters4": {k: r3(preds[k] / tot) for k in "ABCD"},
            "pos_acc4": pos_acc,
            "pickA2": r3(sum(p == "A" for p in two) / max(len(two), 1)),
            "wording": {"v0": r3(v0), "v1": r3(v1), "diff": r3(dv[0]), "lo": r3(dv[1]), "hi": r3(dv[2]),
                        "sig": significant(dv[1], dv[2])},
            "split": {"public": r3(pub[0]), "public_ci": [r3(pub[1]), r3(pub[2])],
                      "heldout": r3(held[0]), "heldout_ci": [r3(held[1]), r3(held[2])]},
            "median_sec": r3(np.median([r["sec"] for r in raw[m].values()])),
        })
    res_models.sort(key=lambda x: -x["macro"]["acc"])
    # Tohum ince ayarları çoğunlukla harf yerine yeni bir soru üretti; bilgi ölçümü sayılamaz,
    # ana sıralamanın dışında ayrı gösterilir.
    aux = [x for x in res_models if x["id"].startswith("tohum")]
    res_models = [x for x in res_models if not x["id"].startswith("tohum")]
    models = [x["id"] for x in res_models]

    # ikili fark testleri (eşleştirilmiş, kategori tabakalı)
    pairs = []
    for i, a in enumerate(res_models):
        for b in res_models[i + 1:]:
            ga, gb = cat_arrays(a["id"]), cat_arrays(b["id"])
            d = stratified_macro({c: ga[c] - gb[c] for c in cats}, seed=3)
            pairs.append({"a": a["id"], "b": b["id"], "diff": r3(d[0]), "lo": r3(d[1]), "hi": r3(d[2]),
                          "sig": significant(d[1], d[2])})
    # kategori bazında da: en iyi ile ikinci arasındaki fark
    OUT.mkdir(parents=True, exist_ok=True)
    counts = Counter((i["category"], i["split"]) for i in items)
    meta = {
        "n_items": len(items), "n_variants": len(vids),
        "categories": {c: {"label": CATEGORIES[c], "baseline": r3(baseline[c]),
                           "public": counts[(c, "public")], "heldout": counts[(c, "heldout")]} for c in cats},
        "baseline_macro": r3(baseline_macro),
        "heldout_sha256": (ROOT / "data" / "heldout.sha256").read_text().split()[0],
    }
    (OUT / "results.json").write_text(json.dumps({"meta": meta, "models": res_models, "aux": aux, "pairs": pairs},
                                                 ensure_ascii=False, indent=1), "utf-8")

    # örnek sorular (yalnızca açık bölümden), her modelin v0 yanıtı
    rng = random.Random(5)
    pub = [i for i in items if i["split"] == "public"]
    samples = []
    for c in cats:
        pool = [i for i in pub if i["category"] == c]
        for it in rng.sample(pool, min(3, len(pool))):
            v = it["variants"][0]
            samples.append({"cat": c, "prompt": v["prompt"], "answer": v["answer"],
                            "choices": v.get("choices"),
                            "models": {m: {"out": raw[m][v["vid"]]["out"].strip()[:80],
                                           "status": raw[m][v["vid"]]["status"]} for m in models}})
    (OUT / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=1), "utf-8")

    # "Kendin dene" havuzu: açık bölümdeki çoktan seçmeli sorular, v0 biçimi
    quiz = []
    for it in pub:
        if it["kind"] != "mc":
            continue
        v = it["variants"][0]
        stem = v["prompt"].split("\nA) ")[0]
        quiz.append({"c": it["category"], "q": stem, "o": v["choices"], "a": "ABCD".index(v["answer"]),
                     "m": [int(raw[m][v["vid"]]["status"] == "correct") for m in [x["id"] for x in res_models]]})
    (OUT / "quiz.json").write_text(json.dumps({"models": [x["id"] for x in res_models], "items": quiz},
                                              ensure_ascii=False, separators=(",", ":")), "utf-8")
    # depoya konacak ham yanıtlar: yalnızca açık bölüm
    pubdir = ROOT / "results" / "public_raw"
    pubdir.mkdir(parents=True, exist_ok=True)
    pub_ids = {i["id"] for i in pub}
    for m in list(raw):
        rows = [r for r in raw[m].values() if r["id"] in pub_ids]
        (pubdir / f"{m}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    for x in res_models + aux:
        print(f'{x["name"]:14s} {x["macro"]["acc"]:.3f} [{x["macro"]["lo"]:.3f},{x["macro"]["hi"]:.3f}] '
              + " ".join(f'{c}={x["cats"][c]["acc"]:.2f}' for c in cats)
              + f' format={x["status"]["format"]:.3f} ret={x["status"]["refusal"]:.3f}')
    print("şans tabanı", baseline_macro)


if __name__ == "__main__":
    main()
