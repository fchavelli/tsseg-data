"""Build all released fishing trips with source phases and literal activity names."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "ais-fishing-semseg"
SOURCE = "https://zenodo.org/records/7283281"
URL = "https://zenodo.org/api/records/7283281/files/128_fishing_trajs.csv/content"
SHA256 = "787bd946fadf0c114f4925dd3ee792e64034311fd4940ea47b91b4ddd804b8ad"
README_URL = (
    "https://zenodo.org/api/records/7283281/files/128_fishing_trajs_README.txt/content"
)
README_SHA = "35452d6fcc10d187306e30e6b638b450638f4c28a5c8e2ab777f9d30ab449b3b"
CHANNELS = [
    "longitude",
    "latitude",
    "x",
    "y",
    "signed_turn",
    "bearing",
    "time_gap",
    "distance_gap",
    "euc_speed",
    "distanceToShore",
]
PHASES = {
    0: "01-sailing",
    1: "02-fishing",
    2: "03-sailing",
    3: "04-fishing",
    4: "05-sailing",
}
ACTIVITY = {0: "sailing", 1: "fishing"}


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "128_fishing_trajs.csv", SHA256, args.raw_dir, ID)
    readme = fetch(README_URL, "README-source.txt", README_SHA, args.raw_dir, ID)
    assert (
        hashlib.md5(raw.read_bytes()).hexdigest() == "c5953081f511e228b19e46ca85fe304f"
    )
    assert (
        hashlib.md5(readme.read_bytes()).hexdigest()
        == "821ab4d9fee26054ebf3147fcaadede9"
    )
    frame = pd.read_csv(raw)
    assert list(frame) == ["id", "t", *CHANNELS, "label"]
    assert not frame.isna().any().any()
    assert set(frame.label) == set(PHASES.values())
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        channel_type=pa.float64(),
        time_column=("timestamp", pa.timestamp("s")),
        label_columns={"label_activity": pa.int32(), "label_source_phase": pa.int32()},
        meta_columns={
            "source_trip_id": pa.string(),
            "source_vessel_id": pa.string(),
            "max_gap_s": pa.int64(),
            "median_gap_s": pa.float64(),
        },
    )
    stats = Statistics()
    gaps = []
    source_ids = frame.id.drop_duplicates()
    assert len(source_ids) == 123
    assert int(frame.id.ne(frame.id.shift()).sum()) == len(source_ids)
    vessels = set()
    reverse = {v: k for k, v in PHASES.items()}
    with DatasetWriter(args.out_dir, spec) as writer:
        for sid, trip in frame.groupby("id", sort=False):
            vessel = sid.split("-", 1)[0]
            vessels.add(vessel)
            time = pd.to_datetime(trip.t, format="%Y-%m-%d %H:%M:%S").to_numpy(
                dtype="datetime64[s]"
            )
            steps = np.diff(time.astype(np.int64))
            assert (steps > 0).all(), sid
            gaps.append(int(steps.max()))
            signal = {c: trip[c].to_numpy(dtype=np.float64) for c in CHANNELS}
            assert all(np.isfinite(v).all() for v in signal.values())
            labels = {
                "label_activity": (
                    trip.label.str.split("-").str[1] == "fishing"
                ).to_numpy(dtype=np.int32),
                "label_source_phase": trip.label.map(reverse).to_numpy(dtype=np.int32),
            }
            writer.add_series(
                sid,
                signal,
                labels=labels,
                time=time,
                meta={
                    "source_trip_id": sid,
                    "source_vessel_id": vessel,
                    "max_gap_s": int(steps.max()),
                    "median_gap_s": float(np.median(steps)),
                },
            )
            stats.add(sid, labels)
    finish(
        args,
        spec,
        writer,
        stats,
        title="Manually labelled fishing AIS trajectories, all released trips",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="All 123 distinct trip IDs actually present in the primary CSV named 128_fishing_trajs.csv, with 1,026,279 AIS observations and all ten released numeric trajectory variables. Native five source-phase strings remain reversible; a second track uses only their literal sailing/fishing names.",
        collection="Song Wu manually labelled AIS fishing trajectories during research for MDM 2022. Native coordinates include longitude/latitude and projected x/y under source SRID 25832; source provides turn, bearing, gaps, speed and distance to Denmark's coast. Both measured positions and already-derived trajectory features are retained.",
        annotation="Primary Zenodo deposit explicitly describes manual author labels, not method predictions. Native strings are 01-sailing, 02-fishing, 03-sailing, 04-fishing and 05-sailing; label_source_phase maps them reversibly to codes 0–4. label_activity removes only the numeric prefix and maps literal sailing=0, fishing=1, so semantic recurrence can be studied without discarding source phases. No outgoing/return semantics beyond the literal labels are invented. All samples have labels; sailing and fishing are both ordinary scored states. No null/unknown class, independent annotator or agreement statistic exists.",
        conversion="One series per native trip id, in original source order; all source rows retained, no resampling or interpolation. Native second-precision timestamp strings parsed without adding a timezone (provider does not specify one). Signals remain float64 to preserve geospatial precision. Source vessel identifier prefix retained as index metadata; evaluation must group by vessel to avoid leakage across trips. Source-derived features are copied unchanged, including first-row gaps calculated relative to a point outside the released trip. Source README SHA and primary MD5 of both files checked.",
        limitations="The deposit title/filename claims 128 trajectories, but the full pinned CSV contains 123 distinct contiguous trip IDs from 84 vessel prefixes; no five missing trips are fabricated. Timestamp gaps reach 47,172 seconds. Nominal sampling rate and timezone unspecified. Source README describes euc_speed as knots/hour; this unusual unit is retained as provider wording rather than silently corrected. Dense labels do not independently establish label uncertainty. Positions and released features may already embody source processing.",
        biases="Fishing trajectories near Denmark and author-selected/labelled trips; substantial fishing class imbalance. Public vessel-based observations need not generalise to other regions, vessel types or fishing methods.",
        personal="Public AIS vessel identifier prefixes, trajectories and times retained because location is the signal of this geospatial task. Vessel IDs may be linkable to owners or operators; do not attempt personal re-identification or treat observations as evidence of unlawful activity.",
        citation="Wu, Song (2022). Dataset for Semantic Segmentation of Fishing Trajectories. Zenodo. doi:10.5281/zenodo.7283281. Related paper: Semantic Segmentation of AIS Trajectories for Detecting Complete Fishing Activities, MDM 2022. doi:10.1109/MDM55031.2022.00092.",
        creators=["Song Wu"],
        date_published="2022-11-04",
        info={
            "state_names": {"label_activity": ACTIVITY, "label_source_phase": PHASES},
            "default_label": "label_activity",
            "reference_doi": "https://doi.org/10.1109/MDM55031.2022.00092",
            "source_readme": {"url": README_URL, "sha256": README_SHA},
            "source_primary_md5": "c5953081f511e228b19e46ca85fe304f",
            "claimed_trips": 128,
            "actual_trip_ids": 123,
            "source_vessel_prefixes": len(vessels),
            "max_timestamp_gap_s": max(gaps),
            "position_reference_system": "longitude/latitude and source SRID 25832 x/y",
            "source_speed_unit_wording": "knots/hour; uncorrected provider README wording",
        },
    )


if __name__ == "__main__":
    main()
