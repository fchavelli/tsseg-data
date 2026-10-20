"""Reconstruct every RSDF published value and conservative CP reference independently."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from tsseg_data.reader import _to_numpy_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/rsdf-china-forest"))
    parser.add_argument("--raw", type=Path, default=Path("raw/rsdf-china-forest"))
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    pins = info["source_files"]
    for pin in pins["files"]:
        data = (args.raw / pin["name"]).read_bytes()
        assert (
            len(data) == pin["bytes"]
            and hashlib.md5(data).hexdigest() == pin["provider_md5"]
            and hashlib.sha256(data).hexdigest() == pin["sha256"]
        )
    source = defaultdict(list)
    for i, row in enumerate(
        csv.DictReader((args.raw / "RSDF.csv").open(encoding="utf-8-sig", newline=""))
    ):
        row["source_row_index"] = i
        source[row["PID"]].append(row)
    index = {
        r["series_id"]: r
        for r in pq.read_table(args.build / "index.parquet").to_pylist()
    }
    aux = pq.read_table(args.build / "source-annotations.parquet").to_pylist()
    assert len(aux) == 13765
    aux_by_source = {r["source_row_index"]: r for r in aux}
    assert len(aux_by_source) == 13765
    source_order = {
        r["series_id"]: r["source_row_index"]
        for r in _to_numpy_rows(pq.read_table(args.build / "source-order.parquet"))
    }
    expected_columns = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2", "Sensor", "QA"]
    seen = set()
    total = 0
    nan_values = 0
    with zipfile.ZipFile(args.raw / "RSDF_SurfaceReflectance.zip") as archive:
        for file in info["configs"]["default"]["files"]:
            for batch in pq.ParquetFile(args.build / file).iter_batches(batch_size=32):
                for row in _to_numpy_rows(pa.Table.from_batches([batch])):
                    pid = row["series_id"]
                    assert pid not in seen
                    seen.add(pid)
                    meta = index[pid]
                    content = archive.read(meta["source_member"])
                    assert hashlib.sha256(content).hexdigest() == meta["source_sha256"]
                    records = list(
                        csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
                    )
                    dates = np.array(
                        [
                            np.datetime64(
                                dt.date(int(r["Year"]), int(r["Month"]), int(r["Day"])),
                                "ns",
                            )
                            for r in records
                        ]
                    )
                    n = len(records)
                    order = source_order[pid]
                    assert np.array_equal(order, np.argsort(dates, kind="stable"))
                    assert meta["native_date_reversals"] == int(
                        np.count_nonzero(dates[1:] < dates[:-1])
                    )
                    native_dates = dates.copy()
                    dates = dates[order]
                    assert all(r["PID"] == pid for r in records)
                    assert all(
                        float(r["Lon"]) == float(records[0]["Lon"])
                        and float(r["Lat"]) == float(records[0]["Lat"])
                        for r in records
                    )
                    assert np.array_equal(row["date"], dates)
                    assert np.array_equal(row["date"][np.argsort(order)], native_dates)
                    assert meta["longitude"] == float(records[0]["Lon"]) and meta[
                        "latitude"
                    ] == float(records[0]["Lat"])
                    for channel, key in zip(
                        info["channels"], expected_columns, strict=True
                    ):
                        expected = np.array(
                            [
                                float(r[key]) if r[key] else float("nan")
                                for r in records
                            ],
                            dtype=np.float32,
                        )
                        nan_values += int(np.isnan(expected).sum())
                        assert np.array_equal(
                            row[channel][np.argsort(order)], expected, equal_nan=True
                        ), (
                            pid,
                            key,
                        )
                    mapped = defaultdict(set)
                    blank = False
                    event = False
                    bad = False
                    for r in source[pid]:
                        actual = aux_by_source[r["source_row_index"]]
                        for key, value in r.items():
                            assert actual[key] == value, (pid, key)
                        if not r["Year"]:
                            blank = True
                            assert (
                                actual["mapping_status"] == "source_stable_claim"
                                and actual["mapped_cp"] is None
                            )
                            continue
                        event = True
                        date = dt.date(int(r["Year"]), 1, 1) + dt.timedelta(
                            days=int(r["Doy"]) - 1
                        )
                        # Independent linear mapping instead of builder searchsorted.
                        cp = next(
                            (
                                i
                                for i, value in enumerate(dates)
                                if value >= np.datetime64(date, "ns")
                            ),
                            n,
                        )
                        assert (
                            actual["event_date"] == date and actual["mapped_cp"] == cp
                        )
                        assert actual["normalized_type"] == r["Type"].strip()
                        expected_next = (
                            None
                            if cp == n
                            else dates[cp].astype("datetime64[us]").astype(dt.datetime)
                        )
                        expected_previous = (
                            None
                            if cp == 0
                            else dates[cp - 1]
                            .astype("datetime64[us]")
                            .astype(dt.datetime)
                        )
                        assert (
                            actual["next_observation_date"] == expected_next
                            and actual["preceding_observation_date"]
                            == expected_previous
                        )
                        if cp == 0 or cp == n:
                            bad = True
                        else:
                            mapped[cp].add((date, r["Type"].strip()))
                    ambiguous = (
                        bad
                        or (blank and event)
                        or any(len(values) > 1 for values in mapped.values())
                    )
                    if ambiguous:
                        assert (
                            row["cps_reference"] is None
                            and meta["n_cps_reference"] is None
                        )
                    else:
                        assert row["cps_reference"].tolist() == sorted(mapped)
                        assert row["cp_types_reference"].tolist() == [
                            next(iter(mapped[k]))[1] for k in sorted(mapped)
                        ]
                    assert row["length"] == n
                    total += n
    assert len(seen) == 12991 and seen == set(source) == set(index)
    print(
        f"Verified12,991/12,991 PIDs, {total} native observations, all6 bands+Sensor+QA, exact source dates/order/coordinates/SHA/CRC, every13,765 source annotation rows and conservative CP mapping, {nan_values} native missing numeric values; no mismatches."
    )


if __name__ == "__main__":
    main()
