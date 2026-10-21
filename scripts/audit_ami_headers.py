"""Audit every native primary WAV format using bounded HTTP ranges only."""

import concurrent.futures
import json
import re
import struct
import subprocess
import wave
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1] / "raw/ami-meeting-corpus"
    pins = json.loads((root / "primary-mix-manifest.json").read_text())["files"]

    def inspect(pin):
        path = root / Path(pin["url"]).name
        if path.exists():
            with wave.open(str(path)) as audio:
                rate, channels, width = (
                    audio.getframerate(),
                    audio.getnchannels(),
                    audio.getsampwidth(),
                )
        else:
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "45",
                    "--range",
                    "0-255",
                    "--max-filesize",
                    "256",
                    "-D",
                    "/dev/stderr",
                    pin["url"],
                ],
                capture_output=True,
                check=True,
            )
            data = result.stdout
            assert len(data) == 256 and b"206 Partial Content" in result.stderr
            assert re.search(
                rb"Content-Range: bytes 0-255/" + str(pin["bytes"]).encode(),
                result.stderr,
                re.I,
            )
            assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
            position = 12
            while data[position : position + 4] != b"fmt ":
                size = struct.unpack_from("<I", data, position + 4)[0]
                position += 8 + size + size % 2
                assert position + 24 <= len(data)
            encoding, channels, rate, _, _, bits = struct.unpack_from(
                "<HHIIHH", data, position + 8
            )
            assert encoding == 1
            width = bits // 8
        assert rate == 16000 and channels in {1, 2} and width == 2, (
            path.name,
            rate,
            channels,
            width,
        )
        return {
            "series_id": path.name.split(".")[0],
            "sample_rate_hz": rate,
            "channels": channels,
            "sample_width_bytes": width,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(inspect, pins))
    (root / "native-header-audit.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(len(rows), "headers", [r for r in rows if r["channels"] != 1])


if __name__ == "__main__":
    main()
