"""Independently compare every ROSMAG40 published value and label with pinned TXT."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/rosmag40"))
    parser.add_argument("--raw", type=Path, default=Path("raw/rosmag40"))
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    pins = info["source_files"]
    source = (args.raw / "selected-prefix.bin").read_bytes()
    assert len(source) == pins["prefix"]["bytes"]
    assert hashlib.sha256(source).hexdigest() == pins["prefix"]["sha256"]
    native = {}
    for pin in pins["members"]:
        pos = pin["offset"]
        # Decode independently of the acquisition/parser implementation.
        header = struct.unpack("<4s5H3I2H", source[pos : pos + 30])
        assert header[0] == b"PK\x03\x04" and header[3] == 8
        name_len, extra_len = header[-2:]
        assert source[pos + 30 : pos + 30 + name_len].decode() == pin["name"]
        start = pos + 30 + name_len + extra_len
        data = zlib.decompress(source[start : start + pin["compressed"]], -15)
        assert len(data) == pin["size"] and zlib.crc32(data) == pin["crc"]
        assert hashlib.sha256(data).hexdigest() == pin["sha256"]
        native[pin["name"].lower()] = data.decode().splitlines()
    assert len(native) == 120
    index = {
        row["series_id"]: row
        for row in pq.read_table(args.build / "index.parquet").to_pylist()
    }
    seen, total = set(), 0
    for file in info["configs"]["default"]["files"]:
        for row in pq.read_table(args.build / file).to_pylist():
            sid = row["series_id"]
            assert sid not in seen
            seen.add(sid)
            lines = native[f"kinematics/{sid}.txt".lower()]
            assert [s.lower() for s in lines[0].split()] == info["channels"]
            expected = np.array(
                [[float(s) for s in line.split()] for line in lines[1:]],
                dtype=np.float32,
            )
            actual = np.column_stack([row[c] for c in info["channels"]]).astype(
                np.float32
            )
            assert np.array_equal(actual, expected)
            n = len(expected)
            assert row["source_row_index"] == list(range(n))
            for level in ["fgd", "md"]:
                labels = np.array(
                    [
                        [int(s) for s in line.split()]
                        for line in native[f"{level}labels/{sid}_gesture.txt".lower()]
                    ]
                )
                assert labels.shape == (n, 2)
                for col, tool in enumerate(["psm1", "psm2"]):
                    assert row[f"label_{level}_{tool}"] == labels[:, col].tolist()
            assert index[sid]["subject_id"] == sid.split("_")[0]
            total += n
    assert len(seen) == 40 and total == 72843
    assert info["sampling_rate_hz"] is None
    print(
        "Verified 40/40 trials, 72,843 rows, all 34 float32 values and four labels per row, exact source order and SHA256/CRC; no mismatches."
    )


if __name__ == "__main__":
    main()
