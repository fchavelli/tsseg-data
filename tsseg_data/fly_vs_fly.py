"""Read the selected primary Fly vs. Fly native MAT tracking view."""

from __future__ import annotations

import hashlib
import io
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import numpy as np
from scipy.io import loadmat

RESERVE = 18 * 2**30
BEHAVIORS = [
    "touch",
    "lunge",
    "wing_threat",
    "charge",
    "hold",
    "tussle",
    "wing_extension",
    "circle",
    "copul_attempt",
    "copulation",
]
SOURCE_NAMES = [
    "pos x",
    "pos y",
    "ori",
    "major axis len",
    "minor axis len",
    "wing l x",
    "wing l y",
    "wing r x",
    "wing r y",
    "body area",
    "fg area",
    "img contrast",
    "min fg dist",
    "wing l ang",
    "wing r ang",
    "wing l len",
    "wing r len",
]
CHANNELS = [f"fly{f}_{name.replace(' ', '_')}" for f in [1, 2] for name in SOURCE_NAMES]
TRACKS = [
    f"label_{annotation}_fly{f}_{b}"
    for annotation in ["primary", "second"]
    for f in [1, 2]
    for b in BEHAVIORS
]


def fetch(url, start, end, total):
    """Accept only the requested bounded primary-source HTTP206 response."""
    size = end - start + 1
    if (
        shutil.disk_usage(Path(__file__).resolve().parents[1]).free - size - 64 * 2**20
        < RESERVE
    ):
        raise RuntimeError("Range transfer breaches the 18-GiB reserve")
    result = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            "180",
            "--range",
            f"{start}-{end}",
            "--max-filesize",
            str(max(size, 1024)),
            "-D",
            "/dev/stderr",
            url,
        ],
        capture_output=True,
        check=True,
    )
    headers = result.stderr.decode().lower()
    if (
        [
            line.split()[1]
            for line in headers.splitlines()
            if line.lower().startswith("http/")
        ][-1]
        != "206"
        or f"content-range: bytes {start}-{end}/{total}" not in headers
        or len(result.stdout) != size
    ):
        raise RuntimeError("Source did not honor exact bounded HTTP range")
    return result.stdout


def acquire(root, manifest):
    """Acquire all SHA-pinned native members without complete archives or videos."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Native MAT cache plus conservative complete Parquet output and buffer.
    needed = (
        sum(p["size"] for a in manifest["archives"] for p in a["members"])
        + 2**30
        + 64 * 2**20
    )
    if shutil.disk_usage(root).free - needed < RESERVE:
        raise RuntimeError("Complete selected source/output budget breaches 18 GiB")
    for archive in manifest["archives"]:
        for pin in archive["members"]:
            assert (
                not Path(pin["name"]).is_absolute()
                and ".." not in Path(pin["name"]).parts
            )
            path = root / archive["name"].removesuffix(".zip") / pin["name"]
            if not path.exists():
                head = fetch(
                    archive["url"], pin["offset"], pin["offset"] + 29, archive["bytes"]
                )
                assert head[:4] == b"PK\x03\x04"
                flags, method = struct.unpack_from("<HH", head, 6)
                assert not flags & 1 and method == pin["method"] == 8
                n, e = struct.unpack_from("<HH", head, 26)
                data = fetch(
                    archive["url"],
                    pin["offset"] + 30,
                    pin["offset"] + 29 + n + e + pin["compressed"],
                    archive["bytes"],
                )
                assert data[:n].decode() == pin["name"] and pin["method"] == 8
                decoder = zlib.decompressobj(-15)
                native = decoder.decompress(data[n + e :], pin["size"] + 1)
                assert (
                    decoder.eof
                    and not decoder.unused_data
                    and not decoder.unconsumed_tail
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(native)
            checked(path, pin)


def checked(path, pin):
    """Verify selected native bytes before parsing them as numeric MATLAB data."""
    data = Path(path).read_bytes()
    assert len(data) == pin["size"] and zlib.crc32(data) == pin["crc"]
    assert hashlib.sha256(data).hexdigest() == pin["sha256"]
    return loadmat(io.BytesIO(data), simplify_cells=True)


def dense(actions, n, annotation, rows, sid, n_annotated_flies):
    """Map literal one-based inclusive bouts independently for every behavior."""
    labels = {
        t: np.full(n, -1, dtype=np.int8)
        for t in TRACKS
        if t.startswith(f"label_{annotation}_")
    }
    if actions is None:
        return labels
    names = list(np.atleast_1d(actions["behs"]))
    assert set(names) <= set(BEHAVIORS + ["unknown", "none", "other"])
    bouts = actions["bouts"]
    assert bouts.shape == (2, len(names))
    for fly in range(2):
        if fly >= n_annotated_flies:
            assert all(np.asarray(cell).size == 0 for cell in bouts[fly])
            continue
        unknown = np.zeros(n, dtype=bool)
        for j, name in enumerate(names):
            intervals = np.asarray(bouts[fly, j])
            if not intervals.size:
                intervals = np.empty((0, 3))
            else:
                intervals = np.atleast_2d(intervals)
            assert intervals.ndim == 2 and intervals.shape[1] in (2, 3)
            if name in BEHAVIORS:
                y = labels[f"label_{annotation}_fly{fly + 1}_{name}"]
                y[:] = 0
            for index, bout in enumerate(intervals):
                start, end = map(int, bout[:2])
                assert start == bout[0] and end == bout[1]
                assert 1 <= start <= end <= n, (sid, name, start, end, n)
                rows.append(
                    {
                        "series_id": sid,
                        "annotation": annotation,
                        "fly": fly + 1,
                        "behavior": str(name),
                        "source_bout_index": index,
                        "start_frame_inclusive": start,
                        "end_frame_inclusive": end,
                        "certainty": float(bout[2]) if len(bout) == 3 else None,
                    }
                )
                if name == "unknown":
                    unknown[start - 1 : end] = True
                elif name in BEHAVIORS:
                    y[start - 1 : end] = 1
        for name in BEHAVIORS:
            labels[f"label_{annotation}_fly{fly + 1}_{name}"][unknown] = -1
    return labels
