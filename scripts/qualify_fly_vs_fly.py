"""Bounded primary ZIP inventory; no downloaded code execution."""

import argparse
import hashlib
import io
import json
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw/fly-vs-fly"
RAW.mkdir(exist_ok=True)
RESERVE = 18 * 2**30


def fetch(url, start, end, total):
    size = end - start + 1
    if shutil.disk_usage(RAW).free - size - 64 * 2**20 < RESERVE:
        raise RuntimeError("18 GiB reserve")
    result = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            "120",
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
    headers = result.stderr.decode()
    if [
        line.split()[1]
        for line in headers.splitlines()
        if line.lower().startswith("http/")
    ][
        -1
    ] != "206" or f"content-range: bytes {start}-{end}/{total}" not in headers.lower():
        raise RuntimeError(headers)
    data = result.stdout
    assert len(data) == size
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    record = json.loads((ROOT / "raw/fly-vs-fly-record.json").read_text())
    manifest = {
        "record": "https://data.caltech.edu/records/zrznw-w7386",
        "archives": [],
    }
    for name in ["Aggression.zip", "BoyMeetsBoy_wo_movies.zip", "Courtship.zip"]:
        entry = record["files"]["entries"][name]
        url = entry["links"]["content"]
        total = entry["size"]
        tail = fetch(url, total - 131072, total - 1, total)
        pos = tail.rfind(b"PK\x05\x06")
        endrec = struct.unpack_from("<4s4H2LH", tail, pos)
        cdsize, cdoffset = endrec[5:7]
        central = fetch(url, cdoffset, cdoffset + cdsize - 1, total)
        # The central-directory offsets remain useful even in a standalone reader.
        z = zipfile.ZipFile(io.BytesIO(central + tail[pos:]))
        items = []
        for info in z.infolist():
            if "__MACOSX" in info.filename or not (
                info.filename.endswith(("_track.mat", "_actions.mat"))
                or Path(info.filename).name == "traintest.mat"
            ):
                continue
            assert (
                not Path(info.filename).is_absolute()
                and ".." not in Path(info.filename).parts
            )
            pin = {
                "name": info.filename,
                "offset": info.header_offset + cdoffset - z.start_dir,
                "compressed": info.compress_size,
                "size": info.file_size,
                "crc": info.CRC,
                "method": info.compress_type,
            }
            items.append(pin)
        arc = {
            "name": name,
            "url": url,
            "bytes": total,
            "md5": entry["checksum"],
            "members": items,
        }
        print(
            name,
            len(items),
            sum(p["compressed"] for p in items),
            sum(p["size"] for p in items),
            flush=True,
        )
        if args.download or args.pilot:
            for pin in items:
                if (
                    args.pilot
                    and "/movie1/" not in pin["name"]
                    and not pin["name"].endswith("traintest.mat")
                ):
                    continue
                target = RAW / name.removesuffix(".zip") / pin["name"]
                if target.exists():
                    data = target.read_bytes()
                    if (
                        len(data) == pin["size"]
                        and __import__("zlib").crc32(data) == pin["crc"]
                    ):
                        pin["sha256"] = hashlib.sha256(data).hexdigest()
                        continue
                # Download each exact local header then bounded compressed payload.
                head = fetch(url, pin["offset"], pin["offset"] + 29, total)
                assert head[:4] == b"PK\x03\x04"
                n, e = struct.unpack_from("<HH", head, 26)
                payload = fetch(
                    url,
                    pin["offset"] + 30,
                    pin["offset"] + 29 + n + e + pin["compressed"],
                    total,
                )
                assert payload[:n].decode() == pin["name"]
                import zlib

                data = zlib.decompress(payload[n + e :], -15)
                assert len(data) == pin["size"] and zlib.crc32(data) == pin["crc"]
                pin["sha256"] = hashlib.sha256(data).hexdigest()
                path = RAW / name.removesuffix(".zip") / pin["name"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        manifest["archives"].append(arc)
    (ROOT / "raw/fly-vs-fly-inventory.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
