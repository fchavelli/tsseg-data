"""Label utilities: run lengths, change points, inter-annotator agreement.

Pure numpy, so builders and ``scripts/validate.py`` do not depend on tsseg or
scikit-learn. Conventions follow the format: ``-1`` = no ground truth; change
points are 0-based indices of the first point of a new segment, without 0 and n.
"""

from __future__ import annotations

import itertools

import numpy as np

__all__ = [
    "runs",
    "change_points",
    "cohen_kappa",
    "adjusted_rand_index",
    "match_count",
    "f1_cps",
    "tcpd_f1",
    "pairwise",
]


def runs(y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run-length encoding: (values, starts, lengths)."""
    y = np.asarray(y)
    if len(y) == 0:
        return y, np.array([], int), np.array([], int)
    starts = np.r_[0, np.flatnonzero(y[1:] != y[:-1]) + 1]
    return y[starts], starts, np.diff(np.r_[starts, len(y)])


def change_points(y: np.ndarray) -> np.ndarray:
    """Change points of dense labels (indices i with y[i] != y[i-1])."""
    y = np.asarray(y)
    return np.flatnonzero(y[1:] != y[:-1]) + 1


def cohen_kappa(a: np.ndarray, b: np.ndarray, missing: int = -1) -> float:
    """Cohen's kappa on the points labelled by both (``missing`` excluded)."""
    a, b = np.asarray(a), np.asarray(b)
    keep = (a != missing) & (b != missing)
    a, b = a[keep], b[keep]
    if len(a) == 0:
        return float("nan")
    cats = np.union1d(a, b)
    ia, ib = np.searchsorted(cats, a), np.searchsorted(cats, b)
    m = np.zeros((len(cats), len(cats)))
    np.add.at(m, (ia, ib), 1)
    m /= m.sum()
    po = np.trace(m)
    pe = float(m.sum(1) @ m.sum(0))
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def adjusted_rand_index(a: np.ndarray, b: np.ndarray, missing: int = -1) -> float:
    a, b = np.asarray(a), np.asarray(b)
    keep = (a != missing) & (b != missing)
    a, b = a[keep], b[keep]
    n = len(a)
    if n < 2:
        return float("nan")
    _, ia = np.unique(a, return_inverse=True)
    _, ib = np.unique(b, return_inverse=True)
    m = np.zeros((ia.max() + 1, ib.max() + 1))
    np.add.at(m, (ia, ib), 1)

    def c2(x):
        return (x * (x - 1) / 2).sum()

    s, sa, sb = c2(m), c2(m.sum(1)), c2(m.sum(0))
    exp = sa * sb / (n * (n - 1) / 2)
    mx = (sa + sb) / 2
    return float((s - exp) / (mx - exp)) if mx != exp else 1.0


def match_count(true: np.ndarray, pred: np.ndarray, margin: int) -> int:
    """Greedy one-to-one matches within ``margin`` (TCPD convention)."""
    used: set[int] = set()
    tp = 0
    for t in true:
        cand = [p for p in pred if abs(p - t) <= margin and p not in used]
        if cand:
            used.add(min(cand, key=lambda p: abs(p - t)))
            tp += 1
    return tp


def f1_cps(true: np.ndarray, pred: np.ndarray, margin: int) -> float:
    """F1 between two CP sets; 0 is added to both, as in TCPD."""
    true, pred = np.union1d(true, [0]), np.union1d(pred, [0])
    tp = match_count(true, pred, margin)
    p, r = tp / len(pred), tp / len(true)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def tcpd_f1(annots: list[np.ndarray], pred: np.ndarray, margin: int = 5) -> float:
    """van den Burg & Williams (2020) F1: precision against the union of the
    annotations, recall averaged over annotators; 0 added to every set."""
    annots = [np.union1d(a, [0]) for a in annots]
    pred = np.union1d(pred, [0])
    union = np.unique(np.concatenate(annots))
    p = match_count(union, pred, margin) / len(pred)
    r = float(np.mean([match_count(a, pred, margin) / len(a) for a in annots]))
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def pairwise(items: dict, fn) -> list[float]:
    """``fn(a, b)`` for every unordered pair of ``items`` values."""
    return [fn(items[x], items[y]) for x, y in itertools.combinations(sorted(items), 2)]
