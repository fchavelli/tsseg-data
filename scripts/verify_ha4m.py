"""Verify every published HA4M observation against literal pinned source blocks.

Run before deleting the validated raw cache. This verification reconstructs
native frame/body/block order from main plus auxiliary rather than reusing the
builder's decoder or selecting an actor.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.ha4m import acquire  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/ha4m"))
    parser.add_argument("--raw", type=Path, default=Path("raw/ha4m"))
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    channels = info["channels"]
    frames = pq.read_table(args.build / "source_frames.parquet").to_pandas()
    originals = pq.read_table(args.build / "original_labels.parquet").to_pandas()
    extras = pq.read_table(args.build / "unassigned_skeletons.parquet").to_pylist()
    extra_by_key = {
        (row["series_id"], row["frame_id"], row["source_block_index"]): row
        for row in extras
    }
    assert len(extra_by_key) == len(extras)
    seen_extra, seen_trials, blocks_total = set(), set(), 0
    for name in info["configs"]["default"]["files"]:
        for batch in pq.ParquetFile(args.build / name).iter_batches(batch_size=1):
            row = batch.to_pydict()
            trial = row["series_id"][0]
            assert trial not in seen_trials
            seen_trials.add(trial)
            native = frames[frames.series_id == trial].set_index("frame_id")
            x = np.column_stack(
                [np.asarray(row[c][0], dtype=np.float32) for c in channels]
            )
            n = len(x)
            assert np.array_equal(native.index, np.arange(n))
            assert row["frame_id"][0] == list(range(n))
            pin = info["source_files"]["trials"][trial]
            raw, labels, _ = acquire(args.raw, trial, pin["source_bytes"], pin)
            original_rows = np.loadtxt(io.BytesIO(labels), dtype=np.int64)
            original_table = originals[originals.source_declared_trial == trial]
            assert np.array_equal(
                original_table[
                    ["source_frame_id", "source_action", "source_repetition"]
                ].to_numpy(),
                original_rows,
            )
            correction = info.get("corrected_label_associations", {}).get(trial)
            if correction:
                label_trial = correction["source_label_trial"]
                labels = (args.raw / f"{label_trial}.Labels.txt").read_bytes()
                assert (
                    hashlib.sha256(labels).hexdigest()
                    == info["source_files"]["trials"][label_trial]["label_sha256"]
                )
                evidence_pin = correction["author_ground_truth"]
                evidence_bytes = (args.raw / evidence_pin["filename"]).read_bytes()
                assert (
                    hashlib.sha256(evidence_bytes).hexdigest() == evidence_pin["sha256"]
                )
                author = np.loadtxt(io.BytesIO(evidence_bytes), dtype=np.int64)
                assert np.array_equal(
                    np.loadtxt(io.BytesIO(labels), dtype=np.int64)[:, 1], author
                )
            label_rows = np.loadtxt(io.BytesIO(labels), dtype=np.int64)
            known = set(label_rows[:, 0])
            for fid, action, repetition in label_rows:
                assert row["label_action"][0][fid] == action
                assert native.loc[fid, "source_action"] == action
                assert native.loc[fid, "source_repetition"] == repetition
            for fid in set(range(n)) - known:
                assert row["label_action"][0][fid] == -1
                assert np.isnan(native.loc[fid, "source_action"])
            source_frame_ids = set()
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    match = re.search(
                        r"FrameID(\d+)_DeviceTimeStamp(\d+)us.txt$", item.filename
                    )
                    assert match
                    fid, timestamp = int(match[1]), int(match[2])
                    source_frame_ids.add(fid)
                    assert native.loc[fid, "device_timestamp_us"] == timestamp
                    data = archive.read(item)
                    header = data.splitlines()[0].decode().split("\t")
                    assert channels == [
                        f"joint{j:02}_{field.lower()}"
                        for j in range(32)
                        for field in header[2:]
                    ]
                    source = np.loadtxt(io.BytesIO(data), skiprows=1).reshape(
                        -1, 32, 14
                    )
                    valid_blocks = sum(
                        int(block[0, 0]) != 0xFFFFFFFF for block in source
                    )
                    main_blocks = 0
                    for index, block in enumerate(source):
                        blocks_total += 1
                        expected = block[:, 2:].astype(np.float32).reshape(-1)
                        assert np.array_equal(block[:, 1], np.arange(32))
                        assert np.all(block[:, 0] == block[0, 0])
                        body = int(block[0, 0])
                        key = (trial, fid, index)
                        if key in extra_by_key:
                            extra = extra_by_key[key]
                            assert extra["source_body_id"] == body
                            assert extra["reason"] == (
                                "invalid_sdk_body_id"
                                if body == 0xFFFFFFFF
                                else "multiple_valid_body_ids"
                            )
                            assert np.array_equal(
                                np.asarray(extra["values"], dtype=np.float32), expected
                            )
                            seen_extra.add(key)
                        else:
                            main_blocks += 1
                            assert native.loc[fid, "body_id"] == body
                            assert np.array_equal(x[fid], expected)
                    assert main_blocks == int(valid_blocks == 1)
                    if not main_blocks:
                        assert np.isnan(x[fid]).all() and np.isnan(
                            native.loc[fid, "body_id"]
                        )
            for fid in set(range(n)) - source_frame_ids:
                assert np.isnan(x[fid]).all()
                assert np.isnan(native.loc[fid, "device_timestamp_us"])
            if len(seen_trials) % 25 == 0:
                print(f"{len(seen_trials)}/217 trials reconstructed", flush=True)
    assert seen_trials == set(info["source_files"]["trials"])
    assert len(seen_trials) == 217 and seen_extra == set(extra_by_key)
    assert blocks_total == info["source_skeleton_blocks"]
    print(
        f"Verified217 trials, {blocks_total} native blocks, {len(extras)} auxiliary blocks; all values/IDs/timestamps/labels exact after float32 cast."
    )


if __name__ == "__main__":
    main()
