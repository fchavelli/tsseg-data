"""Build VFDB rhythm states and a separate source-noise interval track."""

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

ID = "vfdb"
SOURCE = "https://physionet.org/content/vfdb/1.0.0/"
BASE = "https://physionet-open.s3.amazonaws.com/vfdb/1.0.0/"
MANIFEST = Path(__file__).parent / "checksums" / "vfdb.json"
CHECKSUMS_SHA256 = "1157e2168f131f2c53e6eb0e3263c0835d286fc05de94066e069e29b810cd6f6"
# Stable source rhythm vocabulary, including codes absent from a selected subset.
RHYTHMS = [
    "AFIB",
    "ASYS",
    "B",
    "BI",
    "HGEA",
    "N",
    "NOD",
    "PM",
    "SBR",
    "SVTA",
    "VER",
    "VF",
    "VFL",
    "VT",
]
ALIASES = {"NSR": "N", "VFIB": "VF"}


def main():
    def extra(parser):
        parser.add_argument(
            "--records",
            nargs="+",
            help="Explicit record subset; default builds all 22.",
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
        sampling_rate_hz=250,
        label_columns={"label_rhythm": pa.int16(), "label_noise": pa.int16()},
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
                    code = ALIASES.get(code, code)
                    assert code in RHYTHMS or code == "NOISE", (sid, code)
                    changes.append((int(sample), code))
            quality = np.full(rec.sig_len, -1, dtype=np.int16)
            current = -1
            for i, (start, code) in enumerate(changes):
                end = changes[i + 1][0] if i + 1 < len(changes) else rec.sig_len
                assert 0 <= start <= end <= rec.sig_len
                if code != "NOISE":
                    current = RHYTHMS.index(code)
                y[start:end] = current
                quality[start:end] = int(code == "NOISE")
            labels = {"label_rhythm": y, "label_noise": quality}
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
        title="MIT-BIH Malignant Ventricular Ectopy Database",
        source="https://doi.org/10.13026/C22P44",
        sha256=CHECKSUMS_SHA256,
        license_spdx="ODC-By-1.0",
        license_url="https://opendatacommons.org/licenses/by/1-0/",
        license_evidence=SOURCE,
        description=f"Two native 250-Hz ECG channels and source rhythm intervals, {len(records)}/22 source records built. Separate noise track follows source continuation semantics.",
        collection="Twenty-two approximately half-hour two-lead ECG recordings from subjects with sustained ventricular tachycardia, flutter or fibrillation, sampled at 250 Hz.",
        annotation="Source .atr files contain rhythm transitions only, not beat labels. Each parenthesised code starts its named episode. Provider explicitly states that the previous rhythm continues through NOISE and noise ends at the next annotation: keep that rhythm unchanged and record noise separately in label_noise (1=noise, 0=other annotated interval). Before the first annotation use -1. ASYS (asystole) and normal sinus N are ordinary clinical states, not null. Canonicalise source aliases NSR->N and VFIB->VF, retaining exact notes separately.",
        conversion="WFDB 4.3.1 decodes physical mV values then float32 without filters/resampling. Both ECG leads retained in positional order with original names in index metadata. Use official public PhysioNet S3 mirror and individual primary SHA256 pins for .dat/.hea/.atr. Preserve every sparse annotation with original sample and text in annotations.parquet. Exclude free-text demographic header comments. --records selects an explicit subset; default builds all 22.",
        limitations="Small historical clinical cohort enriched for malignant ventricular events. Noise is signal quality, not a new cardiac rhythm, and should be masked only as a sensitivity analysis. The retained previous rhythm during noise follows provider interpretation, not a newly inferred annotation. No independent annotator tracks or beat labels are provided.",
        biases="Severe ventricular arrhythmia selection, historical hospital equipment and limited population diversity.",
        personal="Deidentified record IDs, two ECG signals and rhythm annotations retained; demographic/header comments excluded.",
        citation="Greenwald, S. (1999). MIT-BIH Malignant Ventricular Ectopy Database, v1.0.0. PhysioNet. https://doi.org/10.13026/C22P44. Greenwald, Albrecht, Moody and Mark (1985), Computers in Cardiology 12, 383–386.",
        creators=["Greenwald, Scott"],
        date_published="1999-08-03",
        info={
            "state_names": {
                "label_rhythm": dict(enumerate(RHYTHMS)),
                "label_noise": {0: "not marked noise", 1: "noise"},
            },
            "rhythm_aliases": ALIASES,
            "label_origin": "human",
            "source_sha256_manifest": "builders/checksums/vfdb.json",
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
