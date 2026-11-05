"""Bootstrap güven aralıkları ve eşleştirilmiş fark testi.

Birim soru (item)'dur: bir sorunun iki varyantının ortalaması o sorunun puanıdır.
Böylece aynı sorunun iki ifadesi bağımsız gözlem gibi sayılmaz.
"""
from __future__ import annotations

import numpy as np

B = 10_000


def bootstrap_ci(scores, b: int = B, seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """Ortalama ve yüzdelik bootstrap %95 GA."""
    x = np.asarray(scores, dtype=float)
    if x.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(b, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(x.mean()), float(lo), float(hi)


def paired_diff_ci(a, c, b: int = B, seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """Aynı sorular üzerinde iki modelin farkı (a - c) için bootstrap GA."""
    a = np.asarray(a, dtype=float)
    c = np.asarray(c, dtype=float)
    assert a.shape == c.shape
    return bootstrap_ci(a - c, b=b, seed=seed, alpha=alpha)


def significant(lo: float, hi: float) -> bool:
    return lo > 0 or hi < 0


def stratified_macro(groups: dict[str, "np.ndarray"], b: int = B, seed: int = 0,
                     alpha: float = 0.05) -> tuple[float, float, float]:
    """Kategorilerin eşit ağırlıklı ortalaması; her kategori kendi içinde yeniden örneklenir.

    groups: kategori -> soru puanları. Fark testi için puanlar fark dizisi olarak verilebilir.
    """
    rng = np.random.default_rng(seed)
    arrs = [np.asarray(v, dtype=float) for v in groups.values() if len(v)]
    point = float(np.mean([a.mean() for a in arrs]))
    boots = np.zeros(b)
    for a in arrs:
        idx = rng.integers(0, a.size, size=(b, a.size))
        boots += a[idx].mean(axis=1)
    boots /= len(arrs)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return point, float(lo), float(hi)
