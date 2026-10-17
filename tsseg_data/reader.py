"""Minimal reader of a built dataset (reference for the tsseg loader).

Chunks of a series are concatenated back by ``(series_id, chunk_idx)``. Configs may
have different sampling rates (``tsseg.json`` ``configs.<cfg>.sampling_rate_hz``);
lengths and labels are then those of the config read.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

__all__ = ["load_info", "read_index", "load_series", "iter_series"]


def load_info(root: Path) -> dict:
    return json.loads((Path(root) / "tsseg.json").read_text())


def read_index(root: Path):
    return pq.read_table(Path(root) / "index.parquet")


def _rows(root: Path, files: list[str], series_id: str, columns=None):
    tables = []
    for f in files:
        pf = pq.ParquetFile(Path(root) / f)
        for i in range(pf.num_row_groups):
            st = pf.metadata.row_group(i).column(0).statistics
            if st is not None and st.has_min_max and not (st.min <= series_id <= st.max):
                continue
            t = pf.read_row_group(i, columns=columns)
            t = t.filter(pc.equal(t["series_id"], series_id))
            if t.num_rows:
                tables.append(t)
    return tables


def _to_numpy_rows(t) -> list[dict]:
    """Rows of a table with list columns as numpy arrays (no Python lists)."""
    cols = {}
    for name in t.column_names:
        arr = t[name].combine_chunks()
        if pa.types.is_list(arr.type):
            off = arr.offsets.to_numpy()
            vals = arr.values
            vals = (vals.to_numpy(zero_copy_only=False)
                    if not pa.types.is_string(vals.type) else np.array(vals.to_pylist(), dtype=object))
            nulls = arr.is_null().to_numpy(zero_copy_only=False)
            cols[name] = [None if nulls[i] else vals[off[i]:off[i + 1]] for i in range(len(arr))]
        else:
            cols[name] = arr.to_pylist()
    return [{k: v[i] for k, v in cols.items()} for i in range(t.num_rows)]


def load_series(
    root: Path,
    series_id: str,
    config: str | None = None,
    channels: list[str] | None = None,
) -> dict:
    """Load one series: ``X`` (n, c) float64, dense labels, time, change points, at
    the sampling rate of ``config`` (default config if ``None``)."""
    root = Path(root)
    info = load_info(root)
    config = config or info["default_config"]
    idx = read_index(root)
    row = idx.filter(pc.equal(idx["series_id"], series_id))
    if row.num_rows != 1:
        raise KeyError(series_id)
    files = row[f"files_{config}"][0].as_py()
    chans = channels or info["configs"][config]["channels"]
    tables = _rows(root, files, series_id)
    rows = sorted((r for t in tables for r in _to_numpy_rows(t)), key=lambda r: r["chunk_idx"])
    nc_col = f"n_chunks_{config}" if f"n_chunks_{config}" in row.column_names else "n_chunks"
    n_chunks = row[nc_col][0].as_py()
    if [r["chunk_idx"] for r in rows] != list(range(n_chunks)):
        raise ValueError(f"{series_id}: chunks {[r['chunk_idx'] for r in rows]}")
    pos = 0
    for r in rows:
        if r["chunk_start"] != pos:
            raise ValueError(f"{series_id}: chunk {r['chunk_idx']} starts at "
                             f"{r['chunk_start']}, expected {pos}")
        pos += r["length"]
    rate = info["configs"][config].get("sampling_rate_hz", info.get("sampling_rate_hz"))
    out = {"series_id": series_id, "config": config, "channels": chans, "length": pos,
           "sampling_rate_hz": rate}
    out["X"] = np.column_stack(
        [np.concatenate([np.asarray(r[c], dtype=np.float64) for r in rows]) for c in chans]
    )
    out["labels"] = {
        c: np.concatenate([np.asarray(r[c], dtype=np.int64) for r in rows])
        for c in info.get("label_columns", [])
    }
    tcol = info.get("time_column")
    if tcol:
        out["time"] = np.concatenate([np.asarray(r[tcol]) for r in rows])
    out["cps"] = {
        a: (None if rows[0][f"cps_{a}"] is None else
            (np.asarray(rows[0][f"cps_{a}"], dtype=np.int64),
             list(rows[0][f"cp_types_{a}"])))
        for a in info.get("cp_annotators", [])
    }
    return out


def iter_series(root: Path, config: str | None = None):
    idx = read_index(Path(root))
    for sid in idx["series_id"].to_pylist():
        yield load_series(root, sid, config)
