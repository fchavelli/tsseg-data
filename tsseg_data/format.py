"""On-disk format of a tsseg-data dataset (format version 1.1).

1.0 validated 2026-10-18; 1.1 (same day) adds a sampling rate per config.

Layout of a built dataset ``build/<id>/``::

    README.md              dataset card (Hugging Face format, YAML header)
    croissant.json         Croissant 1.1 core + RAI 1.0 metadata
    tsseg.json             loader metadata (channels, labels, states, configs)
    index.parquet          one row per series
    data/<config>/part-00000.parquet, part-00001.parquet, ...
    <auxiliary>.parquet    optional dataset-specific tables

Rows of ``data/<config>/*.parquet`` (one row per series, or per chunk):

- ``series_id`` (string), ``chunk_idx`` (int32, 0 for unchunked series),
  ``chunk_start`` (int64, offset of the chunk in the series, in samples),
  ``length`` (int32, number of samples in this row);
- one ``list<float>`` column per channel (names in ``tsseg.json``);
- optional time column (``list<int64>`` or ``list<timestamp>``);
- one ``list<int>`` column per dense label column ``label_<name>``; ``-1``
  (``MISSING_LABEL``) only where no ground truth exists (not scored, outside the
  protocol); null / other / transition classes are ordinary states, listed in
  ``tsseg.json`` under ``null_states``;
- pure CPD datasets: ``cps_<annotator>`` (``list<int32>``, 0-based index of the
  first point of the new segment, global to the series, stored on chunk 0 only;
  null = the annotator did not see this series, empty = "no change") and
  ``cp_types_<annotator>`` (``list<string>``).

Several annotators of the same labels: ``label_<annotator>`` + ``label_consensus``
when the source defines one. Several label semantics (tracks): ``label_<track>``.
``tsseg.json`` keeps the two notions apart (``annotators`` vs ``tracks``).

Configs may differ in sampling rate (``DatasetSpec.config_rates``, e.g. a light
``default`` resampled from the native ``full``). Then every row length, chunk and
label column of a config is at that config's rate, ``tsseg.json`` gives
``configs.<cfg>.sampling_rate_hz``, and ``index.parquet`` has ``length_<cfg>`` and
``n_chunks_<cfg>`` for every config (``length`` and ``n_chunks`` are those of the
default config). Label changes (``n_changes_*``) must be the same in every config,
so the label segments of the source must fall on whole samples at every rate.
Change point columns require a single rate.

Series longer than ``CHUNK_SECONDS`` sampled at ``HIGH_FREQ_HZ`` or more are cut
into chunks of exactly ``CHUNK_SECONDS * fs`` samples (the last one shorter); the
reader concatenates them by ``(series_id, chunk_idx)``. Part files are rolled over
at about ``TARGET_FILE_BYTES`` on disk.
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

__all__ = [
    "FORMAT_VERSION",
    "MISSING_LABEL",
    "CHUNK_SECONDS",
    "HIGH_FREQ_HZ",
    "TARGET_FILE_BYTES",
    "RESERVED_COLUMNS",
    "DatasetSpec",
    "DatasetWriter",
    "chunk_length",
    "n_changes",
]

FORMAT_VERSION = "1.1"
MISSING_LABEL = -1
CHUNK_SECONDS = 3600
HIGH_FREQ_HZ = 10.0
TARGET_FILE_BYTES = 256 * 2**20
ROW_GROUP_BYTES = 32 * 2**20
RESERVED_COLUMNS = ("series_id", "chunk_idx", "chunk_start", "length")


def chunk_length(n: int, sampling_rate_hz: float | None) -> int | None:
    """Chunk length in samples, or ``None`` if the series is not chunked."""
    if not sampling_rate_hz or sampling_rate_hz < HIGH_FREQ_HZ:
        return None
    c = int(round(CHUNK_SECONDS * sampling_rate_hz))
    return c if n > c else None


def n_changes(y: np.ndarray) -> int:
    """Number of label changes ``y[i] != y[i-1]`` (CPs derived from dense labels)."""
    y = np.asarray(y)
    return int(np.count_nonzero(y[1:] != y[:-1])) if len(y) > 1 else 0


@dataclass
class DatasetSpec:
    """Column layout of a dataset (shared by all its configs).

    ``configs`` maps a config name to the channels it contains, in order; the
    first config is the default one. ``sampling_rate_hz`` is the native rate;
    ``config_rates`` overrides it for configs stored at another rate (their signals
    and labels are passed to :meth:`DatasetWriter.add_series` in ``resampled``).
    """

    id: str
    task: str  # "cpd" | "sd"
    channels: list[str]
    configs: dict[str, list[str]]
    sampling_rate_hz: float | None = None
    channel_type: pa.DataType = field(default_factory=pa.float32)
    time_column: tuple[str, pa.DataType] | None = None
    label_columns: dict[str, pa.DataType] = field(default_factory=dict)
    cp_annotators: list[str] = field(default_factory=list)
    meta_columns: dict[str, pa.DataType] = field(default_factory=dict)
    config_rates: dict[str, float] = field(default_factory=dict)

    def rate(self, config: str) -> float | None:
        """Sampling rate of a config (Hz), ``None`` for irregular series."""
        return self.config_rates.get(config, self.sampling_rate_hz)

    @property
    def multi_rate(self) -> bool:
        return len({self.rate(c) for c in self.configs}) > 1

    def __post_init__(self):
        assert self.task in ("cpd", "sd"), self.task
        names = list(self.channels) + list(self.label_columns)
        if self.time_column:
            names.append(self.time_column[0])
        for a in self.cp_annotators:
            names += [f"cps_{a}", f"cp_types_{a}"]
        assert len(set(names)) == len(names), "duplicated column names"
        assert not set(names) & set(RESERVED_COLUMNS), "reserved column name"
        for c in self.label_columns:
            assert c.startswith("label_"), c
        for cfg, chans in self.configs.items():
            assert set(chans) <= set(self.channels), cfg
        assert set(self.config_rates) <= set(self.configs), "config_rates: unknown config"
        if self.config_rates:
            assert self.sampling_rate_hz, "config_rates needs a native sampling_rate_hz"
        if self.multi_rate:
            assert not self.cp_annotators, "change point columns need a single rate"

    def row_schema(self, config: str) -> pa.Schema:
        fields = [
            pa.field("series_id", pa.string(), nullable=False),
            pa.field("chunk_idx", pa.int32(), nullable=False),
            pa.field("chunk_start", pa.int64(), nullable=False),
            pa.field("length", pa.int32(), nullable=False),
        ]
        if self.time_column:
            fields.append(pa.field(self.time_column[0], pa.list_(self.time_column[1])))
        fields += [pa.field(c, pa.list_(self.channel_type)) for c in self.configs[config]]
        fields += [pa.field(c, pa.list_(t)) for c, t in self.label_columns.items()]
        for a in self.cp_annotators:
            fields.append(pa.field(f"cps_{a}", pa.list_(pa.int32())))
            fields.append(pa.field(f"cp_types_{a}", pa.list_(pa.string())))
        meta = {"tsseg": json.dumps({"format_version": FORMAT_VERSION,
                                      "dataset": self.id, "config": config})}
        return pa.schema(fields, metadata=meta)

    def index_schema(self) -> pa.Schema:
        fields = [
            pa.field("series_id", pa.string(), nullable=False),
            pa.field("length", pa.int64(), nullable=False),
            pa.field("n_channels", pa.int32(), nullable=False),
            pa.field("n_chunks", pa.int32(), nullable=False),
            pa.field("split", pa.string()),
            pa.field("label_columns", pa.list_(pa.string())),
            pa.field("annotators", pa.list_(pa.string())),
        ]
        fields += [pa.field(f"n_changes_{c[len('label_'):]}", pa.int32())
                   for c in self.label_columns]
        fields += [pa.field(f"n_cps_{a}", pa.int32()) for a in self.cp_annotators]
        if self.multi_rate:
            for cfg in self.configs:
                fields += [pa.field(f"length_{cfg}", pa.int64()),
                           pa.field(f"n_chunks_{cfg}", pa.int32())]
        fields += [pa.field(f"files_{cfg}", pa.list_(pa.string())) for cfg in self.configs]
        fields += [pa.field(k, t) for k, t in self.meta_columns.items()]
        return pa.schema(fields)


def _list_column(arrays: list[np.ndarray], typ: pa.DataType) -> pa.Array:
    lengths = np.fromiter((len(a) for a in arrays), dtype=np.int64, count=len(arrays))
    offsets = np.concatenate([[0], np.cumsum(lengths)])
    if offsets[-1] >= 2**31:
        raise ValueError("row group too large for list<int32 offsets>")
    values = pa.array(np.concatenate(arrays) if arrays else np.array([]), type=typ)
    return pa.ListArray.from_arrays(pa.array(offsets, pa.int32()), values)


class _PartWriter:
    """Writes row groups of ~ROW_GROUP_BYTES (uncompressed) and rolls part files
    over before they exceed ~TARGET_FILE_BYTES on disk (compression ratio estimated
    from the row groups already written)."""

    def __init__(self, root: Path, config: str, schema: pa.Schema, float_cols: list[str]):
        self.root = root
        self.dir = root / "data" / config
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config, self.schema = config, schema
        self.float_cols = float_cols
        self.part, self.writer, self.path = -1, None, None
        self.groups_in_file = 0
        self.buf: list[dict] = []
        self.buf_bytes = 0
        self.raw_written, self.disk_written = 0, 0
        self.files: list[str] = []
        self.series_files: dict[str, list[str]] = {}

    def _open(self):
        self.part += 1
        self.path = self.dir / f"part-{self.part:05d}.parquet"
        self.writer = pq.ParquetWriter(
            self.path,
            self.schema,
            compression="zstd",
            compression_level=9,
            use_dictionary=[f.name for f in self.schema if f.name not in self.float_cols],
            use_byte_stream_split=[f"{c}.list.element" for c in self.float_cols],
            write_statistics=["series_id", "chunk_idx", "chunk_start", "length"],
        )
        self.groups_in_file = 0
        self.files.append(self.path.relative_to(self.root).as_posix())

    def _close_file(self):
        if self.writer is not None:
            self.writer.close()
            self.writer = None

    def add(self, row: dict, nbytes: int) -> None:
        self.buf.append(row)
        self.buf_bytes += nbytes
        if self.buf_bytes >= ROW_GROUP_BYTES:
            self.flush()

    def flush(self):
        if not self.buf:
            return
        ratio = self.disk_written / self.raw_written if self.raw_written else 1.0
        if self.writer is not None and self.groups_in_file and (
                self.path.stat().st_size + ratio * self.buf_bytes > TARGET_FILE_BYTES):
            self._close_file()
        if self.writer is None:
            self._open()
        cols = {}
        for f in self.schema:
            vals = [r[f.name] for r in self.buf]
            if pa.types.is_list(f.type) and all(isinstance(v, np.ndarray) for v in vals):
                cols[f.name] = _list_column(vals, f.type.value_type)
            else:
                cols[f.name] = pa.array(vals, type=f.type)
        before = self.path.stat().st_size
        self.writer.write_table(pa.table(cols, schema=self.schema))
        self.groups_in_file += 1
        self.raw_written += self.buf_bytes
        self.disk_written += max(self.path.stat().st_size - before, 0)
        for r in self.buf:
            fl = self.series_files.setdefault(r["series_id"], [])
            if self.files[-1] not in fl:
                fl.append(self.files[-1])
        self.buf, self.buf_bytes = [], 0

    def close(self):
        self.flush()
        self._close_file()


class DatasetWriter:
    """Write the series of one dataset in every config, then ``index.parquet``.

    Use as a context manager; call :meth:`add_series` once per series.
    """

    def __init__(self, out_dir: Path, spec: DatasetSpec):
        self.root, self.spec = Path(out_dir), spec
        if (self.root / "data").exists():  # stale parts of a previous build
            shutil.rmtree(self.root / "data")
        self.root.mkdir(parents=True, exist_ok=True)
        float_cols = list(spec.channels)
        self.parts = {
            cfg: _PartWriter(self.root, cfg, spec.row_schema(cfg),
                             [c for c in float_cols if c in spec.configs[cfg]])
            for cfg in spec.configs
        }
        self.index_rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.close()

    def add_series(
        self,
        series_id: str,
        signals: dict[str, np.ndarray],
        *,
        labels: dict[str, np.ndarray] | None = None,
        time: np.ndarray | None = None,
        cps: dict[str, tuple[np.ndarray, list[str]] | None] | None = None,
        split: str | None = None,
        annotators: list[str] | None = None,
        meta: dict | None = None,
        resampled: dict[str, dict] | None = None,
    ) -> None:
        """Add one series.

        ``signals``, ``labels`` and ``time`` are at the native rate. Each config of
        ``spec.config_rates`` whose rate differs from the native one needs
        ``resampled[cfg] = {"signals": {channel: array}, "labels": {col: array}}``
        (``"time"`` too if the dataset has a time column), with the channels of
        that config.
        """
        spec = self.spec
        labels = labels or {}
        cps = cps or {}
        resampled = resampled or {}
        assert list(signals) == spec.channels, "signals must follow spec.channels"
        assert set(labels) == set(spec.label_columns), set(labels) ^ set(spec.label_columns)
        assert set(cps) <= set(spec.cp_annotators)
        n = len(next(iter(signals.values())))
        for k, v in {**signals, **labels}.items():
            assert len(v) == n, (series_id, k, len(v), n)
        if time is not None:
            assert len(time) == n
        for a, val in cps.items():
            if val is not None:
                c = np.asarray(val[0])
                assert len(c) == len(val[1]), (series_id, a)
                assert np.all((c > 0) & (c < n)), (series_id, a)
                assert np.all(np.diff(c) > 0), (series_id, a, "cps must be sorted, unique")

        # data of each config: (signals, labels, time, length)
        native = (signals, labels, time, n)
        per_cfg = {}
        for cfg, chans in spec.configs.items():
            if spec.rate(cfg) == spec.sampling_rate_hz:
                assert cfg not in resampled, (series_id, cfg, "config at native rate")
                per_cfg[cfg] = native
                continue
            rs = resampled[cfg]
            sig, lab, tim = rs["signals"], rs["labels"], rs.get("time")
            assert set(sig) == set(chans), (series_id, cfg, set(sig) ^ set(chans))
            assert set(lab) == set(spec.label_columns), (series_id, cfg)
            assert (tim is None) == (spec.time_column is None), (series_id, cfg)
            m = len(next(iter(sig.values())))
            for k, v in {**sig, **lab}.items():
                assert len(v) == m, (series_id, cfg, k, len(v), m)
            assert abs(m / spec.rate(cfg) - n / spec.sampling_rate_hz) * spec.rate(cfg) < 1, (
                series_id, cfg, "duration differs from the native series")
            for c in spec.label_columns:
                assert n_changes(lab[c]) == n_changes(labels[c]), (
                    series_id, cfg, c, "label changes differ from the native labels")
            per_cfg[cfg] = (sig, lab, tim, m)

        n_chunks = {}
        for cfg, chans in spec.configs.items():
            sig, lab_all, tim, m = per_cfg[cfg]
            clen = chunk_length(m, spec.rate(cfg))
            bounds = [(0, m)] if clen is None else [
                (s, min(s + clen, m)) for s in range(0, m, clen)
            ]
            n_chunks[cfg] = (m, len(bounds))
            for k, (s, e) in enumerate(bounds):
                row = {"series_id": series_id, "chunk_idx": k, "chunk_start": s,
                       "length": e - s}
                if spec.time_column:
                    row[spec.time_column[0]] = np.asarray(tim[s:e])
                nbytes = 0
                for ch in chans:
                    arr = np.ascontiguousarray(sig[ch][s:e]).astype(
                        spec.channel_type.to_pandas_dtype(), copy=False)
                    row[ch] = arr
                    nbytes += arr.nbytes
                for c, t in spec.label_columns.items():
                    arr = np.ascontiguousarray(lab_all[c][s:e]).astype(
                        t.to_pandas_dtype(), copy=False)
                    row[c] = arr
                    nbytes += arr.nbytes
                for a in spec.cp_annotators:
                    val = cps.get(a) if k == 0 else None
                    row[f"cps_{a}"] = None if val is None else [int(x) for x in val[0]]
                    row[f"cp_types_{a}"] = None if val is None else list(val[1])
                self.parts[cfg].add(row, nbytes)

        default = next(iter(spec.configs))
        irow = {
            "series_id": series_id,
            "length": n_chunks[default][0],
            "n_channels": len(spec.channels),
            "n_chunks": n_chunks[default][1],
            "split": split,
            "label_columns": list(spec.label_columns) or None,
            "annotators": annotators,
        }
        for c in spec.label_columns:
            irow[f"n_changes_{c[len('label_'):]}"] = n_changes(labels[c])
        for a in spec.cp_annotators:
            val = cps.get(a)
            irow[f"n_cps_{a}"] = None if val is None else len(val[0])
        if spec.multi_rate:
            for cfg, (m, k) in n_chunks.items():
                irow[f"length_{cfg}"], irow[f"n_chunks_{cfg}"] = m, k
        for k in spec.meta_columns:
            irow[k] = (meta or {}).get(k)
        self.index_rows.append(irow)

    def close(self) -> None:
        for p in self.parts.values():
            p.close()
        for irow in self.index_rows:
            for cfg, p in self.parts.items():
                irow[f"files_{cfg}"] = p.series_files[irow["series_id"]]
        schema = self.spec.index_schema()
        table = pa.Table.from_pylist(self.index_rows, schema=schema)
        pq.write_table(table, self.root / "index.parquet", compression="zstd")

    def summary(self) -> dict:
        out = {}
        for cfg, p in self.parts.items():
            sizes = [(self.root / f).stat().st_size for f in p.files]
            out[cfg] = {"files": p.files, "bytes": int(sum(sizes)),
                        "max_file_bytes": int(max(sizes)) if sizes else 0}
        return out


def human_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    k = min(int(math.log(n, 1024)), 4)
    return f"{n / 1024**k:.1f} {['B', 'KiB', 'MiB', 'GiB', 'TiB'][k]}"
