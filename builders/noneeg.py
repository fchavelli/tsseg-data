"""Build native 8-Hz nonEEG records; retain 1-Hz physiology as an auxiliary table."""

from __future__ import annotations

import sys
import zipfile
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

ID = "noneeg"
SOURCE = "https://physionet.org/content/noneeg/1.0.0/"
URL = "https://physionet.org/static/published-projects/noneeg/non-eeg-dataset-for-assessment-of-neurological-status-1.0.0.zip"
SHA256 = "6700b0f78f3e2724d9049a3398f9294dc7b15b296284326e13b639bc1792096e"
CHANNELS = ["ax", "ay", "az", "temp", "EDA"]
STATES = {"Relax": 0, "PhysicalStress": 1, "CognitiveStress": 2, "EmotionalStress": 3}


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    native = raw.parent / "native"
    native.mkdir(exist_ok=True)
    with zipfile.ZipFile(raw) as archive:
        for name in archive.namelist():
            filename = Path(name).name
            if filename.startswith("Subject") and filename.endswith(
                (".dat", ".hea", ".atr")
            ):
                (native / filename).write_bytes(archive.read(name))
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=8,
        label_columns={"label_stress": pa.int16()},
        meta_columns={"subject": pa.string(), "native_1hz_length": pa.int64()},
    )
    stats = Statistics()
    secondary = []
    annotation_rows = []
    with DatasetWriter(args.out_dir, spec) as writer:
        for subject in range(1, 21):
            sid = f"Subject{subject}"
            record = wfdb.rdrecord(str(native / f"{sid}_AccTempEDA"))
            slow = wfdb.rdrecord(str(native / f"{sid}_SpO2HR"))
            ann = wfdb.rdann(str(native / f"{sid}_AccTempEDA"), "atr")
            assert record.fs == 8 and slow.fs == 1
            assert record.sig_name == CHANNELS and slow.sig_name == ["SpO2", "hr"]
            assert set(ann.aux_note) <= set(STATES)
            assert np.all(np.diff(ann.sample) > 0) and ann.sample[-1] < record.sig_len
            y = np.full(record.sig_len, -1, dtype=np.int16)
            for i, (start, name) in enumerate(
                zip(ann.sample, ann.aux_note, strict=True)
            ):
                end = (
                    int(ann.sample[i + 1])
                    if i + 1 < len(ann.sample)
                    else record.sig_len
                )
                y[start:end] = STATES[name]
                annotation_rows.append(
                    {
                        "series_id": sid,
                        "sample": int(start),
                        "source_note": name,
                        "state": STATES[name],
                    }
                )
            labels = {"label_stress": y}
            writer.add_series(
                sid,
                {
                    c: record.p_signal[:, i].astype(np.float32)
                    for i, c in enumerate(CHANNELS)
                },
                labels=labels,
                meta={"subject": sid, "native_1hz_length": slow.sig_len},
            )
            stats.add(sid, labels)
            secondary.append(
                {
                    "series_id": sid,
                    "sampling_rate_hz": 1.0,
                    "length": slow.sig_len,
                    "SpO2": slow.p_signal[:, 0].astype(np.float32).tolist(),
                    "hr": slow.p_signal[:, 1].astype(np.float32).tolist(),
                }
            )
            print(sid, record.sig_len, slow.sig_len, ann.sample.tolist(), flush=True)
    schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("sampling_rate_hz", pa.float64()),
            ("length", pa.int64()),
            ("SpO2", pa.list_(pa.float32())),
            ("hr", pa.list_(pa.float32())),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(secondary, schema=schema),
        args.out_dir / "physiology_1hz.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(annotation_rows),
        args.out_dir / "annotations.parquet",
        compression="zstd",
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Non-EEG Dataset for Assessment of Neurological Status",
        source="https://doi.org/10.13026/C26Q2Z",
        sha256=SHA256,
        license_spdx="ODC-By-1.0",
        license_url="https://opendatacommons.org/licenses/by/1-0/",
        license_evidence=SOURCE,
        description="Twenty native 8-Hz acceleration/temperature/EDA recordings with protocol stress states; native 1-Hz SpO2/heart rate preserved separately.",
        collection="Twenty healthy volunteers at University of Texas at Dallas follow relaxation, physical, cognitive and emotional stress protocol. Wrist biosensors record five channels at 8 Hz and a separate two-channel SpO2/heart-rate stream at 1 Hz. Provider reports approval UTD IRB 12-29.",
        annotation="Source WFDB transition annotations define four semantic states: relaxation, physical, cognitive, emotional stress. Mini-emotional stress before cognitive task shares EmotionalStress state. Preserve WFDB zero-based sample positions exactly; samples before first transition remain -1. Final transition extends to record end. No separate null state or annotator tracks.",
        conversion="WFDB 4.3.1 decodes digital signals to physical units using original header gains/baselines; float32 output, no filtering. Five native 8-Hz channels form each main series. Preserve both 1-Hz SpO2/HR channels and all native samples in physiology_1hz.parquet, rather than claim undocumented cross-device synchronisation: lengths differ. Native annotations retained in annotations.parquet. Do not upsample, truncate, align or invent labels for the separate stream. Source demographic header comments and subjectinfo.csv are excluded.",
        limitations="Small scripted healthy cohort; stress protocol is a proxy for subjective neurological status. Native device durations differ and no exact cross-device time synchronisation is established. Main-series recurrence is protocol-induced; four relaxation stages and two emotional-stress stages are not independent assessments.",
        biases="Healthy convenience-sampled volunteers and laboratory tasks; clinical or real-world stress generalisation is unproven.",
        personal="Pseudonymous IDs and physiological signals retained; age, gender, height and weight in source headers and subjectinfo.csv omitted from output.",
        citation="Birjandtalab et al. Non-EEG Dataset for Assessment of Neurological Status, version 1.0.0, PhysioNet (2017). https://doi.org/10.13026/C26Q2Z.",
        creators=[
            "Cogan, Diane",
            "Birjandtalab, Javad",
            "Baran Pouyan, Maziyar",
            "Nourani, Mehrdad",
        ],
        date_published="2017-07-19",
        info={
            "state_names": {"label_stress": {v: k for k, v in STATES.items()}},
            "label_origin": "protocol",
            "native_secondary_channels": ["SpO2", "hr"],
            "native_secondary_rate_hz": 1,
            "auxiliary": {
                "physiology_1hz.parquet": "Unaligned native 1-Hz SpO2 and heart rate, all source samples per subject.",
                "annotations.parquet": "Unmodified zero-based WFDB transition sample locations and source state names.",
            },
        },
    )


if __name__ == "__main__":
    main()
