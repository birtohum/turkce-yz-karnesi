import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from karne import generate as g
from karne.grade import grade, parse_letter, parse_number
from karne.stats import bootstrap_ci, paired_diff_ci, significant

DATA = Path(__file__).resolve().parent.parent / "data"


# ------------------------------------------------------------ üretim
def test_mc_variant_places_correct():
    v = g.mc_variant("Soru?", "Doğru", ["x", "y", "z"], 2)
    assert v["choices"][2] == "Doğru" and v["answer"] == "C"
    assert "C) Doğru" in v["prompt"]


def test_mc_variant_rejects_duplicates():
    with pytest.raises(AssertionError):
        g.mc_variant("Soru?", "a", ["a", "b"], 0)


def test_two_positions_differ_and_balance():
    rng = random.Random(0)
    ctr = [0]
    firsts = []
    for _ in range(400):
        p0, p1 = g.two_positions(rng, 4, ctr)
        assert p0 != p1
        firsts.append(p0)
    assert Counter(firsts) == {0: 100, 1: 100, 2: 100, 3: 100}


def test_latest_population_picks_last_and_drops_conflicts():
    rows = [
        {"p": "x/Q1", "pop": "100", "date": "2018-12-31T00:00:00Z"},
        {"p": "x/Q1", "pop": "120", "date": "2021-12-31T00:00:00Z"},
        {"p": "x/Q2", "pop": "50", "date": "2021-12-31T00:00:00Z"},
        {"p": "x/Q2", "pop": "55", "date": "2021-12-31T00:00:00Z"},  # aynı tarihte çelişki
    ]
    out = g.latest_population(rows)
    assert out["Q1"]["pop"] == 120 and out["Q1"]["prev"] == ("2018-12-31", 100)
    assert "Q2" not in out


def test_clean_label():
    assert g.clean_label("Pehlivanköy (ilçe)", "Q1") == "Pehlivanköy"
    assert g.clean_label("Q123", "Q123") is None


def test_heldout_is_deterministic_and_about_20pct():
    ids = [f"c:{i}" for i in range(5000)]
    frac = sum(g.is_heldout(i) for i in ids) / len(ids)
    assert 0.17 < frac < 0.23
    assert [g.is_heldout(i) for i in ids[:50]] == [g.is_heldout(i) for i in ids[:50]]


@pytest.mark.skipif(not (DATA / "questions_public.json").exists(), reason="soru seti üretilmemiş")
def test_generated_set_is_consistent():
    items = []
    for s in ("public", "heldout"):
        p = DATA / f"questions_{s}.json"
        if p.exists():
            items += json.loads(p.read_text("utf-8"))
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    for it in items:
        assert len(it["variants"]) == 2
        assert it["split"] == ("heldout" if g.is_heldout(it["id"]) else "public")
        if it["kind"] == "mc":
            a, b = it["variants"]
            assert len(set(a["choices"])) == len(a["choices"])
            assert a["answer"] in "ABCD"[: len(a["choices"])]
        if it["category"] in ("ilce", "gol", "dogum") or it["id"].startswith("plaka:r"):
            a, b = it["variants"]
            # iki varyantta doğru cevap metni aynı, konumu farklı
            assert a["choices"]["ABCD".index(a["answer"])] == b["choices"]["ABCD".index(b["answer"])]
            assert a["answer"] != b["answer"]
    # nüfus: v1 ters soru, doğru cevap metni v0'dakinin tersi
    for it in items:
        if it["category"] == "nufus":
            a, b = it["variants"]
            ca = a["choices"]["AB".index(a["answer"])]
            cb = b["choices"]["AB".index(b["answer"])]
            assert ca != cb
    # cevap harfleri dengeli (konum yanlılığı ölçümü için)
    letters = Counter(it["variants"][0]["answer"] for it in items if it["kind"] == "mc" and len(it["variants"][0]["choices"]) == 4)
    assert max(letters.values()) - min(letters.values()) <= 0.1 * sum(letters.values())


# ------------------------------------------------------------ puanlama
@pytest.mark.parametrize("out,exp", [
    ("B", "B"), ("B)", "B"), ("b) Kocaeli", "B"), ("(C)", "C"), ("**D**", "D"),
    ("Cevap: A", "A"), ("Doğru cevap C şıkkı", "C"), ("Kocaeli", "B"),
    ("<think>hmm A</think>\nB", "B"), ("", None), ("E", None),
])
def test_parse_letter(out, exp):
    assert parse_letter(out, ["Samsun", "Kocaeli", "Batman", "Karaman"]) == exp


def test_parse_letter_ambiguous_text():
    assert parse_letter("Samsun ya da Kocaeli", ["Samsun", "Kocaeli", "Batman", "Karaman"]) is None


def test_parse_letter_two_choices():
    assert parse_letter("C", ["Kars", "Van"]) is None
    assert parse_letter("A", ["Kars", "Van"]) == "A"


@pytest.mark.parametrize("out,exp", [("34", "34"), ("06", "6"), ("Plaka kodu 18'dir.", "18"), ("yok", None), ("1234", None)])
def test_parse_number(out, exp):
    assert parse_number(out) == exp


def test_grade_statuses():
    v = {"choices": ["Kars", "Van"], "answer": "B"}
    assert grade(v, "mc", "B")["status"] == "correct"
    assert grade(v, "mc", "A")["status"] == "wrong"
    assert grade(v, "mc", "Bilmiyorum.")["status"] == "refusal"
    assert grade(v, "mc", "Hmm, zor bir soru")["status"] == "format"
    assert grade({"answer": "6"}, "exact", "06")["status"] == "correct"


# ------------------------------------------------------------ istatistik
def test_bootstrap_ci_matches_normal_approx():
    rng = np.random.default_rng(1)
    x = (rng.random(1000) < 0.7).astype(float)
    m, lo, hi = bootstrap_ci(x, b=5000)
    se = np.sqrt(m * (1 - m) / len(x))
    assert lo < m < hi
    assert abs((hi - lo) - 2 * 1.96 * se) < 0.01


def test_bootstrap_constant_has_zero_width():
    m, lo, hi = bootstrap_ci([1.0] * 50)
    assert m == lo == hi == 1.0


def test_paired_diff_detects_and_rejects():
    rng = np.random.default_rng(2)
    a = (rng.random(800) < 0.8).astype(float)
    c = (rng.random(800) < 0.5).astype(float)
    _, lo, hi = paired_diff_ci(a, c)
    assert significant(lo, hi)
    _, lo, hi = paired_diff_ci(a, a)
    assert not significant(lo, hi)


def test_stratified_macro_equal_weights():
    from karne.stats import stratified_macro
    m, lo, hi = stratified_macro({"a": np.ones(10), "b": np.zeros(1000)})
    assert m == 0.5 and lo == hi == 0.5
    rng = np.random.default_rng(3)
    m, lo, hi = stratified_macro({"a": rng.random(300), "b": rng.random(300)})
    assert lo < m < hi and hi - lo < 0.1
