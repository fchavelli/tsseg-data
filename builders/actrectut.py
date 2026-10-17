"""Build both walk and gesture ActRecTut subsets, preserving every source column."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
from scipy.io import loadmat  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "actrectut"
REVISION = "6d65a5a646f9d12ac45509db9dfe59c01f3183e4"
SOURCE = "https://codeberg.org/andreas-bulling/ActRecTut"
URL = f"{SOURCE}/archive/{REVISION}.zip"
SHA256 = "6a8a1346bcdc640db7b0b07aced0c9531a8762cd024ed55ae245b06cdb260e86"
CLASSES = {
    "walk": ["NULL", "sitting", "standing", "walk horizontal", "walk down", "walk up"],
    "gesture": [
        "NULL",
        "Open window",
        "Drink",
        "Water plant",
        "Close window",
        "Cut",
        "Chop",
        "Stir",
        "Book",
        "Forehand",
        "Backhand",
        "Smash",
    ],
}


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    channels = [f"source_col_{i:02d}" for i in range(1, 25)]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=channels,
        configs={"default": channels},
        sampling_rate_hz=32,
        label_columns={"label_activity": pa.int16()},
        meta_columns={
            "subject": pa.string(),
            "subset": pa.string(),
            "source_file": pa.string(),
            "n_source_channels": pa.int16(),
        },
    )
    stats = Statistics()
    names = {
        str(i + 1 + (100 if subset == "gesture" else 0)): f"{subset}: {name}"
        for subset, classes in CLASSES.items()
        for i, name in enumerate(classes)
    }
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        members = sorted(n for n in archive.namelist() if n.endswith("/data.mat"))
        assert len(members) == 4
        for name in members:
            data = loadmat(io.BytesIO(archive.read(name)))
            x, source_y = data["data"], data["labels"].ravel()
            sid = name.split("/")[-2]
            subject, subset = sid.split("_")
            assert x.shape == (len(source_y), 15 if subset == "gesture" else 24)
            assert np.all(source_y == np.floor(source_y))
            assert set(np.unique(source_y)) <= set(range(1, len(CLASSES[subset]) + 1))
            y = source_y.astype(np.int16) + (100 if subset == "gesture" else 0)
            labels = {"label_activity": y}
            signals = {
                c: x[:, j].astype(np.float32)
                if j < x.shape[1]
                else np.full(len(y), np.nan, dtype=np.float32)
                for j, c in enumerate(channels)
            }
            writer.add_series(
                sid,
                signals,
                labels=labels,
                meta={
                    "subject": subject,
                    "subset": subset,
                    "source_file": name,
                    "n_source_channels": x.shape[1],
                },
            )
            stats.add(sid, labels)
    finish(
        args,
        spec,
        writer,
        stats,
        title="ActRecTut: walk and gesture",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="GPL-3.0-or-later",
        license_url="https://www.gnu.org/licenses/gpl-3.0.html",
        license_evidence=f"{SOURCE}/src/commit/{REVISION}/settings.m",
        description="All four ActRecTut recordings: two subjects, walk and gesture subsets; "
        "24 and 15 source channels respectively at 32 Hz, with recurrent NULL states.",
        collection="Body-worn inertial sensors on two subjects. settings.m lists gesture "
        "placements (right hand, lower arm, upper arm) and walk placements "
        "(right hip, lower arm, ankle, upper leg). Sampling is 32 Hz in settings.m.",
        annotation="Source labels from data.mat; class names from settings.m. Walk IDs "
        "remain 1..6; gesture source IDs 1..12 map to 101..112 to avoid conflating "
        "subset-specific activities. NULL (walk 1, gesture 101) is an ordinary "
        "fully annotated state. No samples are masked.",
        conversion="Preserve every source data.mat column; cast to float32, no filtering "
        "or normalisation. Columns source_col_01..24 denote 1-based positions "
        "within each subset, not shared physical sensors. Gesture has only 15 "
        "channels; columns 16..24 are NaN padding and n_source_channels records "
        "the count. settings.m lists only 20 walk channel names for a 24-column "
        "matrix, so no undocumented axis mapping is invented. Gesture column "
        "names are recorded separately. No truncation to Time2State's first ten columns.",
        limitations="Only two subjects. Source settings.m channel documentation conflicts "
        "with walk matrix width; physical units are not established. Padding "
        "must be removed for gesture using n_source_channels. Subset channel "
        "positions are not physically comparable.",
        biases="Small tutorial dataset, scripted repeated activities and gestures.",
        personal="Pseudonymous subject IDs; motion patterns may identify participants. "
        "No demographic attributes added.",
        citation="Bulling, Andreas; Blanke, Ulf; Schiele, Bernt (2014). A Tutorial on "
        "Human Activity Recognition Using Body-worn Inertial Sensors. ACM Computing "
        "Surveys 46(3), Article 33. https://doi.org/10.1145/2499621",
        creators=["Bulling, Andreas", "Blanke, Ulf", "Schiele, Bernt"],
        date_published="2014",
        null_states={"label_activity": [1, 101]},
        info={
            "reference_doi": "https://doi.org/10.1145/2499621",
            "source_revision": REVISION,
            "state_names": {"label_activity": names},
            "state_source_codes": {"label_activity": {k: int(k) % 100 for k in names}},
            "gesture_source_columns": [
                f"{sensor}_{i}_{axis}"
                for i in range(1, 4)
                for sensor, axes in [("acc", "xyz"), ("gyr", "xy")]
                for axis in axes
            ],
            "tsb_seg_channels": "walk only: source_col_01 through source_col_10",
        },
    )


if __name__ == "__main__":
    main()
