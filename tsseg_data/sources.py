"""Fetching source files: local raw cache, pooch download, HTTP Range on remote zips.

Every file read from a source is checked against a pinned digest (sha256, or the
CRC32 stored in the remote zip's central directory for members extracted by HTTP
Range). Raw files live in ``<raw_dir>/<dataset_id>/`` and are never modified.

Builders that read downloaded files must be run with ``python -I`` (isolated mode),
so that no module planted in a download directory can be imported.
"""

from __future__ import annotations

import hashlib
import struct
import urllib.request
import zlib
from pathlib import Path

__all__ = [
    "USER_AGENT",
    "sha256",
    "fetch",
    "fetch_url_bytes",
    "http_range",
    "RemoteZip",
    "remote_extract",
    "file_crc32",
]

USER_AGENT = {"User-Agent": "tsseg-data/0.1 (research dataset builder)"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_crc32(path: Path) -> int:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            crc = zlib.crc32(chunk, crc)
    return crc


def fetch(
    url: str,
    fname: str,
    expected_sha256: str,
    raw_dir: Path,
    dataset_id: str,
) -> Path:
    """Return ``<raw_dir>/<dataset_id>/<fname>``, downloading it if absent.

    An existing file is reused only if its sha256 matches; a mismatch is an error
    (the raw cache is never overwritten silently). Downloads use ``pooch`` when it
    is installed, ``urllib`` otherwise.
    """
    dest_dir = Path(raw_dir) / dataset_id
    dest = dest_dir / fname
    if dest.exists():
        digest = sha256(dest)
        if digest != expected_sha256:
            raise RuntimeError(
                f"sha256 mismatch for cached {dest}: {digest} != {expected_sha256}"
            )
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pooch
    except ImportError:  # pragma: no cover - fallback without pooch
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers=USER_AGENT)
        with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
            for b in iter(lambda: r.read(1 << 20), b""):
                f.write(b)
        if sha256(tmp) != expected_sha256:
            tmp.unlink()
            raise RuntimeError(f"sha256 mismatch for {url}") from None
        tmp.rename(dest)
        return dest
    pooch.retrieve(
        url,
        known_hash=f"sha256:{expected_sha256}",
        fname=fname,
        path=dest_dir,
        downloader=pooch.HTTPDownloader(headers=USER_AGENT),
    )
    return dest


def fetch_url_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(req) as r:
        return r.read()


def http_range(url: str, start: int, end: int) -> bytes:
    """Bytes ``[start, end]`` (inclusive) of ``url``; fails if Range is ignored."""
    req = urllib.request.Request(
        url, headers={**USER_AGENT, "Range": f"bytes={start}-{end}"}
    )
    with urllib.request.urlopen(req) as r:
        if r.status != 206:
            raise RuntimeError(f"server ignored the Range header ({r.status})")
        return r.read()


class RemoteZip:
    """Reader of a remote zip's central directory over HTTP Range requests.

    Lets a builder extract a few members of a very large archive (e.g. 3 nights
    of a 22 GB Zenodo zip) without downloading it. Zip64 is supported.
    """

    def __init__(self, url: str, size: int):
        self.url, self.size = url, size
        tail = http_range(url, size - 65536 - 22, size - 1)
        i = tail.rfind(b"PK\x05\x06")
        cd_size, cd_off = struct.unpack("<II", tail[i + 12 : i + 20])
        if cd_off == 0xFFFFFFFF:  # zip64 end of central directory record
            j = tail.rfind(b"PK\x06\x06")
            cd_size, cd_off = struct.unpack("<QQ", tail[j + 40 : j + 56])
        cd = http_range(url, cd_off, cd_off + cd_size - 1)
        self.members: dict[str, dict] = {}
        p = 0
        while p < len(cd) and cd[p : p + 4] == b"PK\x01\x02":
            (method,) = struct.unpack("<H", cd[p + 10 : p + 12])
            crc, csize, usize = struct.unpack("<III", cd[p + 16 : p + 28])
            nlen, xlen, clen = struct.unpack("<HHH", cd[p + 28 : p + 34])
            (loff,) = struct.unpack("<I", cd[p + 42 : p + 46])
            name = cd[p + 46 : p + 46 + nlen].decode()
            extra = cd[p + 46 + nlen : p + 46 + nlen + xlen]
            vals: list[int] = []
            q = 0
            while q + 4 <= len(extra):
                hid, hlen = struct.unpack("<HH", extra[q : q + 4])
                if hid == 1:
                    vals = list(
                        struct.unpack(
                            "<" + "Q" * (hlen // 8), extra[q + 4 : q + 4 + hlen]
                        )
                    )
                q += 4 + hlen
            if usize == 0xFFFFFFFF:
                usize = vals.pop(0)
            if csize == 0xFFFFFFFF:
                csize = vals.pop(0)
            if loff == 0xFFFFFFFF:
                loff = vals.pop(0)
            self.members[name] = dict(
                method=method, crc=crc, csize=csize, usize=usize, loff=loff
            )
            p += 46 + nlen + xlen + clen

    def data_offset(self, name: str) -> int:
        m = self.members[name]
        h = http_range(self.url, m["loff"], m["loff"] + 29)
        nlen, xlen = struct.unpack("<HH", h[26:30])
        return m["loff"] + 30 + nlen + xlen


def remote_extract(rz: RemoteZip, name: str, dest: Path) -> int:
    """Stream-decompress one member of a remote zip to ``dest`` (CRC32-checked).

    Returns the number of bytes fetched (0 if ``dest`` already exists).
    """
    if dest.exists():
        return 0
    m = rz.members[name]
    off = rz.data_offset(name)
    req = urllib.request.Request(
        rz.url, headers={**USER_AGENT, "Range": f"bytes={off}-{off + m['csize'] - 1}"}
    )
    dec = zlib.decompressobj(-15) if m["method"] == 8 else None
    crc, fetched = 0, 0
    tmp = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        for b in iter(lambda: r.read(1 << 20), b""):
            fetched += len(b)
            out = dec.decompress(b) if dec else b
            crc = zlib.crc32(out, crc)
            f.write(out)
        if dec:
            out = dec.flush()
            crc = zlib.crc32(out, crc)
            f.write(out)
    if crc != m["crc"]:
        tmp.unlink()
        raise RuntimeError(f"CRC mismatch for {name}")
    tmp.rename(dest)
    return fetched
