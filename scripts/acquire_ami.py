"""Acquire primary AMI WAVs with bounded streaming and record their native SHA pins."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsseg_data.ami import RESERVE, acquire, riff_layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    assert 1 <= args.workers <= 4
    root = Path(__file__).resolve().parents[1]
    raw = root / "raw/ami-meeting-corpus"
    manifest = json.loads((raw / "primary-mix-manifest.json").read_text())
    manifest["audio_downloaded"] = True
    previous = raw / "audio-pins.json"
    if previous.exists():
        old = {p["url"]: p for p in json.loads(previous.read_text())["files"]}
        for pin in manifest["files"]:
            if pin["url"] in old:
                pin.update(old[pin["url"]])
    # Complete cache and deliberately conservative10GiB output, before measured pilot.
    assert (
        shutil.disk_usage(raw).free - manifest["audio_bytes"] - 10 * 2**30 - 64 * 2**20
        >= RESERVE
    )
    selected = [
        pin
        for pin in manifest["files"]
        if not args.pilot
        or Path(pin["url"]).name.split(".")[0]
        in {"ES2002a", "EN2001a", "EN2005a", "ES2011c"}
    ]

    def worker(original):
        pin = dict(original)
        path = acquire(raw, pin, allow_new=True)
        with wave.open(str(path), "rb") as source:
            assert (
                source.getframerate() == 16000
                and source.getnchannels() in {1, 2}
                and source.getsampwidth() == 2
                and source.getcomptype() == "NONE"
            )
            pin.update(
                source_samples=source.getnframes(),
                sample_rate_hz=source.getframerate(),
                channels=source.getnchannels(),
                sample_width_bytes=source.getsampwidth(),
                riff_layout=riff_layout(path),
            )
        return pin

    lookup = {pin["url"]: pin for pin in manifest["files"]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(worker, pin) for pin in selected]
        try:
            for future in concurrent.futures.as_completed(pending):
                pin = future.result()
                lookup[pin["url"]].update(pin)
                temporary = previous.with_suffix(".json.part")
                temporary.write_text(json.dumps(manifest, indent=2) + "\n")
                temporary.replace(previous)
                print(
                    Path(pin["url"]).name.split(".")[0],
                    pin["bytes"],
                    pin["source_samples"],
                    flush=True,
                )
        except BaseException:
            for future in pending:
                future.cancel()
            raise


if __name__ == "__main__":
    main()
