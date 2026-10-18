"""Build HARTH's complete subject recordings with timestamps and all six axes."""

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

ID = "harth"
SOURCE = "https://archive.ics.uci.edu/dataset/779/harth"
URL = "https://archive.ics.uci.edu/static/public/779/harth.zip"
SHA256 = "2ab54d6b11467ddbe998dfb60355f9f1ae181b0af7a89e7c78bb7af2cf16b64a"
CHANNELS = [f"{site}_{a}" for site in ("back", "thigh") for a in "xyz"]
STATES = {
    1: "walking",
    2: "running",
    3: "shuffling",
    4: "stairs ascending",
    5: "stairs descending",
    6: "standing",
    7: "sitting",
    8: "lying",
    13: "cycling sit",
    14: "cycling stand",
    130: "cycling sit inactive",
    140: "cycling stand inactive",
}


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=50,
        time_column=("t_timestamp", pa.timestamp("ns")),
        label_columns={"label_activity": pa.int16()},
        meta_columns={
            "subject": pa.string(),
            "source_file": pa.string(),
            "dt_s_max": pa.float64(),
        },
    )
    stats = Statistics()
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(n for n in archive.namelist() if n.endswith(".csv"))
        assert len(files) == 22
        for name in files:
            with archive.open(name) as stream:
                data = pd.read_csv(stream)
            assert set(CHANNELS + ["timestamp", "label"]) <= set(data.columns)
            assert not data[CHANNELS + ["timestamp", "label"]].isna().any().any()
            y = data["label"].to_numpy(dtype=np.int16)
            assert np.equal(data["label"], y).all() and set(np.unique(y)) <= set(STATES)
            time = pd.to_datetime(data["timestamp"]).to_numpy(dtype="datetime64[ns]")
            delta = np.diff(time).astype("timedelta64[ns]").astype(np.int64)
            assert np.all(delta > 0)
            sid = Path(name).stem
            labels = {"label_activity": y}
            writer.add_series(
                sid,
                {c: data[c].to_numpy(dtype=np.float32) for c in CHANNELS},
                labels=labels,
                time=time,
                meta={
                    "subject": sid,
                    "source_file": name,
                    "dt_s_max": float(delta.max() / 1e9),
                },
            )
            stats.add(sid, labels)
            print(sid, len(y), float(delta.max() / 1e9), flush=True)
    finish(
        args,
        spec,
        writer,
        stats,
        title="HARTH complete free-living accelerometry",
        source="https://doi.org/10.24432/C5NC90",
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="Twenty-two complete free-living subject recordings with back and thigh acceleration, timestamps and twelve activity codes at nominal 50 Hz.",
        collection="Twenty-two participants wear Axivity AX3 accelerometers on lower back and right front thigh during approximately two hours of free-living activity. Acceleration is provided in g at 50 Hz.",
        annotation="Professionals annotated chest-camera video frame by frame. All supplied activity codes retained, including shuffling and inactive cycling as ordinary states. No null or unlabelled code is defined in the provided labels; no missing ground truth is invented.",
        conversion="One continuous series per source subject CSV, all six source axes cast to float32 without filtering/resampling. Original timestamps retained with nanosecond precision; no sample deletion, interpolation, synthetic concatenation or inferred labels. Additional CSV row-index columns, if present, are not sensor channels.",
        limitations="Small convenience cohort; free-living routines and annotation uncertainty. Nominal rate is 50 Hz; actual timestamp gaps are retained and maximum interval is reported per series. No independent annotator tracks are available.",
        biases="Participants and sensor placements may not represent clinical populations or other wearable placements.",
        personal="Pseudonymous subject identifiers, timestamps and movement signals retained. Source videos and direct identifiers are not included.",
        citation="Logacjov, A., Kongsvold, A., Bach, K., Bårdstu, H., and Mork, P. HARTH. UCI Machine Learning Repository. https://doi.org/10.24432/C5NC90. Logacjov et al. (2021), HARTH: A Human Activity Recognition Dataset for Machine Learning, Sensors 21(23), 7853.",
        creators=[
            "Logacjov, Aleksej",
            "Kongsvold, Atle",
            "Bach, Kerstin",
            "Bårdstu, Hilde Bremseth",
            "Mork, Paul Jarle",
        ],
        date_published="2023-02-20",
        info={
            "state_names": {"label_activity": STATES},
            "label_origin": "human",
            "time_description": "Source CSV timestamps; nominal 50 Hz, gaps retained.",
        },
    )


if __name__ == "__main__":
    main()
