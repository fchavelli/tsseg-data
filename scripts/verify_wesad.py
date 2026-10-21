"""Independently compare every WESAD native value, sample index and protocol code."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from tsseg_data.reader import _to_numpy_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/wesad"))
    parser.add_argument("--raw", type=Path, default=Path("raw/wesad"))
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    index = {
        r["series_id"]: r
        for r in pq.read_table(args.build / "index.parquet").to_pylist()
    }
    expected = {"S15"} if args.pilot else {f"S{i}" for i in range(2, 18) if i != 12}
    assert set(index) == expected
    assert info["source_only"] and info["rehosting_allowed"] is False
    assert info["label_origin"] == "protocol"
    archive_path = args.raw / "WESAD.zip"
    hashes = {name: hashlib.new(name) for name in ["md5", "sha1", "sha256"]}
    with archive_path.open("rb") as stream:
        while block := stream.read(2**20):
            for h in hashes.values():
                h.update(block)
    pin = info["source_files"]["archive"]
    assert archive_path.stat().st_size == pin["bytes"]
    assert hashes["sha256"].hexdigest() == pin["sha256"]
    assert hashes["md5"].hexdigest() == pin["provider_md5"]
    assert hashes["sha1"].hexdigest() == pin["provider_sha1"]
    # Independent container decoder already used for PPG-DaLiA. No WESAD builder
    # mapping, label-mask function, channel helper or table writer is imported.
    decoder_path = Path(__file__).resolve().parents[1] / "builders/ppg-dalia.py"
    spec = importlib.util.spec_from_file_location(
        "independent_numeric_decoder", decoder_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chest_columns = {
        "ACC": ["chest_acc_x", "chest_acc_y", "chest_acc_z"],
        "ECG": ["chest_ecg"],
        "EDA": ["chest_eda"],
        "EMG": ["chest_emg"],
        "Resp": ["chest_respiration"],
        "Temp": ["chest_temperature"],
    }
    groups = {
        "wrist_acc": (32, {"ACC": ["wrist_acc_x", "wrist_acc_y", "wrist_acc_z"]}),
        "wrist_bvp": (64, {"BVP": ["wrist_bvp"]}),
        "wrist_slow": (4, {"EDA": ["wrist_eda"], "TEMP": ["wrist_temperature"]}),
    }
    seen_default, seen_native = {}, {}
    recurrence = {str(code): 0 for code in [1, 2, 3, 4]}
    total = 0
    with zipfile.ZipFile(archive_path) as archive:
        for sid in sorted(expected, key=lambda s: int(s[1:])):
            readme = archive.read(f"WESAD/{sid}/{sid}_readme.txt").decode("utf-8")
            additional = readme.partition("### Additional notes ###")[2]
            assert info["source_sensor_quality_notes"][sid] == [
                line.strip()
                for line in additional.splitlines()
                if any(word in line.lower() for word in ["sensor", "signal"])
            ]
            with archive.open(f"WESAD/{sid}/{sid}.pkl") as stream:
                original = module.RestrictedUnpickler(stream, encoding="latin1").load()
                assert stream.read(1) == b""
            assert original["subject"] == sid
            native_label = np.asarray(original["label"])
            assert np.isin(native_label, np.arange(8)).all()
            expected_label = native_label.astype(np.int8).copy()
            for code in [0, 5, 6, 7]:
                expected_label[native_label == code] = -1
            n = len(native_label)
            assert n == index[sid]["length"]
            detail = next(d for d in info["series_details"] if d["series_id"] == sid)
            assert detail["source_code_counts"] == {
                str(code): int(np.count_nonzero(native_label == code))
                for code in range(8)
            }
            assert detail["masked_samples"] == int(
                np.count_nonzero(expected_label == -1)
            )
            episodes = {
                str(code): int(
                    np.count_nonzero(
                        (expected_label == code)
                        & np.r_[True, expected_label[1:] != expected_label[:-1]]
                    )
                )
                for code in [1, 2, 3, 4]
            }
            for code, count in episodes.items():
                recurrence[code] += count > 1
            matched = 0
            for name in index[sid]["files_default"]:
                for batch in pq.ParquetFile(args.build / name).iter_batches(
                    batch_size=1
                ):
                    for row in _to_numpy_rows(pa.Table.from_batches([batch])):
                        if row["series_id"] != sid:
                            continue
                        start, end = (
                            row["chunk_start"],
                            row["chunk_start"] + row["length"],
                        )
                        assert np.array_equal(
                            row["sample_index"], np.arange(start, end)
                        )
                        assert np.array_equal(
                            row["label_protocol"], expected_label[start:end]
                        )
                        for key, names in chest_columns.items():
                            for column, target in enumerate(names):
                                source = original["signal"]["chest"][key][:, column]
                                assert len(source) == n
                                assert np.array_equal(
                                    row[target], source[start:end], equal_nan=True
                                ), (sid, target, start)
                        matched += row["length"]
            assert matched == n
            seen_default[sid] = matched
            for group, (rate, mapping) in groups.items():
                count = 0
                for path in sorted(args.build.glob(f"native_{group}-*.parquet")):
                    table = pq.read_table(path, filters=[("series_id", "=", sid)])
                    if not len(table):
                        continue
                    positions = table["sample_index"].to_numpy()
                    assert np.array_equal(
                        positions, np.arange(count, count + len(table))
                    )
                    for key, names in mapping.items():
                        for column, target in enumerate(names):
                            source = original["signal"]["wrist"][key][:, column]
                            assert np.array_equal(
                                table[target].to_numpy(),
                                source[count : count + len(table)],
                                equal_nan=True,
                            ), (sid, target, count)
                    count += len(table)
                assert count == index[sid][f"native_samples_{group}"]
                for key in mapping:
                    assert count == len(original["signal"]["wrist"][key])
                assert info["native_sampling_rates_hz"][group] == rate
                seen_native[(sid, group)] = count
            count = 0
            for path in sorted(args.build.glob("native_protocol-*.parquet")):
                table = pq.read_table(path, filters=[("series_id", "=", sid)])
                if len(table):
                    assert np.array_equal(
                        table["sample_index"].to_numpy(),
                        np.arange(count, count + len(table)),
                    )
                    assert np.array_equal(
                        table["source_label"].to_numpy(),
                        native_label[count : count + len(table)],
                    )
                    count += len(table)
            assert count == n
            total += n
            print("verified", sid, n, "episodes", episodes, flush=True)
            del original, native_label, expected_label
    assert set(seen_default) == expected and len(seen_native) == 3 * len(expected)
    print("Subjects with recurring valid condition:", recurrence)
    print(
        f"Verified {len(expected)}/{len(expected)} subjects, {total} native chest/protocol samples: all14 signal channels, all native labels, every evaluation mask and every exact sample index match; no resampling or mismatches."
    )


if __name__ == "__main__":
    main()
