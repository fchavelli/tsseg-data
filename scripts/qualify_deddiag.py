"""Audit every primary DEDDIAG annotation member with bounded ZIP ranges only."""

import concurrent.futures
import hashlib
import json
import re
import struct
import subprocess
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw/deddiag"


def interval(pin, first, last):
    assert 0 <= first <= last < pin["size"] and last - first < 16 * 2**20
    response = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--retry",
            "3",
            "--max-time",
            "60",
            "--range",
            f"{first}-{last}",
            "--max-filesize",
            str(last - first + 1),
            "-D",
            "/dev/stderr",
            pin["download_url"],
        ],
        capture_output=True,
        check=True,
    )
    assert len(response.stdout) == last - first + 1
    assert re.findall(rb"^HTTP/\S+ (\d+)", response.stderr, re.M)[-1] == b"206"
    span = re.findall(
        rb"^Content-Range: bytes (\d+)-(\d+)/(\d+)", response.stderr, re.M | re.I
    )[-1]
    assert tuple(map(int, span)) == (first, last, pin["size"])
    return response.stdout


def audit(pin):
    local = RAW / pin["name"]
    selected, members = {}, []
    if local.exists():
        with zipfile.ZipFile(local) as archive:
            for entry in archive.infolist():
                members.append(
                    {
                        "name": entry.filename,
                        "bytes": entry.file_size,
                        "compressed_bytes": entry.compress_size,
                        "crc32": f"{entry.CRC:08x}",
                    }
                )
                if (
                    entry.filename.endswith("items.tsv")
                    or entry.filename.endswith("_annotations.tsv")
                    or entry.filename.endswith("_annotation_labels.tsv")
                ):
                    selected[entry.filename] = archive.read(entry).decode("utf-8")
    else:
        first = max(0, pin["size"] - 65536)
        data = interval(pin, first, pin["size"] - 1)
        end = data.rfind(b"PK\x05\x06")
        directory = struct.unpack_from("<4s4H2IH", data, end)
        count, length, offset = directory[4:7]
        assert offset >= first and offset + length <= pin["size"]
        position = offset - first
        for _ in range(count):
            entry = struct.unpack_from("<4s6H3I5H2I", data, position)
            assert entry[0] == b"PK\x01\x02"
            n, extra, comment = entry[10:13]
            name = data[position + 46 : position + 46 + n].decode("utf-8")
            members.append(
                {
                    "name": name,
                    "bytes": entry[9],
                    "compressed_bytes": entry[8],
                    "crc32": f"{entry[7]:08x}",
                }
            )
            position += 46 + n + extra + comment
            if (
                name.endswith("items.tsv")
                or name.endswith("_annotations.tsv")
                or name.endswith("_annotation_labels.tsv")
            ):
                a = entry[-1]
                b = min(pin["size"] - 1, a + 30 + n + 65536 + entry[8] - 1)
                body = interval(pin, a, b)
                header = struct.unpack_from("<4s5H3I2H", body)
                assert header[0] == b"PK\x03\x04"
                start = 30 + header[-2] + header[-1]
                compressed = body[start : start + entry[8]]
                content = (
                    zlib.decompress(compressed, -15) if header[3] == 8 else compressed
                )
                assert len(content) == entry[9] and zlib.crc32(content) == entry[7]
                selected[name] = content.decode("utf-8")
    return pin["name"], {
        "members": members,
        "selected_text": selected,
        "member_sha256": {
            name: hashlib.sha256(text.encode()).hexdigest()
            for name, text in selected.items()
        },
    }


def main():
    record = json.loads((RAW / "record-20261021.json").read_text())
    pins = [pin for pin in record["files"] if pin["name"].endswith(".zip")]
    assert len(pins) == 15
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = dict(pool.map(audit, pins))
    (RAW / "metadata-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Audited",
        len(result),
        "houses;",
        sum(len(v["selected_text"]) for v in result.values()),
        "metadata members; no demographics or data rows exported",
    )


if __name__ == "__main__":
    main()
