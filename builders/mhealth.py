"""Build MHEALTH's ten continuous logs, retaining the documented null state."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "mhealth"
SOURCE = "https://archive.ics.uci.edu/dataset/319/mhealth+dataset"
URL = "https://archive.ics.uci.edu/static/public/319/mhealth+dataset.zip"
SHA256 = "16ad0ce709f3f00df18f348610d15bce0884b79e2143f57f446493673f02b8e0"
CHANNELS = (
    [f"chest_acc_{a}" for a in "xyz"]
    + ["chest_ecg_1", "chest_ecg_2"]
    + [f"left_ankle_{sensor}_{a}" for sensor in ("acc", "gyro", "mag") for a in "xyz"]
    + [f"right_arm_{sensor}_{a}" for sensor in ("acc", "gyro", "mag") for a in "xyz"]
)
STATES = dict(
    enumerate(
        [
            "null",
            "standing still",
            "sitting and relaxing",
            "lying down",
            "walking",
            "climbing stairs",
            "waist bends forward",
            "frontal elevation of arms",
            "knees bending",
            "cycling",
            "jogging",
            "running",
            "jump front and back",
        ]
    )
)


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
        meta_columns={"subject": pa.string(), "source_file": pa.string()},
    )
    stats = Statistics()
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(n for n in archive.namelist() if n.endswith(".log"))
        assert len(files) == 10
        for name in files:
            with archive.open(name) as stream:
                x = pd.read_csv(stream, sep=r"\s+", header=None).to_numpy()
            assert x.shape[1] == 24 and np.isfinite(x).all()
            assert np.equal(x[:, -1], np.floor(x[:, -1])).all()
            y = x[:, -1].astype(np.int16)
            assert set(np.unique(y)) <= set(STATES)
            sid = Path(name).stem
            labels = {"label_activity": y}
            writer.add_series(
                sid,
                {c: x[:, i].astype(np.float32) for i, c in enumerate(CHANNELS)},
                labels=labels,
                meta={"subject": sid.removeprefix("mHealth_"), "source_file": name},
            )
            stats.add(sid, labels)
            print(sid, len(y), flush=True)
    finish(
        args,
        spec,
        writer,
        stats,
        title="MHEALTH (complete continuous recordings)",
        source="https://doi.org/10.24432/C5TW22",
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="Ten continuous subject logs with all 23 motion/ECG channels at 50 Hz, "
        "12 protocol activities and the source null class.",
        collection="Ten volunteers perform twelve physical activities outside the laboratory, "
        "wearing Shimmer2 devices at chest, left ankle and right lower arm. All "
        "modalities including two ECG leads are sampled at 50 Hz; sessions were video recorded.",
        annotation="Source activity codes 1..12 retained. The primary UCI column description "
        "explicitly calls code 0 the null class and does not exclude it: 0 remains an ordinary "
        "state, listed in null_states. It is not missing ground truth. No samples are removed.",
        conversion="One series per original subject log; retain every row and all 23 sensor "
        "columns in source order, cast to float32 without filtering or resampling. The "
        "source column description repeats column 13 for ankle magnetometer X; positional "
        "columns 12..14 supply magnetometer X/Y/Z. No synthetic time or extra recordings.",
        limitations="Small scripted cohort; the null class is broad and may dominate recurrence. "
        "Activity recurrence should also be assessed with null masked as a sensitivity analysis. "
        "No independent annotator tracks or real timestamps are supplied.",
        biases="Ten convenience-sampled volunteers; scripted exercise and sensor placements "
        "limit generalisation to everyday behaviour.",
        personal="Pseudonymous subject IDs, motion signals and two ECG leads retained; no names included.",
        citation="Banos, O., Garcia, R., and Saez, A. (2014). MHEALTH. UCI Machine Learning "
        "Repository. https://doi.org/10.24432/C5TW22.",
        creators=["Banos, Oresti", "Garcia, Rafael", "Saez, Alejandro"],
        date_published="2014-12-06",
        null_states={"label_activity": [0]},
        info={
            "label_origin": "protocol",
            "state_names": {"label_activity": STATES},
            "source_columns": {c: i + 1 for i, c in enumerate(CHANNELS)},
            "source_zero_label_policy": "0 is the documented null class, retained as a scored state",
        },
    )


if __name__ == "__main__":
    main()
