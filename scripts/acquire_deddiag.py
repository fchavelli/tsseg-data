"""Acquire all fifteen primary DEDDIAG archives with atomic per-file SHA pins."""

from __future__ import annotations

import concurrent.futures
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsseg_data.deddiag import acquire, storage_gate


def download(root, pin):
    completed = dict(pin)
    acquire(root, completed, True)
    return completed


def main():
    root = Path("raw/deddiag")
    pin_path = Path("builders/checksums/deddiag.json")
    checkpoint = root / "complete-pins.json"
    pins = json.loads(pin_path.read_text())
    if checkpoint.exists():
        old = json.loads(checkpoint.read_text())
        for pin, prior in zip(pins["files"], old["files"], strict=True):
            assert all(
                pin[key] == prior[key] for key in ("name", "size", "computed_md5")
            )
            if "sha256" in prior:
                assert "sha256" not in pin or pin["sha256"] == prior["sha256"]
                pin["sha256"] = prior["sha256"]
    print("Initial full corpus storage gate", storage_gate(root, pins), flush=True)
    # This is one acquisition job; four bounded requests use at most128MiB bodies.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        pending = {executor.submit(download, root, pin): pin for pin in pins["files"]}
        for future in concurrent.futures.as_completed(pending):
            pending[future].update(future.result())
            temporary = checkpoint.with_suffix(".json.part")
            temporary.write_text(json.dumps(pins, indent=2) + "\n")
            temporary.replace(checkpoint)
            print(
                "Complete",
                pending[future]["name"],
                pending[future]["sha256"],
                flush=True,
            )
    assert all("sha256" in pin for pin in pins["files"])
    print(
        "All15 complete archives MD5/SHA verified; full output gate",
        storage_gate(root, pins),
        flush=True,
    )


if __name__ == "__main__":
    main()
