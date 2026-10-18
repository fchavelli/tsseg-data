"""Build all MOSAD recordings as nine-channel protocol-labelled CPD series."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "mosad"
SOURCE = "https://github.com/ermshaua/mobile-sensing-human-activity-data-set"
REVISION = "f5d4daf34cd94b7c7a150aa2a650d1d8a4971557"
BASE = f"https://raw.githubusercontent.com/ermshaua/mobile-sensing-human-activity-data-set/{REVISION}/"
SHA256 = "79b767f5bdad2e0bcd5ac96ac59bf287b1eb481be882003779d56ab4469c9687"
ACT_SHA = "ab7e04b165c9eb54e82613a238c308b29dcb865d99cccf76dea832807a524b15"
CP_SHA = "1fa8970978b20b395917422332c125908caaf47906da0b8558f4faba65baf227"
CHANNELS = {
    f"{sensor.lower()}_{axis.lower()}": f"{axis}-{sensor}"
    for sensor in ["Acc", "Gyro", "Mag"]
    for axis in "XYZ"
}


def main() -> None:
    args = parse_args(ID)
    raw = fetch(BASE + "datasets/data.npz", "data.npz", SHA256, args.raw_dir, ID)
    activities_file = fetch(
        BASE + "datasets/activities.txt",
        "datasets_activities.txt.txt",
        ACT_SHA,
        args.raw_dir,
        ID,
    )
    boundaries_file = fetch(
        BASE + "datasets/change_points.txt",
        "datasets_change_points.txt.txt",
        CP_SHA,
        args.raw_dir,
        ID,
    )
    activities = {
        row[0]: row[1:] for row in csv.reader(activities_file.read_text().splitlines())
    }
    source_cps = {
        row[0]: (int(row[1]), np.array(row[2:], dtype=np.int32))
        for row in csv.reader(boundaries_file.read_text().splitlines())
    }
    state_names = sorted({s for values in activities.values() for s in values})
    assert len(state_names) == 20
    codes = {s: i for i, s in enumerate(state_names)}
    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=list(CHANNELS),
        configs={"default": list(CHANNELS)},
        sampling_rate_hz=50,
        label_columns={"label_activity": pa.int32()},
        cp_annotators=["protocol"],
        meta_columns={
            "subject_id": pa.string(),
            "routine_id": pa.string(),
            "source_npz_keys": pa.list_(pa.string()),
        },
    )
    stats = Statistics()
    boundary_count = 0
    with (
        np.load(raw, allow_pickle=False) as archive,
        DatasetWriter(args.out_dir, spec) as writer,
    ):
        assert len(archive.files) == 126 and set(archive.files) == set(source_cps)
        series = sorted({key.rsplit("_", 1)[0] for key in archive.files})
        assert len(series) == 14
        for sid in series:
            routine, subject = sid.split("_")
            source_keys = [f"{sid}_{source}" for source in CHANNELS.values()]
            signal = {
                c: np.asarray(archive[key], dtype=np.float32)
                for c, key in zip(CHANNELS, source_keys, strict=True)
            }
            n = len(next(iter(signal.values())))
            assert all(len(x) == n and np.isfinite(x).all() for x in signal.values())
            rate, cps = source_cps[source_keys[0]]
            assert rate == 50
            for key in source_keys:
                assert source_cps[key][0] == rate and np.array_equal(
                    source_cps[key][1], cps
                )
            assert np.all((cps > 0) & (cps < n)) and np.all(np.diff(cps) > 0)
            names = activities[routine.removeprefix("Routine")]
            assert len(names) == len(cps) + 1 and len(set(names)) == len(names)
            y = np.repeat([codes[s] for s in names], np.diff(np.r_[0, cps, n])).astype(
                np.int32
            )
            labels = {"label_activity": y}
            writer.add_series(
                sid,
                signal,
                labels=labels,
                cps={"protocol": (cps, ["protocol_activity_change"] * len(cps))},
                annotators=["protocol"],
                meta={
                    "subject_id": subject.removeprefix("Subject"),
                    "routine_id": routine.removeprefix("Routine"),
                    "source_npz_keys": source_keys,
                },
            )
            stats.add(sid, labels)
            boundary_count += len(cps)
    finish(
        args,
        spec,
        writer,
        stats,
        title="MOSAD mobile sensing: all native multivariate recordings",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="CC-BY-SA-3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        license_evidence=f"{SOURCE}/blob/{REVISION}/README.md",
        description="All 14 measured MOSAD smartphone recordings, restoring the nine synchronized accelerometer/gyroscope/magnetometer axes from the 126 univariate benchmark views. Native 50-Hz samples, protocol activity names and all reference change-point indices retained. No within-recording activity recurrence, so classified CPD.",
        collection="Six participants perform three ordered activity routines. Released archive includes six household-routine records and four records for each of the other routines; do not fabricate absent subject/routine combinations. The provider represents each physical recording by nine axis views, which share lengths and boundaries and are merged without flattening channels.",
        annotation="activities.txt gives the ordered routine names and change_points.txt gives the same integer boundaries for all nine axes of each recording. Retain every native CP value exactly, interpreted as the zero-based first sample of the next segment in the conversion; the source loader returns these indices unchanged but does not explicitly state an alternative origin. A possible one-sample annotation convention uncertainty is not repaired by signal alignment. Dense activity names are reconstructed on [0, cp1), [cp1, cp2), ...; exact spelling including modified push-ups retained. All samples have protocol ground truth, no null or missing class. Each activity occurs once per recording; no semantic-state recurrence is claimed. No independent annotator tracks or agreement statistic provided.",
        conversion="Read numeric NPZ with allow_pickle=False; never execute the downloaded provider loader. Assert all nine channel lengths, rates and change-point arrays agree before merging into a multivariate series. Cast native numeric signals to float32, preserve sample order, no resampling, smoothing, scaling, concatenation or synthetic records. Global codes map twenty distinct source activity strings reversibly, shared across routines. Preserve source subject/routine IDs for grouped evaluation.",
        limitations="Protocol order is fixed and each activity appears only once within a recording; CPD scores do not demonstrate recurrent state discovery. Twenty unique activity names, not the twenty-one claimed in the draft registry. Boundary convention uncertainty may affect one-sample comparisons. MOSAD and HAS have shared author/protocol context; exact nine-channel float32 recording hashes compared with all 250 pinned local HAS builds yielded no complete duplicates, but this does not prove independence or exclude partial overlap. Do not combine corpora in independent folds without further overlap review.",
        biases="Small six-person smartphone protocol with ordered routines, few repetitions and selected activities. Subject and routine correlations may dominate generalisation; compare grouped rather than random-window splits.",
        personal="Pseudonymous source participant IDs and inertial measurements only. No location channels or personal demographics exist in this release; do not attempt re-identification.",
        citation="Ermshaus, Arik; Singh, Sunita; Leser, Ulf (2023). Time Series Segmentation Applied to a New Data Set for Mobile Sensing of Human Activities. DARLI-AP@EDBT/ICDT.",
        creators=["Arik Ermshaus", "Sunita Singh", "Ulf Leser"],
        date_published="2023-03-24",
        info={
            "source_revision": REVISION,
            "state_names": {"label_activity": dict(enumerate(state_names))},
            "default_label": "label_activity",
            "label_origin": "protocol",
            "reference_change_points": boundary_count,
            "source_univariate_views": 126,
            "physical_recordings": 14,
            "source_annotations": {
                "activities": {
                    "url": BASE + "datasets/activities.txt",
                    "sha256": ACT_SHA,
                },
                "change_points": {
                    "url": BASE + "datasets/change_points.txt",
                    "sha256": CP_SHA,
                },
            },
            "overlap_audit": {
                "comparison_dataset": "has",
                "comparison_source_revision": "a77bf78d1ff7e7115e64b2214da809660f99d943",
                "method": "Exact whole-recording SHA256 over all nine float32 channels in sensor/axis order; no matches among 250 built HAS records. Partial/processed overlap remains untested.",
                "complete_matches": 0,
            },
            "date_published_scope": "Pinned source repository revision date",
        },
    )


if __name__ == "__main__":
    main()
