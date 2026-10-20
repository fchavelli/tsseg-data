"""Read a pinned bounded prefix of the primary ROSMAG40 ZIP, without videos."""

from __future__ import annotations

import hashlib
import io
import shutil
import struct
import urllib.request
import zlib
from pathlib import Path

import numpy as np

RESERVE = 18 * 2**30


def acquire(root, manifest):
    """Require exact HTTP ranges and SHA-bound selected source bytes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "selected-prefix.bin"
    pin = manifest["prefix"]
    if not path.exists():
        # Reserve the complete source and a conservative uncompressed output budget.
        needed = pin["bytes"] + manifest["native_bytes"] * 2 + 64 * 2**20
        if shutil.disk_usage(root).free - needed < RESERVE:
            raise RuntimeError("Complete selected view breaches the 18-GiB reserve")
        req = urllib.request.Request(
            manifest["url"], headers={"Range": f"bytes=0-{pin['bytes'] - 1}"}
        )
        with urllib.request.urlopen(req, timeout=180) as response:
            expected = f"bytes 0-{pin['bytes'] - 1}/{manifest['archive_bytes']}"
            if (
                response.status != 206
                or response.headers.get("Content-Range") != expected
            ):
                raise RuntimeError("Primary endpoint did not honor the bounded range")
            data = response.read(pin["bytes"] + 1)
        if (
            len(data) != pin["bytes"]
            or hashlib.sha256(data).hexdigest() != pin["sha256"]
        ):
            raise RuntimeError("Selected source prefix size/SHA256 mismatch")
        path.write_bytes(data)
    data = path.read_bytes()
    if len(data) != pin["bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise RuntimeError("Cached selected prefix size/SHA256 mismatch")
    return data


def member(data, pin):
    """Decode one explicitly selected local ZIP member and verify native bytes."""
    offset = pin["offset"]
    assert data[offset : offset + 4] == b"PK\x03\x04"
    flags, method = struct.unpack_from("<HH", data, offset + 6)
    assert not flags & 1 and method == pin["method"] == 8
    name_size, extra_size = struct.unpack_from("<HH", data, offset + 26)
    name = data[offset + 30 : offset + 30 + name_size].decode()
    assert name == pin["name"]
    start = offset + 30 + name_size + extra_size
    decoder = zlib.decompressobj(-15)
    result = decoder.decompress(
        data[start : start + pin["compressed"]], pin["size"] + 1
    )
    assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    assert len(result) == pin["size"] and zlib.crc32(result) == pin["crc"]
    assert hashlib.sha256(result).hexdigest() == pin["sha256"]
    return result


def parse_signal(data, channels):
    """Parse the published 34-column feature view without additional processing."""
    assert data.decode().splitlines()[0].split() == channels
    values = np.loadtxt(io.BytesIO(data), skiprows=1)
    assert values.ndim == 2 and values.shape[1] == 34 and np.isfinite(values).all()
    return values.astype(np.float32)
