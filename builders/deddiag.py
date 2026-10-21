"""Preserve all native sparse DEDDIAG observations and overlapping source events."""

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

from tsseg_data.batch import Statistics, finish
from tsseg_data.build import parse_args
from tsseg_data.deddiag import (
    RESERVE,
    acquire,
    event_runs,
    label_values,
    metadata,
    provenance_runs,
    read_measurements,
    storage_gate,
)
from tsseg_data.format import DatasetSpec, DatasetWriter
from tsseg_data.sources import sha256

ID = "deddiag"
SOURCE = "https://doi.org/10.6084/m9.figshare.13615073.v1"
PIN = Path(__file__).parent / "checksums/deddiag.json"


def main():
    def extra(parser):
        parser.add_argument("--pilot", action="store_true")
        parser.add_argument("--houses", type=int, nargs="+")

    args = parse_args(ID, extra=extra)
    raw = args.raw_dir / ID
    raw.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pins = json.loads(PIN.read_text())
    selected = set(args.houses or ([1, 8] if args.pilot else range(15)))
    assert selected <= set(range(15)) and (args.pilot or selected == set(range(15)))
    if args.pilot:
        if shutil.disk_usage(raw).free - 8 * 2**30 < RESERVE:
            raise RuntimeError("Pilot output/scratch allowance unavailable")
    else:
        print("Full corpus storage gate", storage_gate(raw, pins), flush=True)
    archives = {}
    for pin in pins["files"]:
        if int(pin["name"][6:8]) in selected:
            archives[pin["name"]] = acquire(raw, pin)
    audit_path = raw / "metadata-audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
    else:
        assert not args.pilot
        audit = {}
        for pin in pins["files"]:
            with zipfile.ZipFile(archives[pin["name"]]) as z:
                texts = {
                    name: z.read(name).decode("utf-8")
                    for name in pin["metadata_member_sha256"]
                }
            audit[pin["name"]] = {"selected_text": texts}
    # Complete metadata vocabulary is fixed from all15 primary house archives.
    for pin in pins["files"]:
        for member, digest in pin["metadata_member_sha256"].items():
            assert (
                hashlib.sha256(
                    audit[pin["name"]]["selected_text"][member].encode()
                ).hexdigest()
                == digest
            )
    items, definitions, annotations = metadata(audit)
    for archive_name, path in archives.items():
        house = int(archive_name[6:8])
        expected = {
            f"house_{house:02d}/item_{int(row['item_id']):04d}_data.tsv.gz"
            for row in items
            if int(row["house"]) == house
        }
        with zipfile.ZipFile(path) as archive:
            assert {
                name for name in archive.namelist() if name.endswith("_data.tsv.gz")
            } == expected
    rows_by_item = {
        int(item["item_id"]): [
            r for r in annotations if r["item_id"] == item["item_id"]
        ]
        for item in items
    }
    runs_by_item = {item: event_runs(rows) for item, rows in rows_by_item.items()}
    sets = sorted({labels for runs in runs_by_item.values() for _, _, labels in runs})
    codebook = {labels: index + 1 for index, labels in enumerate(sets)}
    label_names = {int(r["id"]): r["text"] for r in definitions}
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["power_w"],
        configs={"default": ["power_w"]},
        sampling_rate_hz=None,
        channel_type=pa.float64(),
        time_column=("time_ns", pa.int64()),
        label_columns={"label_activity": pa.int32()},
        meta_columns={
            "house_id": pa.int16(),
            "item_id": pa.int32(),
            "item_name": pa.string(),
            "category": pa.string(),
            "source_annotated": pa.bool_(),
            "source_gap_count": pa.int32(),
            "source_order_runs": pa.int64(),
        },
    )
    source_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("sorted_start", pa.int64()),
            ("source_start", pa.int64()),
            ("length", pa.int64()),
        ]
    )
    stats, details, mapped_rows, gap_rows = Statistics(), [], [], []
    subset = [r for r in items if int(r["house"]) in selected]
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "source-order.parquet", source_schema, compression="zstd"
        ) as order_writer,
    ):
        for item in sorted(subset, key=lambda r: (int(r["house"]), int(r["item_id"]))):
            house, item_id = int(item["house"]), int(item["item_id"])
            sid = f"house_{house:02d}_item_{item_id:04d}"
            if shutil.disk_usage(raw).free - 4 * 2**30 < RESERVE:
                raise RuntimeError(
                    "18 GiB reserve plus4GiB scratch/write allowance unavailable"
                )
            member = f"house_{house:02d}/item_{item_id:04d}_data.tsv.gz"
            with zipfile.ZipFile(archives[f"house_{house:02d}.zip"]) as z:
                for name, text in audit[f"house_{house:02d}.zip"][
                    "selected_text"
                ].items():
                    assert z.read(name).decode("utf-8") == text
                times, values, order, chronology = read_measurements(
                    z, member, raw / "work"
                )
            assert len(times) < 2**31 and len(times) == len(values) == len(order)
            # Scratch is already charged to current free space. Bound the new
            # Parquet write by all native column bytes plus128MiB overhead.
            if shutil.disk_usage(raw).free - len(times) * 20 - 128 * 2**20 < RESERVE:
                raise RuntimeError("Native trace write would threaten18GiB reserve")
            labels, ties = label_values(times, runs_by_item[item_id], codebook)
            run_count, buffer = 0, []
            for run in provenance_runs(sid, order):
                buffer.append(run)
                run_count += 1
                if len(buffer) == 65536:
                    order_writer.write_table(
                        pa.Table.from_pylist(buffer, schema=source_schema)
                    )
                    buffer = []
            if buffer:
                order_writer.write_table(
                    pa.Table.from_pylist(buffer, schema=source_schema)
                )
            gaps = 0
            for start in range(1, len(times), 262144):
                end = min(len(times), start + 262144)
                positions = (
                    np.flatnonzero(
                        times[start:end] - times[start - 1 : end - 1] > 3605 * 10**9
                    )
                    + start
                )
                for position in positions:
                    gap_rows.append(
                        {
                            "series_id": sid,
                            "before_index": int(position - 1),
                            "after_index": int(position),
                            "before_time_ns": int(times[position - 1]),
                            "after_time_ns": int(times[position]),
                        }
                    )
                gaps += len(positions)
            for original in rows_by_item[item_id]:
                row = dict(original)
                row["series_id"] = sid
                row["native_start_index"] = int(
                    np.searchsorted(times, row["start_ns"] - 500000000, side="left")
                )
                row["native_end_exclusive"] = int(
                    np.searchsorted(times, row["stop_ns"] + 500000000, side="left")
                )
                mapped_rows.append(row)
            if shutil.disk_usage(raw).free - 2**30 < RESERVE:
                raise RuntimeError("18 GiB reserve plus write buffer unavailable")
            writer.add_series(
                sid,
                {"power_w": values},
                labels={"label_activity": labels},
                time=times,
                meta={
                    "house_id": house,
                    "item_id": item_id,
                    "item_name": item["label"],
                    "category": item["category"],
                    "source_annotated": bool(rows_by_item[item_id]),
                    "source_gap_count": gaps,
                    "source_order_runs": run_count,
                },
            )
            stats.add(sid, {"label_activity": labels})
            details.append(
                {
                    "series_id": sid,
                    "house_id": house,
                    "item_id": item_id,
                    "samples": len(times),
                    "first_time_ns": int(times[0]),
                    "last_time_ns": int(times[-1]),
                    **chronology,
                    "source_order_runs": run_count,
                    "gaps_over_3605_seconds": gaps,
                    "ambiguous_half_second_boundary_samples": ties,
                    "positive_samples": int(np.count_nonzero(labels != -1)),
                    "nonfinite_power_samples": int(
                        np.count_nonzero(~np.isfinite(values))
                    ),
                    "power_samples_ge_4000": int(np.count_nonzero(values >= 4000)),
                }
            )
            print(sid, details[-1], flush=True)
            del times, values, order, labels
    chosen_ids = {r["item_id"] for r in subset}
    for name, rows in {
        "source-annotations.parquet": mapped_rows,
        "source-labels.parquet": [r for r in definitions if r["item_id"] in chosen_ids],
        "source-items.parquet": subset,
        "monitoring-gaps.parquet": gap_rows,
    }.items():
        pq.write_table(
            pa.Table.from_pylist(rows), args.out_dir / name, compression="zstd"
        )
    if not args.pilot:
        assert len(stats.rows) == 54 and len(mapped_rows) == 1738
    finish(
        args,
        spec,
        writer,
        stats,
        title="DEDDIAG: complete native sparse appliance and mains observations",
        source=SOURCE,
        sha256=sha256(PIN),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence="https://api.figshare.com/v2/articles/13615073/versions/1",
        license_verified_date="2026-10-21",
        description="All54 native sparse power traces from15 primary houses:50 appliances and4 mains channels. Preserve UTC microsecond timestamps and every measured value, with overlapping manual events as reversible label sets and complete original interval tables; no fabricated1Hz grid.",
        collection="Fixed Figshare version1,15 house ZIPs;50 appliance streams plus three-phase and total mains from house08. Hardware queries are nominally about1Hz, but only value changes and an hourly heartbeat are stored. Native rows are irregular observations, not dense second-by-second signals. Original times are UTC with microsecond precision. All recorded measurements remain, including high-power readings and duplicates. Exclude household demographics while retaining anonymous house/item grouping and source appliance categories.",
        annotation="All1738 original closed start/stop event intervals from14 appliances,37 label definitions across15 appliances including item35 with no events. A source label definition alone does not imply reviewed negative coverage. Preserve source IDs, literal text/descriptions (including technical/error/unknown classes), original row order and decimal UTC timing. Overlapping labels become a reversible active-label set, never an exclusive winner. Unreviewed observations outside positive source intervals and unannotated streams are-1; no absence/standby negatives are invented. Default labels refer only to the observed sparse timestamps, not a dense state filling between measurements. Source annotator identities are not supplied, so no inter-rater or consensus claim.",
        conversion="Check provider MD5 and fixed SHA256 for every complete ZIP; consume nested gzip/TSV with CRC checks and bounded parsing, never execute imported SQL/scripts or extract the139GB TSV corpus. Parse source power losslessly to float64 and UTC timestamps to exact int64 nanoseconds. Stable chronological sort per item retains duplicates, with an exact per-observation source-row index represented by consecutive mapping runs in source-order.parquet; source_index=source_start+(sorted_index-sorted_start). Original annotation rows retain source_row_index. Only label association uses the authors' nearest-whole-second UI convention and closed endpoints; native timestamps are unchanged. PostgreSQL floating rounding ties are platform-dependent: exact half-second boundary cases with different adjacent label sets remain unscored. Do not apply the optional SQL get_measurements()1Hz expansion, last-value selection, interpolation or value<4000 filter. Record gaps>3605s as source-described possible monitoring gaps; no fill, trimming, downsampling or signal repair. Retain all15 houses/54 native streams, including data-only streams without dense reference.",
        limitations="Only14 of54 measurement streams have sparse positive event annotations. Outside positive intervals has no established reviewed-negative coverage; the large unscored share must not be treated as idle truth. Annotation times have second precision while source measurements have irregular subsecond precision. Events without any matching native observation remain in the original interval table and do not create samples or an exact index boundary. Time-series statistics count stored observations, not elapsed seconds. Long gaps are missing monitoring rather than inferred constant power; an explicit nominal1Hz sensor rate does not establish a regular released grid. Technical/error/unknown source labels stay distinct rather than being silently discarded. Source-row provenance permits exact inverse reconstruction of the original unsorted exports.",
        biases="A small German household cohort, device mix, multi-year recording periods and heterogeneous annotation windows limit generalization. Split by house, not random neighboring readings or devices from the same home. Mains and appliance signals within a house are correlated and are not independent annotators.",
        personal="Electricity traces can convey domestic activity patterns. Preserve anonymous source house/item IDs, timestamps and appliance categories, but omit the house.tsv resident demographics, ages and absence schedules. No inference of occupancy or resident identity is added.",
        citation="Wenninger M., Maier A., Schmidt J. (2021). DEDDIAG, a domestic electricity demand dataset of individual appliances in Germany. Scientific Data8,176. https://doi.org/10.1038/s41597-021-00963-2",
        creators=["Marc Wenninger", "Andreas Maier", "Jochen Schmidt"],
        date_published="2021-01-28",
        null_states={},
        info={
            "label_origin": "human",
            "annotators": [],
            "tracks": {
                "label_activity": {
                    "semantics": "reversible simultaneous source-label set; positive intervals only, not an exclusive appliance mode"
                }
            },
            "state_names": {
                "label_activity": {
                    code: " + ".join(
                        f"{label}:{label_names[label]}" for label in active
                    )
                    for active, code in codebook.items()
                }
            },
            "source_label_sets": {
                str(code): list(active) for active, code in codebook.items()
            },
            "nominal_sensor_rate_hz": 1,
            "released_sampling": "irregular sparse value changes plus hourly heartbeat; no resampling",
            "timestamp_unit": "UTC nanoseconds",
            "source_files": pins,
            "series_details": details,
            "pilot": args.pilot,
            "reference_doi": "https://doi.org/10.1038/s41597-021-00963-2",
            "auxiliary": {
                "source-order.parquet": "Exact source-row index for every sorted observation, represented as consecutive mapping runs; reverse the chronology without losing duplicates.",
                "source-annotations.parquet": "Every original manual interval/ID/label/timing/source-row field; inclusive source endpoints. native_start_index/native_end_exclusive describe the nearest-second candidate range before ambiguous half-second boundary masking, not sample-exact physical change points.",
                "source-labels.parquet": "Original per-appliance label vocabulary, including original misspellings and technical/unknown states.",
                "source-items.parquet": "Original non-demographic appliance descriptors and source row index.",
                "monitoring-gaps.parquet": "Observed neighboring timestamps separated by>3605s, following the primary monitoring-gap threshold; no invented intermediate rows.",
            },
        },
    )


if __name__ == "__main__":
    main()
