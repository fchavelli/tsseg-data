"""Regenerate the dataset table of README.md from the registry.

Usage: ``python -I scripts/collection_table.py`` (rewrites the block between the
``datasets:start`` / ``datasets:end`` markers of README.md).

Status: ``built`` when ``builders/<id>.py`` exists and ``build/<id>/`` passes
``scripts/validate.py`` (not re-run here: the status column is updated by hand
through ``STATUS``), ``planned`` otherwise; tier C datasets are built from the
source only until their authors allow re-hosting.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
STATUS = {  # id -> status text, for datasets beyond "planned"
    "hapt": "builder + validated local build (61 raw experiments; licence conflict)",
    "mhealth": "builder + validated build (10 complete logs; null state retained)",
    "pump": "builder + validated build (400 cycles)",
    "skab": "builder + validated build (all 129 source CP markers)",
    "actrectut": "builder + validated build (walk + gesture)",
    "tssb": "builder + validated local build (10/75 recurrent)",
    "has": "builder + validated build (250 series, GPS removed)",
    "pamap2": "builder + validated build (Protocol + Optional; activityID=0 excluded, ~29% unscored)",
    "mocap": "builder + validated local build (14 Barbič trials)",
    "utsa": "builder + validated local build (32 series; 1 recurrent)",
    "usc-had": "builder + validated local build (70 artificial CPD series)",
    "mozilla-perf-cpd-annotations": "builder + validated build",
    "opportunity": "builder + validated build",
    "dreem-dod-h": "builder + validated build (3 of 25 nights)",
}
TASK = {"sd": "SD", "cpd": "CPD", "both": "SD + CPD"}
# English wording for registry fields written in French (the registry is a copy).
LICENSE_EN = {
    "tssb": "BSD-3-Clause (TSSB repo); upstream UCR/UEA rights unresolved",
    "utsa": "none at the source",
    "usc-had": "none at the source",
    "mocap": "CMU motion terms; Barbič labels unlicensed",
    "wesad": "Siegen scientific, non-commercial use; redistribution not granted",
    "bebe": "CC-BY-4.0 (repository); per-species licenses",
    "bee-dance": "none; citation requested",
    "tcpd": "mixed per series (CC BY, CC0, GPL-2.0, OGL, MIT, US PD; 9 not redistributable)",
    "bimacs": "CC0-1.0 (annotations, derived data); RGB-D for scientific use",
    "rtt-ripe-atlas-labelled": "MIT (repository); RIPE Atlas data under RIPE NCC terms",
}
NAME_EN = {
    "utsa": "UCR Time Series Semantic Segmentation Archive (UTSA, FLOSS datasets)",
    "bebe": "BEBE: Bio-logger Ethogram Benchmark (collection of 9 datasets)",
    "rtt-ripe-atlas-labelled": "RTT change detection dataset (RIPE Atlas, manual labels), Shao et al.",
    "ais-fishing-semseg": "Dataset for Semantic Segmentation of Fishing Trajectories (128 AIS trajectories)",
    "ami-meeting-corpus": "AMI Meeting Corpus: diarisation, recurrent speakers (derived-feature track)",
}


def main() -> None:
    short = yaml.safe_load((REPO / "registry" / "shortlist.yaml").read_text())
    rows = ["| Dataset | Domain | Task | License (tier) | Status |", "|---|---|---|---|---|"]
    for d in short["datasets"]:
        entry = yaml.safe_load((REPO / "registry" / "datasets" / f"{d['id']}.yaml").read_text())
        name = NAME_EN.get(d["id"], str(entry.get("name", d["id"]))).replace("|", "/")
        status = STATUS.get(d["id"], "planned")
        if d.get("license_tier") == "C":
            status += "; source-only builder until the authors allow re-hosting"
        elif d.get("contact_needed"):
            status += "; author contact planned"
        rows.append(f"| `{d['id']}`: {name} | {d['domain']} | {TASK.get(d['task'], d['task'])} "
                    f"| {LICENSE_EN.get(d['id'], d['license'])} ({d['license_tier']}) | {status} |")
    readme = REPO / "README.md"
    text = readme.read_text()
    block = "<!-- datasets:start -->\n" + "\n".join(rows) + "\n<!-- datasets:end -->"
    text = re.sub(r"<!-- datasets:start -->.*?<!-- datasets:end -->", block, text, flags=re.S)
    readme.write_text(text)
    print(f"{len(rows) - 2} datasets")


if __name__ == "__main__":
    main()
