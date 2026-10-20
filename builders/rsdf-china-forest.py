"""Build all native RSDF surface-reflectance trajectories and dated event references."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from tsseg_data.batch import ChangePointStatistics, finish
from tsseg_data.build import parse_args
from tsseg_data.format import DatasetSpec, DatasetWriter
from tsseg_data.rsdf import CHANNELS, annotations, reference, signal
from tsseg_data.sources import fetch, sha256

ID = "rsdf-china-forest"
SOURCE = "https://doi.org/10.6084/m9.figshare.33313359.v1"
PINS = Path(__file__).parent / "checksums/rsdf-china-forest.json"
RESERVE = 18 * 2**30


def main():
    args = parse_args(
        ID, extra=lambda p: p.add_argument("--pilot", action="store_true")
    )
    pins = json.loads(PINS.read_text())
    raw = args.raw_dir / ID
    raw.mkdir(parents=True, exist_ok=True)
    # Full source plus conservative native signal output, before empirical pilot.
    projected = sum(p["bytes"] for p in pins["files"]) + 10 * 2**30
    if shutil.disk_usage(raw).free - projected < RESERVE:
        raise RuntimeError("Complete source/output gate breaches18GiB")
    local = {
        p["name"]: fetch(p["url"], p["name"], p["sha256"], args.raw_dir, ID)
        for p in pins["files"]
    }
    labels = annotations(local["RSDF.csv"])
    assert len(labels) == 12991
    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=None,
        time_column=("date", pa.timestamp("ns")),
        cp_annotators=["reference"],
        meta_columns={
            "longitude": pa.float64(),
            "latitude": pa.float64(),
            "annotation_longitude": pa.float64(),
            "annotation_latitude": pa.float64(),
            "source_member": pa.string(),
            "source_sha256": pa.string(),
            "source_crc32": pa.uint32(),
            "n_source_annotation_rows": pa.int32(),
            "reference_issues": pa.list_(pa.string()),
            "n_invalid_qa": pa.int32(),
            "duplicate_dates": pa.int32(),
            "native_date_reversals": pa.int32(),
        },
    )
    stats = ChangePointStatistics()
    events = []
    details = []
    source_order_rows = []
    native_bytes = 0
    sample_count = 0
    valid_qa = 0
    with zipfile.ZipFile(local["RSDF_SurfaceReflectance.zip"]) as archive:
        members = sorted(
            [i for i in archive.infolist() if i.filename.endswith(".csv")],
            key=lambda i: i.filename,
        )
        assert len(members) == 12991 and {
            Path(i.filename).stem[1:] for i in members
        } == set(labels)
        if args.pilot:
            wanted = {
                min(members, key=lambda i: i.file_size).filename,
                max(members, key=lambda i: i.file_size).filename,
            }
            for kind in ["fire", "harvest", "other", "forestation"]:
                pid = next(
                    pid
                    for pid, rows in labels.items()
                    if any(row["Type"].strip() == kind for row in rows)
                )
                wanted.add(
                    next(
                        i.filename
                        for i in members
                        if Path(i.filename).stem == "P" + pid
                    )
                )
            pid = next(
                pid
                for pid, rows in labels.items()
                if any(not row["Year"] for row in rows)
                and any(row["Year"] for row in rows)
            )
            wanted.add(
                next(i.filename for i in members if Path(i.filename).stem == "P" + pid)
            )
            members = [i for i in members if i.filename in wanted]
        with DatasetWriter(args.out_dir, spec) as writer:
            for item in members:
                pid = Path(item.filename).stem[1:]
                data = archive.read(item)
                native_bytes += len(data)
                x, dates, lon, lat, order, reversals = signal(data, pid)
                source_order_rows.append({"series_id": pid, "source_row_index": order})
                cps, rows, issues = reference(labels[pid], dates)
                events.extend(rows)
                n = len(x)
                sample_count += n
                valid_qa += int(x[:, -1].sum())
                duplicate = int(np.count_nonzero(dates[1:] == dates[:-1]))
                writer.add_series(
                    pid,
                    {c: x[:, i] for i, c in enumerate(CHANNELS)},
                    time=dates,
                    cps={"reference": cps},
                    annotators=["reference"] if cps is not None else [],
                    meta={
                        "longitude": lon,
                        "latitude": lat,
                        "annotation_longitude": float(labels[pid][0]["longitude"]),
                        "annotation_latitude": float(labels[pid][0]["latitude"]),
                        "source_member": item.filename,
                        "source_sha256": hashlib.sha256(data).hexdigest(),
                        "source_crc32": item.CRC,
                        "n_source_annotation_rows": len(labels[pid]),
                        "reference_issues": issues,
                        "n_invalid_qa": int(n - x[:, -1].sum()),
                        "duplicate_dates": duplicate,
                        "native_date_reversals": reversals,
                    },
                )
                stats.add(pid, n, {"reference": None if cps is None else cps[0]})
                details.append(
                    {
                        "series_id": pid,
                        "length": n,
                        "issues": issues,
                        "duplicate_dates": duplicate,
                        "native_date_reversals": reversals,
                    }
                )
                if shutil.disk_usage(raw).free < RESERVE:
                    raise RuntimeError("18GiB reserve breached")
    pq.write_table(
        pa.Table.from_pylist(source_order_rows),
        args.out_dir / "source-order.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(events),
        args.out_dir / "source-annotations.parquet",
        compression="zstd",
    )
    if not args.pilot:
        assert len(stats.rows) == 12991 and len(events) == 13765
    finish(
        args,
        spec,
        writer,
        stats,
        title="RSDF China: complete native Landsat reflectance and dated forest-change reference",
        source=SOURCE,
        sha256=sha256(PINS),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence="https://api.figshare.com/v2/articles/33313359/versions/1",
        license_verified_date="2026-10-20",
        description="All12,991 released RSDF forest sample trajectories across China, six native reflectance bands plus Sensor and QA fields, irregular original acquisition dates and every original dated change/stability annotation. No imagery or diagnostic PDF figures included.",
        collection="Landsat5/7/8/9 Collection2 Level2 observations from1986–2025 for stratified forest sample points. This is the complete provider-published CSV view, already subject to the source processing pipeline; it is not a reconstruction of raw Landsat scenes. Source CSVs retain both QA1 valid and QA0 invalid observations. All six reflectance columns, acquisition sensor and QA flag remain unchanged after float32 conversion; sample coordinates retained as geospatial context.",
        annotation="Primary paper documents hierarchical visual interpretation using satellite time series, higher-resolution imagery and forest records, with consensus quality review. Released Year/DOY/Type specify dated events; null triples claim stable forest. No individual rater tracks are released. Retain every source row and confidence string in source-annotations.parquet. A PID with both stable and event claims is explicitly conflicted: default cps_reference=null rather than silently treating stable as no change. Events outside the interior observation window or distinct events mapping to one boundary likewise make that entire default reference unscored. Otherwise map each dated event to the first original observation on/after it, preserve raw dates and neighboring acquisitions, and deduplicate identical event/date/type records only in the CP list. This is a deterministic observation-grid mapping of calendar-day reference dates, not a claim of exact image-sample onset. Stable-only points have an empty CP list; no state taxonomy or recurrence is invented.",
        conversion="Verify primary Figshare version1 file byte counts/provider MD5 and pin SHA256 of the reflectance ZIP and annotation CSV. Read CSV members directly with ZIP CRC checking, never extract files or execute source code. Require exact14-column schema, one PID/coordinate per trajectory, valid calendar dates, Sensor5/7/8/9 and QA0/1. Keep every row, including invalid QA0, duplicate acquisition dates and native reflectance codes. Cast signal values once to float32; no resampling, new cloud mask, filtering, scaling, offset correction, interpolation, spectral index construction or QA-based row removal. Native physical reflectance scale/offset is not established by released CSV metadata, so no calibration is guessed. Stable-sort observations by their original calendar date, preserving relative order of duplicate dates; retain source_row_index for every observation in source-order.parquet, so the original native CSV order is exactly recoverable. Only CP indices are projected into this sorted observation order; original event dates are unchanged. Audit native date reversals and duplicate dates for every PID; global sampling rate null.",
        limitations="Source pipeline already includes quality masking and adaptive time-series filtering according to the paper, but released CSVs still contain QA0 rows: preserve them and provide the flag rather than treating invalid values as reliable reflectance. Reflectance codes may include invalid placeholders; no numerical sentinel interpretation is invented. Reference dates have calendar-day resolution and lie in irregular observation gaps; evaluate timing in elapsed days, not a fixed count of samples. Stable/event contradictions, unrepresentable boundary events and collisions are explicitly unscored in the default reference while original claims remain available. Multiple events do not establish recurrent latent states. Confidence is source consensus support, not an independent probability or new annotator. Paper-wide agreement is not recomputed from unreleased individual ratings.",
        biases="Stratified forest-only30m sample points across China; unequal spatial density, cloudy acquisition gaps, mixed pixels, sensor changes and nearby-site correlation. Source selection excludes nonforest points and low-confidence samples. Stable points dominate, so retain them when assessing false positives. Do not treat nearby samples or invalid QA0 observations as independent clean evidence.",
        personal="Public forest-pixel coordinates and satellite measurements; no human participant or private household attributes. No high-resolution source imagery is rehosted.",
        citation="Shang R., Xu S., Yang Z., et al. (2026). A reference sample dataset of stable, disturbed and forestated forests over China from1986 to near present. Earth System Science Data Discussions, preprint doi:10.5194/essd-2026-705. Dataset doi:10.6084/m9.figshare.33313359.v1.",
        creators=["Rong Shang", "Shengwei Xu", "Ziyi Yang", "Jing M. Chen"],
        date_published="2026-08-31",
        info={
            "source_files": pins,
            "reference_doi": "https://doi.org/10.5194/essd-2026-705",
            "annotators": [],
            "cp_reference": "Released consensus event dates; reference slot is not an individual rater",
            "source_reported_raters": 15,
            "auxiliary": {
                "source-order.parquet": "Per-series list source_row_index maps every chronological observation back to its zero-based original native CSV row; exact inverse reconstructs source order.",
                "source-annotations.parquet": "Every original RSDF annotation row, including empty stable claims, literal certainty strings, original event dates and mapped observation boundaries; default conflicts remain unscored.",
            },
            "source_channel_names": [
                "Blue",
                "Green",
                "Red",
                "NIR",
                "SWIR1",
                "SWIR2",
                "Sensor",
                "QA",
            ],
            "channel_units": {
                c: "native published reflectance code; scale/offset unasserted"
                if c not in ["qa", "sensor"]
                else "source validity flag1/0"
                if c == "qa"
                else "Landsat sensor identifier5/7/8/9"
                for c in CHANNELS
            },
            "native_csv_bytes": native_bytes,
            "valid_qa_samples": valid_qa,
            "invalid_qa_samples": sample_count - valid_qa,
            "series_details": details,
        },
    )
    print(
        {
            "series": len(stats.rows),
            "samples": sample_count,
            "native_csv_bytes": native_bytes,
            "issues": sum(bool(row["issues"]) for row in details),
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
