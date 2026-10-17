"""Copy the shortlist and the registry entries of the retained datasets.

Usage: ``python -I scripts/sync_registry.py <notes/datasets dir>``

- ``<notes>/shortlist.yaml`` -> ``registry/shortlist.yaml`` (verbatim);
- for every dataset of the shortlist, its entry in ``<notes>/registry/<file>.yaml``
  -> ``registry/datasets/<id>.yaml`` (text block copied verbatim, comments kept).

The raw per-domain registries (~370 entries, search logs) are not copied.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def entry_block(text: str, ds_id: str) -> str:
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.fullmatch(rf"  - id: {re.escape(ds_id)}\s*", ln):
            start = i
            break
    if start is None:
        raise KeyError(ds_id)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("  - id:") or re.match(r"^[A-Za-z_]+:", lines[j]):
            end = j
            break
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    # de-indent the list item into a mapping
    out = [block[0].replace("  - id:", "id:", 1)]
    out += [ln[4:] if ln.startswith("    ") else ln for ln in block[1:]]
    return "\n".join(out) + "\n"


def main(notes: Path) -> None:
    src = (notes / "shortlist.yaml").read_text()
    (REPO / "registry").mkdir(exist_ok=True)
    (REPO / "registry" / "shortlist.yaml").write_text(src)
    short = yaml.safe_load(src)
    out = REPO / "registry" / "datasets"
    out.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = {}
    for d in short["datasets"]:
        f = d["registry"]
        cache.setdefault(f, (notes / "registry" / f).read_text())
        block = entry_block(cache[f], d["id"])
        yaml.safe_load(block)  # must parse
        header = (f"# Copied from notes/datasets/registry/{f} (phase-1 registry entry),"
                  " not edited here.\n")
        (out / f"{d['id']}.yaml").write_text(header + block)
    print(f"{len(short['datasets'])} entries copied to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
