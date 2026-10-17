"""Build UTSA locally using the exact source-file pins of the TSB-SEG downloader."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "utsa"
SOURCE = "https://sites.google.com/site/onlinesemanticsegmentation/"
MANIFEST = Path(__file__).resolve().parent / "checksums" / "utsa.json"
SCOPE = (
    "No explicit data licence is stated on the primary Google Sites page "
    "(checked 2026-10-18). The CLaP repository BSD licence is not treated as "
    "permission for upstream UTSA data. SOURCE-ONLY: no redistribution pending "
    "author permission. The download mirror and per-file SHA256 pins are those "
    "of the frozen TSB-SEG source downloader; no public TSB-SEG files are modified."
)


def main():
    args = parse_args(ID)
    manifest = json.loads(MANIFEST.read_text())
    paths = {
        name: fetch(manifest["base_url"] + name, name, digest, args.raw_dir, ID)
        for name, digest in manifest["files"].items()
    }
    desc = [line.split(",") for line in paths["desc.txt"].read_text().splitlines()]
    props = {
        line.split(",")[0]: [int(s) for s in line.split(",")[1:]]
        for line in paths["properties.txt"].read_text().splitlines()
    }
    assert len(desc) == len(props) == 32
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["value"],
        configs={"default": ["value"]},
        label_columns={"label_state": pa.int16()},
        meta_columns={
            "source_file": pa.string(),
            "window_size": pa.int32(),
            "synthetic": pa.bool_(),
        },
    )
    stats = Statistics()
    states = set()
    with DatasetWriter(args.out_dir, spec) as writer:
        for row in desc:
            sid, window, *boundaries = row
            x = np.loadtxt(paths[sid + ".txt"], dtype=np.float32)
            cp = np.asarray(boundaries, dtype=np.int64)
            values = np.asarray(props[sid], dtype=np.int16)
            assert x.ndim == 1 and len(values) == len(cp) + 1
            assert np.all((cp > 0) & (cp < len(x))) and np.all(np.diff(cp) > 0)
            y = np.repeat(values, np.diff(np.r_[0, cp, len(x)])).astype(np.int16)
            assert np.array_equal(np.flatnonzero(y[1:] != y[:-1]) + 1, cp)
            states.update(values.tolist())
            labels = {"label_state": y}
            writer.add_series(
                sid,
                {"value": x},
                labels=labels,
                meta={
                    "source_file": sid + ".txt",
                    "window_size": int(window),
                    "synthetic": sid == "SimpleSynthetic",
                },
            )
            stats.add(sid, labels)
    digest = sha256(MANIFEST)
    finish(
        args,
        spec,
        writer,
        stats,
        title="UTSA semantic segmentation archive (source-only)",
        source=SOURCE,
        sha256=digest,
        license_spdx="LicenseRef-UTSA-Unlicensed",
        license_url=SOURCE,
        license_evidence=SOURCE,
        description="32 univariate UTSA/FLOSS benchmark series. Local source-only "
        "conversion from the checksum-pinned CLaP mirror used by TSB-SEG.",
        collection="A heterogeneous segmentation benchmark assembled for online semantic "
        "segmentation, including motion, physiological, industrial and animal "
        "signals, plus SimpleSynthetic. Individual physical sample rates vary "
        "and are not asserted globally.",
        annotation="CP positions from mirror desc.txt; mirror properties.txt supplies "
        "local state IDs. These IDs are CLaP repackage labels, not claimed as "
        "original UTSA semantic state annotations. Only SimpleSynthetic repeats "
        "a state; the other series primarily test CPD. No null class or missing "
        "annotation is inferred.",
        conversion="Reuse TSB-SEG downloader URL revision and every SHA256 pin; verify "
        "34 files (32 signals plus desc/properties) before parsing. Read numeric "
        "signals as float32; expand segment labels without scaling/interpolation. "
        "The sourceSha256 field is the SHA256 of builders/checksums/utsa.json, "
        "whose per-file digests are also included in tsseg.json. The CLaP mirror "
        "is a transport source and annotation provider, not a licence authority.",
        limitations="Mostly nonrecurring local state IDs; heterogeneous source domains "
        "and unspecified physical sample rates. Repackage labels must not be "
        "presented as verified original semantic regimes. " + SCOPE,
        biases="Small curated benchmark, overrepresents abrupt changes and a few domains.",
        personal="Some series originate in human physiology or activity measurements. "
        "No demographic or identity fields are added; upstream consent is not re-audited.",
        citation="Gharghabi, S. et al. (2017). Matrix Profile VIII: Domain Agnostic "
        "Online Semantic Segmentation at Superhuman Performance Levels. ICDM. "
        + SOURCE,
        creators=[
            "Gharghabi, Shaghayegh",
            "Ding, Yifei",
            "Yeh, Chin-Chia Michael",
            "Kamgar, Kaveh",
            "Ulanova, Liudmila",
            "Keogh, Eamonn",
        ],
        date_published="2017",
        synthetic=True,
        info={
            "license_scope": SCOPE,
            "license_tier": "C",
            "rehosting_allowed": False,
            "hf_license": "other",
            "label_origin": "repackage (CLaP properties.txt)",
            "transport_source": manifest["base_url"],
            "source_file_sha256": manifest["files"],
            "source_digest_kind": "SHA256 of builders/checksums/utsa.json",
            "state_names": {
                "label_state": {
                    str(s): f"source-local repackage state {s}" for s in sorted(states)
                }
            },
        },
    )


if __name__ == "__main__":
    main()
