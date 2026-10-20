"""Qualify complete HA4M native sources with a bounded, lossless gzip cache.

Requires prior public WebDAV skeleton/label size metadata and representative
pilots in raw/ha4m. This is an explicit source-qualification command, not a
builder that silently accepts new inputs. It writes pins only after all trials.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsseg_data.ha4m import (  # noqa: E402
    RESERVE,
    acquire,
    decode,
    qualify_label_associations,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=Path("raw/ha4m"))
    p.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=2)
    args = p.parse_args()
    root = args.raw_dir
    sizes = json.loads((root / "skeleton-sizes.json").read_text())
    pilots = json.loads((root / "representative-pilots.json").read_text())
    assert len(sizes) == 217 and len(pilots) == 3
    assert {x["trial"] for x in pilots} == {"IDU001V001", "IDU034V006", "IDU017V003"}
    cache_ratio = max(
        0.45, max(x["gzip_cache_bytes"] / x["source_bytes"] for x in pilots)
    )
    output_ratio = max(0.27, max(x["output_bytes"] / x["source_bytes"] for x in pilots))
    total = sum(x["skeleton_bytes"] for x in sizes)
    pins_path = root / "qualified-trials.json"
    pins = json.loads(pins_path.read_text()) if pins_path.exists() else {}

    def qualify(source):
        trial = source["trial"]
        raw, labels, info = acquire(
            root, trial, source["skeleton_bytes"], pins.get(trial)
        )
        assert info["source_bytes"] == source["skeleton_bytes"]
        assert info["label_bytes"] == source["label_bytes"]
        x, timestamps, bodies, action, repetition, unassigned = decode(raw, labels)
        assert len(x) > 0
        info.update(
            {
                "frames": len(x),
                "missing_skeletons": int((bodies == -1).sum()),
                "missing_labels": int((action == -1).sum()),
                "unassigned_skeleton_blocks": len(unassigned),
                "source_skeleton_blocks": int((bodies >= 0).sum()) + len(unassigned),
                "ambiguous_frames": len(
                    {
                        v["frame_id"]
                        for v in unassigned
                        if v["reason"] == "multiple_valid_body_ids"
                    }
                ),
                "invalid_sdk_blocks": sum(
                    v["reason"] == "invalid_sdk_body_id" for v in unassigned
                ),
            }
        )
        return trial, info

    # One source-qualification job, at most four bounded trial responses in RAM.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(sizes), args.workers):
            remaining = sum(
                x["skeleton_bytes"]
                for x in sizes
                if not (root / f"{x['trial']}.zip.gz").exists()
            )
            budget = (
                remaining * cache_ratio * 1.25
                + total * output_ratio * 1.25
                + 96 * 2**20
            )
            free = shutil.disk_usage(root).free
            if free - budget < RESERVE:
                raise RuntimeError(
                    f"Full source+output projection breaches reserve: {(free - budget) / 2**30:.3f}GiB"
                )
            futures = [
                pool.submit(qualify, source)
                for source in sizes[offset : offset + args.workers]
            ]
            for future in as_completed(futures):
                trial, info = future.result()
                pins[trial] = info
                pins_path.write_text(
                    json.dumps(dict(sorted(pins.items())), indent=2) + "\n"
                )
                cache_ratio = max(
                    cache_ratio, info["gzip_cache_bytes"] / info["source_bytes"]
                )
                print(
                    f"{len(pins)}/217 {trial}: {info['frames']} frames; free={free / 2**30:.3f}GiB projected={(free - budget) / 2**30:.3f}GiB",
                    flush=True,
                )
    corrections = qualify_label_associations(root, pins)
    target = Path(__file__).resolve().parents[1] / "builders/checksums/ha4m.json"
    target.write_text(
        json.dumps(
            {
                "source_version": "primary ownCloud snapshot 2026-10-20",
                "canonical_digest": "sha256 of sorted UTF-8 native member names with uint32-LE length, uint64-LE byte length, then bytes; directory entries excluded",
                "source_bytes": total,
                "cache_ratio_floor": cache_ratio,
                "output_ratio_floor": output_ratio,
                "trials": dict(sorted(pins.items())),
                "corrected_label_associations": corrections,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
