"""Build the 250 labelled HAS challenge series, dropping location channels."""

from __future__ import annotations

import ast
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

ID = "has"
REVISION = "a77bf78d1ff7e7115e64b2214da809660f99d943"
SOURCE = "https://github.com/patrickzib/human_activity_segmentation_challenge"
URL = f"https://codeload.github.com/patrickzib/human_activity_segmentation_challenge/zip/{REVISION}"
SHA256 = "09218285c2006e941ff6d013cc301eff51c03b6e20a0e7a9a1002c58730d9a8e"
CHANNELS = {
    f"{sensor}_{axis}": f"{axis}-{sensor}"
    for sensor in ["acc", "gyro", "mag"]
    for axis in "xyz"
}


def numbers(value, dtype):
    """Parse only numeric list text; never execute provider eval-based loaders."""
    if pd.isna(value) or value == "":
        return np.array([], dtype=dtype)
    assert value.startswith("[") and value.endswith("]")
    return np.fromstring(value[1:-1], sep=",", dtype=dtype)


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=list(CHANNELS),
        configs={"default": list(CHANNELS)},
        sampling_rate_hz=50,
        label_columns={"label_activity": pa.int16()},
        meta_columns={
            "subject": pa.string(),
            "routine": pa.string(),
            "group": pa.string(),
            "challenge_id": pa.int32(),
            "n_source_channels": pa.int16(),
            "source_file": pa.string(),
        },
    )
    stats = Statistics()
    with zipfile.ZipFile(raw) as archive:
        member = next(
            n for n in archive.namelist() if n.endswith("/has2023_master.csv.zip")
        )
        with zipfile.ZipFile(io.BytesIO(archive.read(member))) as master:
            csv = master.namelist()[0]
            # Global exact names avoid the lossy per-series re-indexing of CLaP.
            with master.open(csv) as stream:
                name_rows = pd.read_csv(stream, usecols=["activities"])
            state_names = sorted(
                {s for text in name_rows.activities for s in ast.literal_eval(text)}
            )
            assert len(state_names) == 100
            codes = {s: i for i, s in enumerate(state_names)}
            keep = [
                "ts_id",
                "ts_challenge_id",
                "subject",
                "routine",
                "group",
                "split",
                "activities",
                "change_points",
                *CHANNELS.values(),
            ]
            with (
                master.open(csv) as stream,
                DatasetWriter(args.out_dir, spec) as writer,
            ):
                for frame in pd.read_csv(stream, usecols=keep, chunksize=1):
                    row = frame.iloc[0]
                    signal = {
                        c: numbers(row[source], np.float32)
                        for c, source in CHANNELS.items()
                    }
                    n = len(signal["acc_x"])
                    present = sum(len(v) == n for v in signal.values())
                    assert present in (6, 9) and all(
                        len(v) in (0, n) for v in signal.values()
                    )
                    signal = {
                        c: v if len(v) else np.full(n, np.nan, np.float32)
                        for c, v in signal.items()
                    }
                    cp = np.asarray(ast.literal_eval(row.change_points), dtype=np.int64)
                    activities = ast.literal_eval(row.activities)
                    assert len(activities) == len(cp) + 1
                    assert np.all((cp > 0) & (cp < n)) and np.all(np.diff(cp) > 0)
                    y = np.repeat(
                        [codes[s] for s in activities], np.diff(np.r_[0, cp, n])
                    ).astype(np.int16)
                    sid = f"TS{int(row.ts_id)}"
                    labels = {"label_activity": y}
                    writer.add_series(
                        sid,
                        signal,
                        labels=labels,
                        split=row["split"],
                        meta={
                            "subject": str(row.subject),
                            "routine": str(row.routine),
                            "group": row.group,
                            "challenge_id": int(row.ts_challenge_id),
                            "n_source_channels": present,
                            "source_file": "datasets/has2023_master.csv.zip:" + csv,
                        },
                    )
                    stats.add(sid, labels)
    assert len(stats.rows) == 250
    finish(
        args,
        spec,
        writer,
        stats,
        title="Human Activity Segmentation Challenge 2023",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="CC-BY-NC-SA-4.0",
        license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
        license_evidence=f"{SOURCE}/blob/{REVISION}/LICENSE",
        description="250 labelled smartphone motion recordings from the ECML/PKDD 2023 "
        "challenge, 100 activity names preserved globally, all inertial channels, "
        "location and speed removed. Noncommercial share-alike licence.",
        collection="Smartphone motion collected and annotated in a student project in "
        "indoor/outdoor daily routines; provider README specifies 50 Hz. "
        "The master CSV has 250 recordings, public/private challenge splits.",
        annotation="Dense labels expand provider change_points and exact activity-name "
        "sequences. A global alphabetically sorted mapping preserves the 100 "
        "original names across recordings. transition is an ordinary null/transition "
        "state; rest, wait and break activities are ordinary named states. "
        "No label is replaced by -1. No independent annotators are provided.",
        conversion="Read only labelled master CSV and non-location columns, parse list "
        "literals safely (never execute the provider eval loader), cast signals "
        "to float32. No extra interpolation or scaling. Preserve 125 public and "
        "125 private split assignments and both original/challenge IDs. "
        "Absent outdoor gyroscopes are NaN padding, n_source_channels records "
        "six versus nine. Exclude latitude, longitude and speed from all outputs.",
        limitations="Small convenience cohort and scripted routines. Names include fine "
        "context and route actions; class balance and recurrence vary strongly. "
        "GPS removal does not make motion or contextual labels anonymous.",
        biases="Student convenience sample and restricted geographic/activity contexts.",
        personal="Pseudonymous subject/routine IDs and activity names retained; latitude, "
        "longitude and speed are excluded. Motion patterns and context may remain identifying.",
        citation="Ermshaus, Arik et al. (2023). Human Activity Segmentation Challenge @ "
        "ECML/PKDD'23. AALTD, pp. 3–13. https://doi.org/10.1007/978-3-031-49896-1_1",
        creators=[
            "Ermshaus, Arik",
            "Schafer, Patrick",
            "Bagnall, Anthony",
            "Guyet, Thomas",
            "Ifrim, Georgiana",
            "Lemaire, Vincent",
            "Leser, Ulf",
            "Leverger, Colin",
            "Malinowski, Simon",
        ],
        date_published="2023",
        null_states={"label_activity": [codes["transition"]]},
        info={
            "reference_doi": "https://doi.org/10.1007/978-3-031-49896-1_1",
            "source_revision": REVISION,
            "state_names": {"label_activity": dict(enumerate(state_names))},
            "source_columns": CHANNELS,
            "privacy_dropped_columns": ["lat", "lon", "speed"],
            "splits": {
                "public": "original challenge public",
                "private": "original challenge private",
            },
        },
    )


if __name__ == "__main__":
    main()
