"""Independently compare every native Fly vs. Fly value, bout and binary label."""

from __future__ import annotations

import argparse
import hashlib
import json
import zlib
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from scipy.io import loadmat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/fly-vs-fly"))
    parser.add_argument("--raw", type=Path, default=Path("raw/fly-vs-fly"))
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    index = {
        r["series_id"]: r
        for r in pq.read_table(args.build / "index.parquet").to_pylist()
    }
    pin_index = {}
    for archive in info["source_files"]["archives"]:
        for pin in archive["members"]:
            path = args.raw / archive["name"].removesuffix(".zip") / pin["name"]
            data = path.read_bytes()
            assert (
                len(data) == pin["size"]
                and zlib.crc32(data) == pin["crc"]
                and hashlib.sha256(data).hexdigest() == pin["sha256"]
            )
            pin_index[pin["name"]] = path
    bout_actual = pq.read_table(args.build / "bouts.parquet").to_pylist()
    flags = pq.read_table(args.build / "tracking-flags.parquet").to_pylist()
    bouts_expected = []
    seen = set()
    total = 0
    for file in info["configs"]["default"]["files"]:
        for batch in pq.ParquetFile(args.build / file).iter_batches(batch_size=1):
            row = batch.to_pylist()[0]
            sid = row["series_id"]
            meta = index[sid]
            assert sid not in seen
            seen.add(sid)
            path = pin_index[meta["source_track_member"]]
            source = loadmat(path, struct_as_record=False, squeeze_me=True)["trk"]
            assert source.data.shape == (2, row["length"], 17)
            n = row["length"]
            rate = 200 if meta["subset"].startswith("Boy") else 30
            assert meta["sampling_rate_hz"] == rate
            assert row["time_ns"] == [i * 10**9 // rate for i in range(n)]
            for f in range(2):
                for j, name in enumerate(source.names):
                    column = f"fly{f + 1}_{str(name).replace(' ', '_')}"
                    assert np.array_equal(
                        np.asarray(row[column], np.float32),
                        source.data[f, :, j].astype(np.float32),
                        equal_nan=True,
                    ), (sid, column)
            source_flags = np.asarray(source.flag_frames)
            reconstructed = np.full(len(source_flags), -999, dtype=np.int64)
            for interval in [r for r in flags if r["series_id"] == sid]:
                a = interval["start"]
                b = interval["end_exclusive"]
                assert np.all(reconstructed[a:b] == -999)
                reconstructed[a:b] = interval["flag_frames"]
            assert np.array_equal(reconstructed, source_flags)
            split_path = next(
                p
                for name, p in pin_index.items()
                if name.split("/")[0] == meta["source_track_member"].split("/")[0]
                and name.endswith("traintest.mat")
            )
            split = loadmat(split_path, simplify_cells=True)
            relative = meta["source_track_member"].split("/", 1)[1].rsplit("/", 1)[0]
            movie_id = list(split["movienames"]).index(relative) + 1
            assert meta["split"] == (
                "train" if movie_id in np.atleast_1d(split["trainids"]) else "test"
            )
            for slot in ["primary", "second"]:
                suffix = "_actions.mat" if slot == "primary" else "_second_actions.mat"
                action_name = meta["source_track_member"].replace("_track.mat", suffix)
                action = (
                    loadmat(pin_index[action_name], simplify_cells=True)
                    if action_name in pin_index
                    else None
                )
                for f in range(2):
                    unknown = np.zeros(n, dtype=bool)
                    if action is not None:
                        for b, behavior in enumerate(action["behs"]):
                            cells = np.asarray(action["bouts"][f, b])
                            cells = (
                                np.atleast_2d(cells) if cells.size else np.empty((0, 3))
                            )
                            for k, interval in enumerate(cells):
                                start, end = map(int, interval[:2])
                                assert 1 <= start <= end <= n
                                bouts_expected.append(
                                    {
                                        "series_id": sid,
                                        "annotation": slot,
                                        "fly": f + 1,
                                        "behavior": str(behavior),
                                        "source_bout_index": k,
                                        "start_frame_inclusive": start,
                                        "end_frame_inclusive": end,
                                        "certainty": float(interval[2])
                                        if len(interval) == 3
                                        else None,
                                    }
                                )
                                if behavior == "unknown":
                                    unknown[np.arange(start - 1, end)] = True
                    for column in info["label_columns"]:
                        prefix = f"label_{slot}_fly{f + 1}_"
                        if not column.startswith(prefix):
                            continue
                        behavior = column[len(prefix) :]
                        expected = np.full(n, -1, dtype=np.int8)
                        if (
                            action is not None
                            and f < int(split["n_flies"])
                            and behavior in action["behs"]
                        ):
                            expected[:] = 0
                            b = list(action["behs"]).index(behavior)
                            cells = np.asarray(action["bouts"][f, b])
                            if cells.size:
                                for interval in np.atleast_2d(cells):
                                    expected[
                                        np.arange(
                                            int(interval[0]) - 1, int(interval[1])
                                        )
                                    ] = 1
                            expected[unknown] = -1
                        assert np.array_equal(row[column], expected), (sid, column)
            total += n

    def key(r):
        return (
            r["series_id"],
            r["annotation"],
            r["fly"],
            r["behavior"],
            r["source_bout_index"],
        )

    assert sorted(bout_actual, key=key) == sorted(bouts_expected, key=key)
    assert len(seen) == 47 and seen == set(index)
    print(
        f"Verified47/47 scenes, {total} frames, all34 float32 observations including NaNs,40 binary tracks, exact source splits, native clocks, every flag value and {len(bouts_expected)} original bouts; no mismatches."
    )


if __name__ == "__main__":
    main()
