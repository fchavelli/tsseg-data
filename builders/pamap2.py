"""Build complete PAMAP2 Protocol + Optional; activity 0 is unscored (-1)."""

from __future__ import annotations

import io
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

ID = "pamap2"
SOURCE = "https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring"
URL = "https://archive.ics.uci.edu/static/public/231/pamap2+physical+activity+monitoring.zip"
SHA256 = "76b3580bd5a804121f507717cb498c66a312ef5c774f4a78ac470e6558add352"
STATES = {
    1: "lying",
    2: "sitting",
    3: "standing",
    4: "walking",
    5: "running",
    6: "cycling",
    7: "Nordic walking",
    9: "watching TV",
    10: "computer work",
    11: "car driving",
    12: "ascending stairs",
    13: "descending stairs",
    16: "vacuum cleaning",
    17: "ironing",
    18: "folding laundry",
    19: "house cleaning",
    20: "playing soccer",
    24: "rope jumping",
}


def channel_columns():
    channels = {"heart_rate": 2}
    for placement, offset in [("hand", 3), ("chest", 20), ("ankle", 37)]:
        names = [
            "temperature",
            *[f"acc_16g_{a}" for a in "xyz"],
            *[f"acc_6g_{a}" for a in "xyz"],
            *[f"gyro_{a}" for a in "xyz"],
            *[f"mag_{a}" for a in "xyz"],
            *[f"orientation_{i}" for i in range(1, 5)],
        ]
        channels.update(
            {f"{placement}_{name}": offset + i for i, name in enumerate(names)}
        )
    assert len(channels) == 52
    return channels


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    columns = channel_columns()
    channels = list(columns)
    default = [c for c in channels if "_acc_16g_" in c]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=channels,
        configs={"default": default, "full": channels},
        sampling_rate_hz=100,
        time_column=("t_seconds", pa.float64()),
        label_columns={"label_activity": pa.int16()},
        meta_columns={
            "subject": pa.string(),
            "session": pa.string(),
            "source_file": pa.string(),
            "nan_share_default": pa.float64(),
            "nan_share_full": pa.float64(),
            "dt_s_max": pa.float64(),
        },
    )
    stats = Statistics()
    with zipfile.ZipFile(raw) as outer:
        nested = [n for n in outer.namelist() if n.endswith("PAMAP2_Dataset.zip")]
        archive = (
            zipfile.ZipFile(io.BytesIO(outer.read(nested[0]))) if nested else outer
        )
        with DatasetWriter(args.out_dir, spec) as writer:
            files = sorted(n for n in archive.namelist() if n.endswith(".dat"))
            assert any("/Protocol/" in n for n in files) and any(
                "/Optional/" in n for n in files
            )
            for name in files:
                with archive.open(name) as stream:
                    x = pd.read_csv(
                        stream, sep=r"\s+", header=None, dtype=np.float64
                    ).to_numpy()
                assert x.shape[1] == 54
                source_y = x[:, 1]
                assert set(np.unique(source_y)) <= set(STATES) | {0}
                y = source_y.astype(np.int16)
                y[y == 0] = -1
                signal = {c: x[:, j].astype(np.float32) for c, j in columns.items()}
                session, filename = name.split("/")[-2:]
                subject = Path(filename).stem
                sid = f"{session}/{subject}"
                labels = {"label_activity": y}
                assert np.all(np.diff(x[:, 0]) > 0)
                writer.add_series(
                    sid,
                    signal,
                    labels=labels,
                    time=x[:, 0],
                    meta={
                        "subject": subject,
                        "session": session,
                        "source_file": name,
                        "nan_share_default": float(
                            np.mean([np.isnan(signal[c]).mean() for c in default])
                        ),
                        "nan_share_full": float(np.isnan(x[:, 2:]).mean()),
                        "dt_s_max": float(np.diff(x[:, 0]).max()),
                    },
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
        title="PAMAP2 Physical Activity Monitoring (complete)",
        source="https://doi.org/10.24432/C5NW2H",
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="Complete PAMAP2 Protocol and Optional sessions; 9-channel accelerometer "
        "default and all 52 source channels in full. Activity 0 is unscored (-1).",
        collection="Nine participants wearing three IMUs (dominant wrist, chest, dominant "
        "ankle) at nominal 100 Hz, plus heart-rate monitor at approximately 9 Hz. "
        "Protocol has twelve activities; Optional recordings add six activities.",
        annotation="Source GUI activity codes retained for 18 named activities. Source readme "
        "explicitly excludes activityID=0 from every analysis: these points map "
        "to -1 and remain in place. They include transient movements and joins "
        "between interrupted recordings. No null class is scored as a state.",
        conversion="All Protocol and Optional source .dat sessions, one series per session. "
        "Retain timestamps; source numeric values cast to float32, no interpolation "
        "or normalisation. Preserve NaN packet losses and sparse heart-rate readings. "
        "Default selects three +/-16g accelerometers (9 axes), recommended over "
        "the less calibrated +/-6g sensors. Full retains all 52 attributes including "
        "the 12 orientation components explicitly marked INVALID by the provider; "
        "these must not be used as valid orientation measurements.",
        limitations="Small cohort; scripted activities, wireless packet loss and interrupted "
        "recordings. Heart rate is approximately 9 Hz embedded in a 100 Hz grid "
        "with NaNs. Orientation channels are invalid. Evaluation must ignore -1 "
        "rather than reconnect separated labelled intervals.",
        biases="DFKI employee/student convenience sample, mostly male; scripted routines.",
        personal="Pseudonymous subject IDs and physiological/motion signals retained. The "
        "separate per-subject demographic PDF is not included in output.",
        citation="Reiss, Attila (2012). PAMAP2 Physical Activity Monitoring. UCI Machine "
        "Learning Repository. https://doi.org/10.24432/C5NW2H. Reiss and Stricker "
        "(2012), Introducing a New Benchmarked Dataset for Activity Monitoring, ISWC.",
        creators=["Reiss, Attila"],
        date_published="2012-08-05",
        info={
            "label_origin": "protocol",
            "state_names": {"label_activity": STATES},
            "source_columns": {c: i + 1 for c, i in columns.items()},
            "invalid_channels": [c for c in channels if "_orientation_" in c],
            "time_description": "Source timestamp in seconds; source grid nominally 0.01 s.",
            "source_zero_label_policy": "activityID 0 -> -1 per source readme section II.2",
        },
    )


if __name__ == "__main__":
    main()
