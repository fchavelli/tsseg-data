"""Independently invert DEDDIAG source order and verify every native TSV value."""

from __future__ import annotations

import argparse
import calendar
import csv
import gzip
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from tsseg_data.reader import _to_numpy_rows

SECOND = 10**9


def stamp(value):
    parsed = datetime.fromisoformat(value)
    return calendar.timegm(parsed.timetuple()) * SECOND + parsed.microsecond * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/deddiag"))
    parser.add_argument("--raw", type=Path, default=Path("raw/deddiag"))
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    index = {
        r["series_id"]: r
        for r in pq.read_table(args.build / "index.parquet").to_pylist()
    }
    if not info["pilot"]:
        assert len(index) == 54
    annotations = pq.read_table(args.build / "source-annotations.parquet").to_pylist()
    actual_annotations = {int(row["id"]): row for row in annotations}
    actual_definitions = {
        (row["source_member"], row["source_row_index"]): row
        for row in pq.read_table(args.build / "source-labels.parquet").to_pylist()
    }
    actual_items = {
        (row["source_member"], row["source_row_index"]): row
        for row in pq.read_table(args.build / "source-items.parquet").to_pylist()
    }
    order_rows = pq.read_table(args.build / "source-order.parquet").to_pylist()
    gaps = pq.read_table(args.build / "monitoring-gaps.parquet").to_pylist()
    bits_to_code = {
        sum(1 << label for label in labels): int(code)
        for code, labels in info["source_label_sets"].items()
    }
    verified, seen_annotations, seen_definitions, seen_items = {}, set(), set(), set()
    raw_events = {}
    houses = {row["house_id"] for row in index.values()}
    with_archives = {}
    for pin in info["source_files"]["files"]:
        house = int(pin["name"][6:8])
        if house not in houses:
            continue
        path = args.raw / pin["name"]
        assert path.stat().st_size == pin["size"]
        hashes = {key: hashlib.new(key) for key in ["md5", "sha256"]}
        with path.open("rb") as stream:
            while block := stream.read(2**20):
                for h in hashes.values():
                    h.update(block)
        assert hashes["md5"].hexdigest() == pin["computed_md5"]
        assert hashes["sha256"].hexdigest() == pin["sha256"]
        archive = zipfile.ZipFile(path)
        with_archives[house] = archive
        assert {
            name for name in archive.namelist() if name.endswith("_data.tsv.gz")
        } == {
            f"house_{house:02d}/item_{row['item_id']:04d}_data.tsv.gz"
            for row in index.values()
            if row["house_id"] == house
        }
        for member in archive.namelist():
            if not (
                member.endswith("items.tsv")
                or member.endswith("_annotation_labels.tsv")
                or member.endswith("_annotations.tsv")
            ):
                continue
            text = archive.read(member).decode("utf-8")
            assert (
                hashlib.sha256(text.encode()).hexdigest()
                == pin["metadata_member_sha256"][member]
            )
            for offset, record in enumerate(
                csv.DictReader(io.StringIO(text), delimiter="\t")
            ):
                if member.endswith("_annotations.tsv"):
                    key = int(record["id"])
                    stored = actual_annotations[key]
                    seen_annotations.add(key)
                    assert (
                        stored["source_member"] == member
                        and stored["source_row_index"] == offset
                    )
                    for field, value in record.items():
                        assert stored[field] == value
                    assert stored["start_ns"] == stamp(record["start_date"])
                    assert stored["stop_ns"] == stamp(record["stop_date"])
                    raw_events.setdefault(int(record["item_id"]), []).append(
                        (
                            stamp(record["start_date"]),
                            stamp(record["stop_date"]),
                            int(record["label_id"]),
                        )
                    )
                else:
                    key = (member, offset)
                    target = (
                        actual_items
                        if member.endswith("items.tsv")
                        else actual_definitions
                    )
                    stored = target[key]
                    for field, value in record.items():
                        assert stored[field] == value
                    (
                        seen_items if member.endswith("items.tsv") else seen_definitions
                    ).add(key)
    assert seen_annotations == set(actual_annotations) and len(seen_annotations) == len(
        annotations
    )
    assert seen_definitions == set(actual_definitions) and seen_items == set(
        actual_items
    )
    for filename in info["configs"]["default"]["files"]:
        for batch in pq.ParquetFile(args.build / filename).iter_batches(batch_size=1):
            for row in _to_numpy_rows(pa.Table.from_batches([batch])):
                sid = row["series_id"]
                assert (
                    sid not in verified
                    and row["chunk_idx"] == 0
                    and row["chunk_start"] == 0
                )
                meta = index[sid]
                times, values, labels = (
                    row["time_ns"],
                    row["power_w"],
                    row["label_activity"],
                )
                n = len(times)
                assert n == meta["length"] and np.all(times[1:] >= times[:-1])
                provenance = [r for r in order_rows if r["series_id"] == sid]
                assert len(provenance) == meta["source_order_runs"]
                inverse = np.empty(n, dtype=np.uint32)
                previous_sorted = previous_source_end = 0
                for run in provenance:
                    assert run["sorted_start"] == previous_sorted and run["length"] > 0
                    a, b, length = (
                        run["source_start"],
                        run["sorted_start"],
                        run["length"],
                    )
                    assert a >= 0 and a + length <= n
                    if b and times[b - 1] == times[b]:
                        assert previous_source_end < a
                    inverse[a : a + length] = np.arange(b, b + length, dtype=np.uint32)
                    previous_sorted += length
                    previous_source_end = a + length - 1
                assert previous_sorted == n
                previous = 0
                for run in sorted(provenance, key=lambda r: r["source_start"]):
                    assert run["source_start"] == previous
                    previous += run["length"]
                assert previous == n
                source_member = f"house_{meta['house_id']:02d}/item_{meta['item_id']:04d}_data.tsv.gz"
                archive = with_archives[meta["house_id"]]
                count = 0
                with gzip.GzipFile(fileobj=archive.open(source_member)) as source:
                    reader = pacsv.open_csv(
                        source,
                        read_options=pacsv.ReadOptions(block_size=8 * 2**20),
                        parse_options=pacsv.ParseOptions(delimiter="\t"),
                        convert_options=pacsv.ConvertOptions(
                            column_types={
                                "item_id": pa.int32(),
                                "time": pa.timestamp("ns"),
                                "value": pa.float64(),
                            },
                            null_values=["\\N"],
                        ),
                    )
                    for original in reader:
                        length = len(original)
                        assert np.all(
                            original.column("item_id").to_numpy() == meta["item_id"]
                        )
                        source_times = (
                            original.column("time").cast(pa.int64()).to_numpy()
                        )
                        source_values = original.column("value").to_numpy()
                        positions = inverse[count : count + length]
                        assert np.array_equal(times[positions], source_times), (
                            sid,
                            count,
                            "source time",
                        )
                        assert np.array_equal(
                            values[positions], source_values, equal_nan=True
                        ), (sid, count, "source power")
                        count += length
                assert count == n
                events = raw_events.get(meta["item_id"], [])
                assert meta["source_annotated"] == bool(events)
                for stored in annotations:
                    if stored["series_id"] != sid:
                        continue
                    assert stored["native_start_index"] == int(
                        np.searchsorted(
                            times, stamp(stored["start_date"]) - SECOND // 2
                        )
                    )
                    assert stored["native_end_exclusive"] == int(
                        np.searchsorted(times, stamp(stored["stop_date"]) + SECOND // 2)
                    )
                expected = np.full(n, -1, dtype=np.int32)
                if events:
                    active = np.zeros(n, dtype=np.uint64)
                    for first, last, label in events:
                        a = np.searchsorted(times, first - SECOND // 2, side="left")
                        b = np.searchsorted(times, last + SECOND // 2, side="left")
                        active[a:b] |= np.uint64(1 << label)
                    for bits, code in bits_to_code.items():
                        expected[active == bits] = code
                    for start in range(0, n, 262144):
                        tie_positions = (
                            np.flatnonzero(
                                times[start : start + 262144] % SECOND == SECOND // 2
                            )
                            + start
                        )
                        for point in tie_positions:
                            floor = int(times[point] // SECOND) * SECOND
                            left = {label for a, b, label in events if a <= floor <= b}
                            right = {
                                label
                                for a, b, label in events
                                if a <= floor + SECOND <= b
                            }
                            if left != right:
                                expected[point] = -1
                    del active
                assert np.array_equal(labels, expected), (sid, "every reference label")
                actual_gaps = [
                    (
                        r["before_index"],
                        r["after_index"],
                        r["before_time_ns"],
                        r["after_time_ns"],
                    )
                    for r in gaps
                    if r["series_id"] == sid
                ]
                expected_gaps = []
                for start in range(1, n, 262144):
                    end = min(n, start + 262144)
                    positions = (
                        np.flatnonzero(
                            times[start:end] - times[start - 1 : end - 1]
                            > 3605 * SECOND
                        )
                        + start
                    )
                    expected_gaps.extend(
                        (int(p - 1), int(p), int(times[p - 1]), int(times[p]))
                        for p in positions
                    )
                assert (
                    actual_gaps == expected_gaps
                    and len(actual_gaps) == meta["source_gap_count"]
                )
                verified[sid] = n
                print("verified", sid, n, flush=True)
                del inverse, expected, times, values, labels
    assert set(verified) == set(index)
    for archive in with_archives.values():
        archive.close()
    print(
        f"Verified {len(verified)}/{len(index)} native sparse traces, {sum(verified.values())} observations: exact inverse source order, timestamps/power, duplicates, original annotation/label/item fields, overlapping reference sets and monitoring gaps; no mismatches."
    )


if __name__ == "__main__":
    main()
