"""Wikidata'dan Türkiye'ye özgü, tek ve denetlenebilir cevaplı sorular üretir.

Her soru (item) iki varyantla sorulur:
  v0: A kalıbı, seçenekler bir sırada
  v1: B kalıbı (yeniden ifade ya da ters soru), seçenekler başka sırada
Böylece hem ezberlenmiş ifadeye hem de seçenek konumuna bağımlılık ölçülebilir.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from .sparql import query

ROOT = Path(__file__).resolve().parent.parent
LETTERS = "ABCD"
HELDOUT_SALT = "karne-2026-11"
HELDOUT_FRAC = 0.2
PER_CAT = 300


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def is_heldout(item_id: str) -> bool:
    h = hashlib.sha256(f"{HELDOUT_SALT}:{item_id}".encode()).digest()
    return h[0] < 256 * HELDOUT_FRAC


def clean_label(label: str, q: str) -> str | None:
    """Etiket yoksa (Q-id dönüyorsa) None."""
    if not label or re.fullmatch(r"Q\d+", label) or label == q:
        return None
    # "Pehlivanköy (ilçe)" gibi ayrım eklerini at
    label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
    return label or None


# ---------------------------------------------------------------- sorgular
Q_PROV = """SELECT ?p ?pLabel ?plate ?cap ?capLabel ?elev WHERE {
 ?p wdt:P31 wd:Q48336 . FILTER NOT EXISTS { ?p wdt:P576 ?end }
 OPTIONAL { ?p wdt:P395 ?plate }
 OPTIONAL { ?p wdt:P36 ?cap . OPTIONAL { ?cap wdt:P2044 ?elev } }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "tr". } }"""

Q_POP = """SELECT ?p ?pop ?date WHERE { ?p wdt:P31 wd:Q48336 ; p:P1082 ?st .
 ?st ps:P1082 ?pop ; pq:P585 ?date . FILTER NOT EXISTS { ?st wikibase:rank wikibase:DeprecatedRank } }"""

Q_DIST = """SELECT ?d ?dLabel ?prov WHERE { ?d wdt:P31 wd:Q1147395 ; wdt:P131 ?prov .
 ?prov wdt:P31 wd:Q48336 . FILTER NOT EXISTS { ?d wdt:P576 ?end }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "tr". } }"""

Q_LAKE = """SELECT ?l ?lLabel ?prov ?kind WHERE {
 VALUES ?kind { wd:Q23397 wd:Q131681 }
 ?l wdt:P31 ?kind ; wdt:P17 wd:Q43 ; wdt:P131 ?x . ?x wdt:P131* ?prov . ?prov wdt:P31 wd:Q48336 .
 SERVICE wikibase:label { bd:serviceParam wikibase:language "tr". } }"""

Q_HUMAN = """SELECT ?h ?hLabel ?b ?prec ?sl (COUNT(DISTINCT ?ref) AS ?nref) WHERE {
 ?h wdt:P31 wd:Q5 ; wdt:P27 wd:Q43 ; wikibase:sitelinks ?sl . FILTER(?sl >= 20)
 ?tr schema:about ?h ; schema:isPartOf <https://tr.wikipedia.org/> .
 ?h p:P569 ?st . ?st psv:P569 ?bv . ?bv wikibase:timeValue ?b ; wikibase:timePrecision ?prec .
 FILTER NOT EXISTS { ?st wikibase:rank wikibase:DeprecatedRank }
 OPTIONAL { ?st prov:wasDerivedFrom ?ref }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "tr". } } GROUP BY ?h ?hLabel ?b ?prec ?sl"""


# ---------------------------------------------------------------- yardımcılar
def mc_variant(stem: str, correct: str, distractors: list[str], correct_pos: int) -> dict:
    """Doğru cevap `correct_pos` konumunda olacak şekilde seçenekleri dizer."""
    n = len(distractors) + 1
    assert 0 <= correct_pos < n
    opts = list(distractors)
    opts.insert(correct_pos, correct)
    assert len(set(opts)) == n, opts
    lines = "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(opts))
    return {"prompt": f"{stem}\n{lines}", "choices": opts, "answer": LETTERS[correct_pos]}


def two_positions(rng: random.Random, n: int, counter: list[int]) -> tuple[int, int]:
    """v0 ve v1 için farklı doğru-cevap konumları; konumlar veri boyunca dengeli dağılır."""
    p0 = counter[0] % n
    counter[0] += 1
    p1 = (p0 + rng.randrange(1, n)) % n
    return p0, p1


def make_item(cat: str, key: str, variants: list[dict], kind: str, meta: dict) -> dict:
    iid = f"{cat}:{key}"
    return {"id": iid, "category": cat, "kind": kind,
            "split": "heldout" if is_heldout(iid) else "public",
            "variants": [dict(v, vid=f"{iid}#{i}") for i, v in enumerate(variants)],
            "meta": meta}


# ---------------------------------------------------------------- veri
def load_provinces() -> dict[str, dict]:
    rows = query(Q_PROV)
    prov: dict[str, dict] = {}
    plates, elevs = defaultdict(set), defaultdict(set)
    for r in rows:
        q = qid(r["p"])
        name = clean_label(r.get("pLabel", ""), q)
        if not name:
            continue
        prov.setdefault(q, {"qid": q, "name": name, "cap": None, "cap_name": None})
        if "plate" in r:
            plates[q].add(r["plate"].strip())
        if "cap" in r:
            prov[q]["cap"] = qid(r["cap"])
            prov[q]["cap_name"] = clean_label(r.get("capLabel", ""), qid(r["cap"]))
            if "elev" in r:
                elevs[q].add(round(float(r["elev"])))
    for q, p in prov.items():
        ps = {x for x in plates[q] if re.fullmatch(r"\d{2}", x)}
        p["plate"] = int(ps.pop()) if len(ps) == 1 else None  # çelişkili ise at
        p["elev"] = elevs[q].pop() if len(elevs[q]) == 1 else None
    return prov


def latest_population(rows: list[dict]) -> dict[str, dict]:
    """Her il için en son tarihli nüfus; aynı tarihte farklı değer varsa il atılır."""
    by = defaultdict(lambda: defaultdict(set))
    for r in rows:
        by[qid(r["p"])][r["date"][:10]].add(round(float(r["pop"])))
    out = {}
    for q, dates in by.items():
        ds = sorted(dates)
        last = ds[-1]
        if len(dates[last]) != 1:
            continue
        prev = None
        for d in reversed(ds[:-1]):
            if len(dates[d]) == 1:
                prev = (d, next(iter(dates[d])))
                break
        out[q] = {"date": last, "pop": next(iter(dates[last])), "prev": prev}
    return out


# ---------------------------------------------------------------- kategoriler
def cat_population(prov, pops, rng) -> list[dict]:
    ok = [q for q in prov if q in pops]
    pairs = [(a, b) for i, a in enumerate(ok) for b in ok[i + 1:]]
    rng.shuffle(pairs)
    items, ctr = [], [0]
    for a, b in pairs:
        pa, pb = pops[a]["pop"], pops[b]["pop"]
        big, small = (a, b) if pa > pb else (b, a)
        if max(pa, pb) / min(pa, pb) < 1.15:  # yakın nüfuslar belirsiz: at
            continue
        # önceki sayımda sıra tersse çelişkili say, at
        if pops[a]["prev"] and pops[b]["prev"]:
            if (pops[a]["prev"][1] > pops[b]["prev"][1]) != (pa > pb):
                continue
        nb, ns = prov[big]["name"], prov[small]["name"]
        p0, p1 = two_positions(rng, 2, ctr)
        first, second = (nb, ns) if rng.random() < .5 else (ns, nb)
        v0 = mc_variant(f"Hangi ilin nüfusu daha fazladır?", nb, [ns], p0)
        v1 = mc_variant(f"{first} ile {second} karşılaştırıldığında hangisinin nüfusu daha azdır?", ns, [nb], p1)
        items.append(make_item("nufus", f"{big}-{small}", [v0, v1], "mc",
                               {"big": big, "small": small, "pop": {big: pops[big], small: pops[small]}}))
        if len(items) >= PER_CAT:
            break
    return items


def cat_altitude(prov, rng) -> list[dict]:
    ok = [q for q, p in prov.items() if p["elev"] is not None and p["cap_name"]]
    pairs = [(a, b) for i, a in enumerate(ok) for b in ok[i + 1:]]
    rng.shuffle(pairs)
    items, ctr = [], [0]
    for a, b in pairs:
        ea, eb = prov[a]["elev"], prov[b]["elev"]
        if abs(ea - eb) < 200:  # rakım ölçüm noktasına göre değişir; küçük farklar belirsiz
            continue
        hi, lo = (a, b) if ea > eb else (b, a)
        nh, nl = prov[hi]["cap_name"], prov[lo]["cap_name"]
        if nh == nl:
            continue
        p0, p1 = two_positions(rng, 2, ctr)
        v0 = mc_variant("Hangi şehir merkezi deniz seviyesinden daha yüksektedir?", nh, [nl], p0)
        v1 = mc_variant("Aşağıdaki iki şehirden hangisi daha alçakta (deniz seviyesine daha yakın) yer alır?", nl, [nh], p1)
        items.append(make_item("rakim", f"{hi}-{lo}", [v0, v1], "mc",
                               {"high": prov[hi]["cap"], "low": prov[lo]["cap"],
                                "elev": {nh: prov[hi]["elev"], nl: prov[lo]["elev"]}}))
        if len(items) >= PER_CAT:
            break
    return items


def cat_district(prov, rng) -> list[dict]:
    rows = query(Q_DIST)
    by_name = defaultdict(set)
    for r in rows:
        d = qid(r["d"])
        name = clean_label(r.get("dLabel", ""), d)
        if name and qid(r["prov"]) in prov:
            by_name[name].add((d, qid(r["prov"])))
    prov_names = {p["name"] for p in prov.values()}
    cands = []
    for name, s in by_name.items():
        provs = {p for _, p in s}
        ds = {d for d, _ in s}
        # aynı adlı ilçe birden fazla ilde, birden çok P131 ya da il adıyla aynı: belirsiz
        if len(provs) != 1 or len(ds) != 1 or name in prov_names or "Merkez" in name:
            continue
        cands.append((name, ds.pop(), provs.pop()))
    cands.sort()
    rng.shuffle(cands)
    allp = sorted(prov)
    items, ctr = [], [0]
    for name, d, p in cands[:PER_CAT]:
        # "Hasköy İlçesi" gibi etiketlerde ek tekrarını önle (aday sırası değişmesin diye burada)
        name = re.sub(r"\s+[İi]lçesi$", "", name)
        wrong = rng.sample([x for x in allp if x != p], 3)
        names = [prov[x]["name"] for x in wrong]
        p0, p1 = two_positions(rng, 4, ctr)
        v0 = mc_variant(f"{name} ilçesi hangi ile bağlıdır?", prov[p]["name"], names, p0)
        v1 = mc_variant(f"{name} hangi ilin ilçelerinden biridir?", prov[p]["name"], rng.sample(names, 3), p1)
        items.append(make_item("ilce", d, [v0, v1], "mc", {"district": d, "province": p}))
    return items


def cat_plate(prov, rng) -> list[dict]:
    ok = sorted(q for q, p in prov.items() if p["plate"])
    # Aynı kodu iki ile veren kayıtlar çelişkilidir (ör. Wikidata'da Konya=53, Uşak=62
    # yazıyordu); ikisini de at.
    cnt = defaultdict(int)
    for q in ok:
        cnt[prov[q]["plate"]] += 1
    ok = [q for q in ok if cnt[prov[q]["plate"]] == 1]
    plates = [prov[q]["plate"] for q in ok]
    assert len(set(plates)) == len(plates), "plaka kodları tekil olmalı"
    items, ctr = [], [0]
    for q in ok:
        n, code = prov[q]["name"], prov[q]["plate"]
        v0 = {"prompt": f"{n} ilinin plaka kodu kaçtır? Yalnızca sayıyı yaz.", "answer": str(code)}
        v1 = {"prompt": f"Araç plakalarında {n} için kullanılan il kodu hangi sayıdır? Yalnızca sayıyı yaz.", "answer": str(code)}
        items.append(make_item("plaka", q, [v0, v1], "exact", {"province": q, "plate": code}))
    # ters yön: koddan ile (çoktan seçmeli)
    for q in ok:
        n, code = prov[q]["name"], prov[q]["plate"]
        wrong = [prov[x]["name"] for x in rng.sample([x for x in ok if x != q], 3)]
        p0, p1 = two_positions(rng, 4, ctr)
        v0 = mc_variant(f"Plaka kodu {code:02d} olan il hangisidir?", n, wrong, p0)
        v1 = mc_variant(f"Bir aracın plakası {code:02d} ile başlıyorsa araç hangi ilde kayıtlıdır?", n, rng.sample(wrong, 3), p1)
        items.append(make_item("plaka", f"r{q}", [v0, v1], "mc", {"province": q, "plate": code}))
    return items


def cat_lake(prov, rng) -> list[dict]:
    rows = query(Q_LAKE)
    by = defaultdict(set)
    names = {}
    for r in rows:
        l = qid(r["l"])
        nm = clean_label(r.get("lLabel", ""), l)
        if nm and qid(r["prov"]) in prov:
            by[l].add(qid(r["prov"]))
            names[l] = nm
    cnt = defaultdict(int)
    for l in by:
        cnt[names[l]] += 1
    cands = sorted((names[l], l, next(iter(ps))) for l, ps in by.items()
                   if len(ps) == 1 and cnt[names[l]] == 1)
    rng.shuffle(cands)
    allp = sorted(prov)
    items, ctr = [], [0]
    for nm, l, p in cands[:PER_CAT]:
        wrong = [prov[x]["name"] for x in rng.sample([x for x in allp if x != p], 3)]
        p0, p1 = two_positions(rng, 4, ctr)
        v0 = mc_variant(f"{nm} hangi ilin sınırları içindedir?", prov[p]["name"], wrong, p0)
        v1 = mc_variant(f"{nm} Türkiye'nin hangi ilinde bulunur?", prov[p]["name"], rng.sample(wrong, 3), p1)
        items.append(make_item("gol", l, [v0, v1], "mc", {"lake": l, "province": p}))
    return items


def cat_birth(rng) -> list[dict]:
    rows = query(Q_HUMAN)
    by = defaultdict(list)
    meta = {}
    for r in rows:
        h = qid(r["h"])
        nm = clean_label(r.get("hLabel", ""), h)
        if not nm:
            continue
        by[h].append((r["b"], int(r["prec"]), int(r["nref"])))
        meta[h] = (nm, int(r["sl"]))
    cands = []
    namecount = defaultdict(int)
    for h in by:
        namecount[meta[h][0]] += 1
    for h, vals in by.items():
        # tek değer, en az yıl hassasiyeti, en az bir kaynak
        if len(vals) != 1:
            continue
        b, prec, nref = vals[0]
        if prec < 9 or nref < 1 or b.startswith("-") or namecount[meta[h][0]] > 1:
            continue
        cands.append((meta[h][1], h, meta[h][0], int(b[:4])))
    cands.sort(key=lambda x: (-x[0], x[1]))
    items, ctr = [], [0]
    for sl, h, nm, y in cands[:PER_CAT]:
        offs = rng.sample([o for o in range(-12, 13) if abs(o) >= 2], 3)
        # aynı konuma gelmeyen, birbirinden en az 2 yıl uzak yanlışlar
        while len({y + o for o in offs}) < 3 or min(abs(a - b) for a in offs for b in offs if a != b) < 2:
            offs = rng.sample([o for o in range(-12, 13) if abs(o) >= 2], 3)
        wrong = [str(y + o) for o in offs]
        p0, p1 = two_positions(rng, 4, ctr)
        v0 = mc_variant(f"{nm} hangi yıl doğmuştur?", str(y), wrong, p0)
        v1 = mc_variant(f"Aşağıdakilerden hangisi {nm} adlı kişinin doğum yılıdır?", str(y), rng.sample(wrong, 3), p1)
        items.append(make_item("dogum", h, [v0, v1], "mc", {"person": h, "year": y, "sitelinks": sl}))
    return items


CATEGORIES = {
    "nufus": "İl nüfusu karşılaştırma",
    "ilce": "İlçe hangi ilde",
    "plaka": "Plaka kodu",
    "rakim": "Şehir rakımı karşılaştırma",
    "gol": "Göl ve baraj gölü hangi ilde",
    "dogum": "Ünlülerin doğum yılı",
}


def build(seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    prov = load_provinces()
    pops = latest_population(query(Q_POP))
    items = []
    items += cat_population(prov, pops, rng)
    items += cat_district(prov, rng)
    items += cat_plate(prov, rng)
    items += cat_altitude(prov, rng)
    items += cat_lake(prov, rng)
    items += cat_birth(rng)
    return items


def main() -> None:
    items = build()
    out = ROOT / "data"
    pub = [i for i in items if i["split"] == "public"]
    held = [i for i in items if i["split"] == "heldout"]
    (out / "questions_public.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1), "utf-8")
    (out / "questions_heldout.json").write_text(json.dumps(held, ensure_ascii=False, indent=1), "utf-8")
    digest = hashlib.sha256((out / "questions_heldout.json").read_bytes()).hexdigest()
    (out / "heldout.sha256").write_text(digest + "  questions_heldout.json\n")
    from collections import Counter
    c = Counter((i["category"], i["split"]) for i in items)
    for cat in CATEGORIES:
        print(f"{cat:7s} public={c[(cat, 'public')]:4d} heldout={c[(cat, 'heldout')]:4d}")
    print("toplam", len(items))


if __name__ == "__main__":
    main()
