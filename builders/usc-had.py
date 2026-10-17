"""Build USC-HAD locally from the primary archive; never redistribute it."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from scipy.io import loadmat  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "usc-had"
SOURCE = "https://sipi.usc.edu/had/"
URL = SOURCE + "USC-HAD.zip"
# Same primary archive and digest as the frozen TSB-SEG source downloader.
SHA256 = "7b9c1ff39aa5a7055656aa2dbdbb17283a9f1abcf467a8605ec5315b67111341"
CHANNELS = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
NAMES = [
    "Walking Forward",
    "Walking Left",
    "Walking Right",
    "Walking Upstairs",
    "Walking Downstairs",
    "Running Forward",
    "Jumping Up",
    "Sitting",
    "Standing",
    "Sleeping",
    "Elevator Up",
    "Elevator Down",
]
SCOPE = (
    "The primary USC-SIPI download page and archive readme contain no explicit "
    "data licence (verified 2026-10-18). Citation and download availability do "
    "not establish redistribution permission. SOURCE-ONLY: build locally from "
    "USC; do not redistribute until written author permission is obtained."
)


def scalar_text(value):
    return str(np.asarray(value).ravel()[0]).strip()


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=100,
        label_columns={
            "label_activity": pa.int16(),
            "label_source_activity": pa.int16(),
        },
        meta_columns={
            "subject": pa.string(),
            "trial": pa.int16(),
            "n_native_recordings": pa.int16(),
            "artificial_joins": pa.bool_(),
        },
    )
    stats = Statistics()
    recording_rows = []
    discrepancies = {}
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        mat_files = [n for n in archive.namelist() if n.endswith(".mat")]
        assert len(mat_files) == 840
        for subject in range(1, 15):
            for trial in range(1, 6):
                arrays, labels, source_labels = [], [], []
                sid = f"Subject{subject}/trial{trial}"
                offset = 0
                for activity in range(1, 13):
                    name = f"USC-HAD/Subject{subject}/a{activity}t{trial}.mat"
                    # Select only needed variables; demographic fields are neither
                    # loaded into the conversion nor written to any output table.
                    d = loadmat(
                        io.BytesIO(archive.read(name)),
                        variable_names=[
                            "sensor_readings",
                            "activity_number",
                            "activity",
                            "subject",
                            "trial",
                        ],
                    )
                    source_activity = scalar_text(d["activity"])
                    declared = (
                        int(scalar_text(d["activity_number"]))
                        if "activity_number" in d
                        else None
                    )
                    # One file lacks activity_number but explicitly states elevator-up.
                    # Recover from its actual string, never from the expected filename.
                    source_code = (
                        declared
                        if declared is not None
                        else {
                            title.lower().replace(" ", "-"): i
                            for i, title in enumerate(NAMES, 1)
                        }[source_activity.lower()]
                    )
                    assert source_code in range(1, 13)
                    source_subject = int(scalar_text(d["subject"]))
                    source_trial = int(scalar_text(d["trial"]))
                    if (source_subject, declared, source_trial) != (
                        subject,
                        activity,
                        trial,
                    ):
                        discrepancies[name] = {
                            "filename_subject": subject,
                            "filename_activity": activity,
                            "filename_trial": trial,
                            "declared_subject": source_subject,
                            "declared_activity_number": declared,
                            "declared_trial": source_trial,
                            "declared_activity": source_activity,
                        }
                    x = d["sensor_readings"].astype(np.float32)
                    assert x.ndim == 2 and x.shape[1] == 6
                    arrays.append(x)
                    labels.append(np.full(len(x), activity, np.int16))
                    source_labels.append(np.full(len(x), source_code, np.int16))
                    recording_rows.append(
                        {
                            "series_id": sid,
                            "source_file": name,
                            "activity": activity,
                            "source_activity": source_activity,
                            "source_activity_number": declared,
                            "source_subject": source_subject,
                            "source_trial": source_trial,
                            "metadata_discrepancy": name in discrepancies,
                            "start": offset,
                            "end": offset + len(x),
                            "artificial_start": activity > 1,
                        }
                    )
                    offset += len(x)
                x, y = np.concatenate(arrays), np.concatenate(labels)
                dense = {
                    "label_activity": y,
                    "label_source_activity": np.concatenate(source_labels),
                }
                writer.add_series(
                    sid,
                    {c: x[:, j] for j, c in enumerate(CHANNELS)},
                    labels=dense,
                    meta={
                        "subject": str(subject),
                        "trial": trial,
                        "n_native_recordings": 12,
                        "artificial_joins": True,
                    },
                )
                stats.add(sid, dense)
    pq.write_table(
        pa.Table.from_pylist(recording_rows),
        args.out_dir / "recordings.parquet",
        compression="zstd",
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="USC-HAD: source-only benchmark concatenations",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="LicenseRef-USC-HAD-Unlicensed",
        license_url=SOURCE,
        license_evidence=SOURCE,
        description="All 840 native USC-HAD recordings arranged as 70 explicitly artificial "
        "a1-to-a12 concatenations (14 subjects x 5 trials), six hip inertial channels "
        "at 100 Hz. Source-only conversion, demographic fields excluded.",
        collection="MotionNode at front-right hip, 100 Hz, accelerometer +/-6g and "
        "gyroscope +/-500 degrees/s (primary archive Readme.txt). Twelve activities "
        "recorded separately, five trials for each of fourteen subjects.",
        annotation="Default label_activity follows activity IDs in filenames, reproducing "
        "the benchmark's fixed a1..a12 order. label_source_activity separately preserves "
        "MAT activity_number; one missing number is recovered from its explicit elevator-up "
        "string. Subject14/a3t2 declares activity 2/walking-left despite filename a3: both "
        "claims are retained without deciding which is correct. Two source trial fields "
        "also disagree with filenames; all four discrepancies are listed in metadata. "
        "These are alternative source representations, not independent annotators. "
        "Every CP is an artificial join between "
        "separately recorded activities, not a naturally observed transition. "
        "No null or missing ground truth. Original names and offsets retained "
        "for all 840 recordings in recordings.parquet.",
        conversion="Download primary USC archive with the SHA256 pinned by TSB-SEG. "
        "Read sensor_readings and activity identifiers only; cast signals to "
        "float32 with no filtering, interpolation or normalisation. Concatenate "
        "activities 1..12 for each subject/trial to reproduce the benchmark "
        "construction. recordings.parquet preserves exact native recording "
        "boundaries, enabling recovery of all original sensor arrays. Exclude "
        "age, height, weight, dates and other demographic fields from outputs.",
        limitations="Artificial CPs and fixed filename activity order. No recurring state "
        "in either track; the unresolved Subject14/a3t2 disagreement merges two adjacent "
        "activity-2 recordings in the metadata track and removes one label change. "
        "Unsuitable for assessing recognition of recurring states. Protocol-driven cohort. "
        + SCOPE,
        biases="Fourteen-person convenience sample and twelve prescribed daily activities; "
        "fixed concatenation order is a strong benchmark artefact.",
        personal="Only pseudonymous subject/trial IDs and motion retained; age, height, "
        "weight and dates excluded. Motion patterns can still be identifying.",
        citation="Zhang, Mi and Sawchuk, Alexander A. (2012). USC-HAD: A Daily Activity "
        "Dataset for Ubiquitous Activity Recognition Using Wearable Sensors. "
        "UbiComp SAGAware workshop. https://sipi.usc.edu/had/mi_ubicomp_sagaware12.pdf",
        creators=["Zhang, Mi", "Sawchuk, Alexander A."],
        date_published="2012",
        info={
            "use_cases": "CPD on explicitly artificial activity concatenations. No within-series "
            "state recurrence; this construction does not test recognition of recurrent states.",
            "license_scope": SCOPE,
            "license_tier": "C",
            "hf_license": "other",
            "rehosting_allowed": False,
            "label_origin": "concatenation of source activities",
            "native_recordings": 840,
            "artificial_joins": True,
            "state_names": {
                track: {str(i): name for i, name in enumerate(NAMES, 1)}
                for track in spec.label_columns
            },
            "metadata_discrepancies": discrepancies,
            "units": {c: "g" if c.startswith("acc") else "degrees/s" for c in CHANNELS},
            "privacy_dropped_fields": ["age", "height", "weight", "date"],
            "auxiliary": {
                "recordings.parquet": "Native recording source paths, exact "
                "offsets, source activity names and artificial join flags."
            },
        },
    )


if __name__ == "__main__":
    main()
