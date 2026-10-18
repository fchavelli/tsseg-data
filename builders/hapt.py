"""Build continuous HAPT raw experiments with all twelve activity codes."""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "hapt"
SOURCE = "https://archive.ics.uci.edu/dataset/341/smartphone+based+recognition+of+human+activities+and+postural+transitions"
URL = "https://archive.ics.uci.edu/static/public/341/smartphone+based+recognition+of+human+activities+and+postural+transitions.zip"
SHA256 = "4ac4ae064227c07045a99551876b54d204837e995e298b6488559e209b3deb09"
CHANNELS = [f"{sensor}_{a}" for sensor in ("acc", "gyro") for a in "xyz"]


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=50,
        label_columns={"label_activity": pa.int16()},
        meta_columns={"subject": pa.string(), "experiment": pa.int16()},
    )
    stats = Statistics()
    with zipfile.ZipFile(raw) as outer:
        nested = [n for n in outer.namelist() if n.endswith(".zip")]
        archive = (
            zipfile.ZipFile(io.BytesIO(outer.read(nested[0]))) if nested else outer
        )
        names = archive.namelist()

        def unique(suffix):
            found = [n for n in names if n.endswith(suffix)]
            assert len(found) == 1, (suffix, found)
            return found[0]

        intervals = np.loadtxt(
            io.BytesIO(archive.read(unique("RawData/labels.txt"))), dtype=int
        )
        state_text = archive.read(unique("activity_labels.txt")).decode()
        states = {
            int(line.split()[0]): " ".join(line.split()[1:])
            for line in state_text.splitlines()
            if line.strip()
        }
        assert set(states) == set(range(1, 13))
        split_subjects = {}
        for split, directory in [("train", "Train"), ("test", "Test")]:
            member = unique(f"{directory}/subject_id_{split}.txt")
            for subject in np.unique(
                np.loadtxt(io.BytesIO(archive.read(member)), dtype=int)
            ):
                assert int(subject) not in split_subjects
                split_subjects[int(subject)] = split
        acc_files = sorted(
            n for n in names if re.search(r"RawData/acc_exp\d+_user\d+\.txt$", n)
        )
        with DatasetWriter(args.out_dir, spec) as writer:
            for name in acc_files:
                exp, subject = map(
                    int, re.search(r"acc_exp(\d+)_user(\d+)\.txt$", name).groups()
                )
                acc = np.loadtxt(io.BytesIO(archive.read(name)))
                gyro = np.loadtxt(
                    io.BytesIO(archive.read(name.replace("/acc_", "/gyro_")))
                )
                assert acc.shape == gyro.shape and acc.shape[1] == 3
                x = np.column_stack((acc, gyro)).astype(np.float32)
                assert np.isfinite(x).all()
                y = np.full(len(x), -1, dtype=np.int16)
                rows = intervals[intervals[:, 0] == exp]
                assert len(rows) and np.all(rows[:, 1] == subject)
                for _, _, activity, start, end in rows:
                    assert activity in states and 1 <= start <= end <= len(y)
                    # Provider sample numbers interpreted as one-based inclusive endpoints.
                    assert np.all(y[start - 1 : end] == -1)
                    y[start - 1 : end] = activity
                sid = f"exp{exp:02d}_user{subject:02d}"
                labels = {"label_activity": y}
                writer.add_series(
                    sid,
                    {c: x[:, i] for i, c in enumerate(CHANNELS)},
                    labels=labels,
                    split=split_subjects[subject],
                    meta={"subject": f"user{subject:02d}", "experiment": exp},
                )
                stats.add(sid, labels)
                print(sid, len(y), flush=True)
        if nested:
            archive.close()
    finish(
        args,
        spec,
        writer,
        stats,
        title="HAPT continuous raw inertial recordings",
        source="https://doi.org/10.24432/C54G7M",
        sha256=SHA256,
        license_spdx="LicenseRef-HAPT-Source-Terms",
        license_url=SOURCE,
        license_evidence=SOURCE,
        description="Continuous raw waist-smartphone experiments with six inertial axes and twelve activity/postural-transition codes at 50 Hz.",
        collection="Thirty volunteers wear a waist-mounted Samsung Galaxy S II and perform a scripted activity protocol; accelerometer and gyroscope capture at 50 Hz.",
        annotation="Manual video-derived RawData/labels.txt intervals. Preserve the six basic activities and all six postural transitions as ordinary states. Samples outside the annotated intervals remain in place with -1; no null class is invented. Source sample numbers are interpreted as one-based inclusive start/end points.",
        conversion="Use continuous RawData accelerometer and gyroscope logs, not overlapping windows or 561-feature vectors. Retain all samples and all six axes, cast to float32 without filters. Acceleration units are g; angular velocity units are rad/s. Subject-disjoint train/test membership is recovered from the original subject_id lists. Preserve source interval table as source annotation reference via pinned archive.",
        limitations="Scripted small cohort. Provider labels do not explicitly spell out indexing origin: conversion declares the one-based inclusive convention; boundary locations have a possible one-sample convention uncertainty. Unannotated gaps must be ignored without reconnecting intervals.",
        biases="Thirty adult volunteers and fixed phone location/protocol; limited coverage of unconstrained activities.",
        personal="Pseudonymous user IDs and inertial signals retained; no raw video or participant demographics included.",
        citation="Reyes-Ortiz, J., Anguita, D., Oneto, L., and Parra, X. (2015). Smartphone-Based Recognition of Human Activities and Postural Transitions. UCI. https://doi.org/10.24432/C54G7M.",
        creators=[
            "Reyes-Ortiz, Jorge",
            "Anguita, Davide",
            "Oneto, Luca",
            "Parra, Xavier",
        ],
        date_published="2015-07-28",
        info={
            "hf_license": "other",
            "license_scope": "UCI displays CC BY 4.0, but the primary archive README v2.1 prohibits commercial use. Conflicting terms: conservatively tier C, source-only until clarified; do not redistribute.",
            "rehosting_allowed": False,
            "state_names": {"label_activity": states},
            "interval_convention": "one-based inclusive source sample numbers; -1 outside intervals",
            "label_origin": "human",
        },
    )


if __name__ == "__main__":
    main()
