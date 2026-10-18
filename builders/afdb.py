"""Build all 23 AFDB two-lead ECGs and manual rhythm transitions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import wfdb  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "afdb"
SOURCE = "https://physionet.org/content/afdb/1.0.0/"
BASE = "https://physionet-open.s3.amazonaws.com/afdb/1.0.0/"
MANIFEST = Path(__file__).parent / "checksums" / "afdb.json"
CHECKSUMS_SHA256 = "8f3ab7b38bf0591235680a855d6a7f00fe8fdaf2e457fa4c00edad2c735e0d9a"
# Stable source rhythm vocabulary, including codes absent from a selected subset.
RHYTHMS = ["N", "AFIB", "AFL", "J"]


def main():
    def extra(parser):
        parser.add_argument(
            "--records",
            nargs="+",
            help="Explicit record subset; default builds all 23 signal records.",
        )

    args = parse_args(ID, extra=extra)
    pins = json.loads(MANIFEST.read_text())
    notes = fetch(
        BASE + "notes.txt", "notes.txt", pins["notes.txt"], args.raw_dir, ID
    ).read_text()
    all_records = sorted(n.removesuffix(".dat") for n in pins if n.endswith(".dat"))
    records = sorted(set(args.records or all_records))
    assert records and set(records) <= set(all_records)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["ecg_1", "ecg_2"],
        configs={"default": ["ecg_1", "ecg_2"]},
        sampling_rate_hz=250,
        label_columns={"label_rhythm": pa.int16()},
        meta_columns={"source_leads": pa.list_(pa.string())},
    )
    stats = Statistics()
    annotations = []
    with DatasetWriter(args.out_dir, spec) as writer:
        for sid in records:
            for ext in ["dat", "hea", "atr"]:
                name = f"{sid}.{ext}"
                fetch(BASE + name, name, pins[name], args.raw_dir, ID)
            root = args.raw_dir / ID / sid
            rec = wfdb.rdrecord(str(root))
            ann = wfdb.rdann(str(root), "atr")
            assert rec.fs == 250 and rec.n_sig == 2 and rec.sig_len > 0
            assert rec.units == ["mV", "mV"]
            y = np.full(rec.sig_len, -1, dtype=np.int16)
            changes = []
            for sample, symbol, note, subtype, channel, number in zip(
                ann.sample,
                ann.symbol,
                ann.aux_note,
                ann.subtype,
                ann.chan,
                ann.num,
                strict=True,
            ):
                note = note.rstrip("\x00")
                annotations.append(
                    {
                        "series_id": sid,
                        "sample": int(sample),
                        "symbol": symbol,
                        "aux_note": note,
                        "subtype": int(subtype),
                        "channel": int(channel),
                        "number": int(number),
                    }
                )
                if note.startswith("("):
                    code = note[1:].strip()
                    assert code in RHYTHMS, (sid, code)
                    changes.append((int(sample), RHYTHMS.index(code)))
            for i, (start, state) in enumerate(changes):
                end = changes[i + 1][0] if i + 1 < len(changes) else rec.sig_len
                assert 0 <= start <= end <= rec.sig_len
                y[start:end] = state
            labels = {"label_rhythm": y}
            writer.add_series(
                sid,
                {
                    "ecg_1": rec.p_signal[:, 0].astype(np.float32),
                    "ecg_2": rec.p_signal[:, 1].astype(np.float32),
                },
                labels=labels,
                meta={"source_leads": rec.sig_name},
            )
            stats.add(sid, labels)
            print(sid, len(changes), flush=True)
    pq.write_table(
        pa.Table.from_pylist(annotations),
        args.out_dir / "annotations.parquet",
        compression="zstd",
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="MIT-BIH Atrial Fibrillation Database (all signal records)",
        source="https://doi.org/10.13026/C2MW2D",
        sha256=CHECKSUMS_SHA256,
        license_spdx="ODC-By-1.0",
        license_url="https://opendatacommons.org/licenses/by/1-0/",
        license_evidence=SOURCE,
        description=f"Two native 250-Hz ECG channels and source rhythm intervals, {len(records)}/23 source records built. All source rhythm annotations retained separately.",
        collection="Twenty-five long-term ambulatory ECG recordings from subjects with atrial fibrillation at Boston Beth Israel Hospital; 23 have two signal channels at 250 Hz, approximately ten hours each. Records 00735 and 03665 have annotations only and are excluded from the time-series product.",
        annotation="Use only explicit parenthesised rhythm auxiliary notes from manually prepared reference .atr files as dense rhythm boundaries. WFDB zero-based sample positions preserved; before the first explicit rhythm note use -1, and if no rhythm note exists the whole recording stays unlabelled. AFDB N means all rhythms other than AFIB/AFL/J, not necessarily normal sinus rhythm; retain as an ordinary state. All manual .atr annotations remain sparse in annotations.parquet. Automatic, unaudited .qrs beat detections are excluded from ground truth; source notes identify optional corrected .qrsc beats. Manual reference annotations are a single supplied track, not independent annotator tracks.",
        conversion="WFDB 4.3.1 decodes original physical mV values using source calibration, then float32 without filtering, resampling or selecting one lead. Source lead names vary by record and remain in index metadata (ecg_1/ecg_2 retain positional order). Official public PhysioNet S3 transport; all .dat/.hea/.atr source files pinned individually against primary SHA256SUMS.txt. Demographic/free-text header comments excluded. --records explicitly selects a local subset; omit to build all 23 signal records.",
        limitations="Source notes: 04043 block 39 unreadable; 08405 block 1067 unreadable; 08434 blocks 648/857/894 unreadable (10.24 s per block, replaced by zero by provider). Record06453 ends after about 9 h 15 min; no fixed length assumed. Clinical selection and small historical cohort; arrhythmia proportions are not population prevalence. Some records have no rhythm changes or no rhythm annotations and contribute little segmentation information. The dense rhythm track does not cover every beat or signal-quality label. Partial builds must be reported as partial.",
        biases="Historical hospital population and deliberate enrichment of uncommon arrhythmias; limited device and demographic diversity.",
        personal="Deidentified record IDs, ECG signals and clinical reference annotations retained. Source demographic/header comments omitted; same patient may occur in multiple records.",
        citation="Moody, G., and Mark, R. (2000). MIT-BIH Atrial Fibrillation Database, v1.0.0. PhysioNet. https://doi.org/10.13026/C2MW2D. Moody and Mark (1983), Computers in Cardiology 10, 227–230.",
        creators=["Moody, George", "Mark, Roger"],
        date_published="2000-11-04",
        info={
            "state_names": {"label_rhythm": dict(enumerate(RHYTHMS))},
            "label_origin": "human",
            "provider_notes": notes,
            "source_sha256_manifest": "builders/checksums/afdb.json",
            "built_records": records,
            "available_records": all_records,
            "complete_source": records == all_records,
            "source_sha256_scope": "Primary SHA256SUMS.txt; individual selected file hashes are in the committed builder manifest.",
            "auxiliary": {
                "annotations.parquet": "All sparse source WFDB annotations with exact sample offsets, symbols and auxiliary notes."
            },
        },
    )


if __name__ == "__main__":
    main()
