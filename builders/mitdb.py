"""Build MIT-BIH ECG rhythm segmentation; sparse beat annotations stay sparse."""

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

ID = "mitdb"
SOURCE = "https://physionet.org/content/mitdb/1.0.0/"
BASE = "https://physionet-open.s3.amazonaws.com/mitdb/1.0.0/"
MANIFEST = Path(__file__).parent / "checksums" / "mitdb.json"
CHECKSUMS_SHA256 = "b61158a96d5f2ca80edfb354a9a66a6324836c390a84e1966dcee2b907d6be43"
# Stable source rhythm vocabulary, including codes absent from a selected subset.
RHYTHMS = [
    "N",
    "AB",
    "AFIB",
    "AFL",
    "B",
    "BII",
    "IVR",
    "NOD",
    "P",
    "PREX",
    "SBR",
    "SVTA",
    "T",
    "VFL",
    "VT",
]


def main():
    def extra(parser):
        parser.add_argument(
            "--records",
            nargs="+",
            help="Explicit record subset; default builds all 48.",
        )

    args = parse_args(ID, extra=extra)
    pins = json.loads(MANIFEST.read_text())
    all_records = sorted(n.removesuffix(".dat") for n in pins if n.endswith(".dat"))
    records = sorted(set(args.records or all_records))
    assert records and set(records) <= set(all_records)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["ecg_1", "ecg_2"],
        configs={"default": ["ecg_1", "ecg_2"]},
        sampling_rate_hz=360,
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
            assert rec.fs == 360 and rec.n_sig == 2 and rec.sig_len == 650000
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
        title="MIT-BIH Arrhythmia Database (rhythm segmentation)",
        source="https://doi.org/10.13026/C2F305",
        sha256=CHECKSUMS_SHA256,
        license_spdx="ODC-By-1.0",
        license_url="https://opendatacommons.org/licenses/by/1-0/",
        license_evidence=SOURCE,
        description=f"Two native 360-Hz ECG channels and source rhythm intervals, {len(records)}/48 source records built. All sparse reference annotations retained separately.",
        collection="Forty-eight approximately half-hour ambulatory ECG recordings from 47 subjects, collected at Boston Beth Israel Hospital between 1975 and 1979; 360 Hz, two leads. The source mixes randomly selected excerpts and less common clinically significant arrhythmias.",
        annotation="Use only explicit parenthesised rhythm auxiliary notes from expert-reviewed reference .atr files as dense rhythm boundaries. WFDB zero-based sample positions preserved; before the first explicit rhythm note use -1, and if no rhythm note exists the whole recording stays unlabelled. Rhythm N is a valid normal state, not null. Beat symbols and all other annotations remain sparse in annotations.parquet; never spread beat classifications across time. Reference annotations represent adjudicated labels, not independent annotator tracks.",
        conversion="WFDB 4.3.1 decodes original physical mV values using source calibration, then float32 without filtering, resampling or selecting one lead. Source lead names vary by record and remain in index metadata (ecg_1/ecg_2 retain positional order). Official public PhysioNet S3 transport; all .dat/.hea/.atr source files pinned individually against primary SHA256SUMS.txt. Demographic/free-text header comments excluded. --records explicitly selects a local subset; omit to build all 48.",
        limitations="Clinical selection and small historical cohort; arrhythmia proportions are not population prevalence. Some records have no rhythm changes or no rhythm annotations and contribute little segmentation information. The dense rhythm track does not cover every beat or signal-quality label. Partial builds must be reported as partial.",
        biases="Historical hospital population and deliberate enrichment of uncommon arrhythmias; limited device and demographic diversity.",
        personal="Deidentified record IDs, ECG signals and clinical reference annotations retained. Source demographic/header comments omitted; same patient may occur in multiple records.",
        citation="Moody, G., and Mark, R. (2005). MIT-BIH Arrhythmia Database, v1.0.0. PhysioNet. https://doi.org/10.13026/C2F305. Moody and Mark (2001), IEEE Engineering in Medicine and Biology 20(3), 45–50.",
        creators=["Moody, George", "Mark, Roger"],
        date_published="2005-02-24",
        info={
            "state_names": {"label_rhythm": dict(enumerate(RHYTHMS))},
            "label_origin": "human",
            "source_sha256_manifest": "builders/checksums/mitdb.json",
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
