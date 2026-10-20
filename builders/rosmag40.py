"""Build all 40 published ROSMAG40 kinematic feature and gesture sequences."""

from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.rosmag40 import RESERVE, acquire, member, parse_signal  # noqa: E402
from tsseg_data.sources import sha256  # noqa: E402

ID = "rosmag40"
SOURCE = "https://zenodo.org/records/10719748"
PINS = Path(__file__).parent / "checksums/rosmag40.json"
MD = {1: "idle", 2: "precision", 3: "displacement", 4: "collaboration"}
FGD = {
    1: "idle",
    2: "picking",
    3: "placing",
    4: "free_motion",
    5: "load_motion",
    6: "collaboration",
}
TRACKS = {
    f"label_{level}_{tool}": (MD if level == "md" else FGD)
    for level in ["fgd", "md"]
    for tool in ["psm1", "psm2"]
}


def main():
    args = parse_args(ID)
    pins = json.loads(PINS.read_text())
    raw = args.raw_dir / ID
    data = acquire(raw, pins)
    if shutil.disk_usage(raw).free - pins["native_bytes"] * 2 - 64 * 2**20 < RESERVE:
        raise RuntimeError("Complete output budget breaches the 18-GiB reserve")
    channels = [c.lower() for c in pins["channels"]]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=channels,
        configs={"default": channels},
        sampling_rate_hz=None,
        time_column=("source_row_index", pa.int32()),
        label_columns={track: pa.int8() for track in TRACKS},
        meta_columns={
            "subject_id": pa.string(),
            "task_name": pa.string(),
            "trial_number": pa.int16(),
            "source_signal_member": pa.string(),
        },
    )
    lookup = {p["name"].lower(): p for p in pins["members"]}
    signals = [p for p in pins["members"] if p["name"].startswith("kinematics/")]
    assert len(signals) == 40 and len(lookup) == 120
    stats = Statistics()
    substantive = {t: 0 for t in TRACKS}
    counts = {t: {} for t in TRACKS}
    hierarchy = np.array([0, 1, 2, 2, 3, 3, 4])
    with DatasetWriter(args.out_dir, spec) as writer:
        for pin in sorted(signals, key=lambda p: p["name"]):
            sid = Path(pin["name"]).stem
            x = parse_signal(member(data, pin), pins["channels"])
            labels = {}
            for level in ["fgd", "md"]:
                lp = lookup[f"{level}labels/{sid}_gesture.txt".lower()]
                y = np.loadtxt(io.BytesIO(member(data, lp)), dtype=np.int8)
                assert y.shape == (len(x), 2)
                for col, tool in enumerate(["psm1", "psm2"]):
                    track = f"label_{level}_{tool}"
                    assert set(y[:, col]) <= set(TRACKS[track])
                    labels[track] = y[:, col]
            for tool in ["psm1", "psm2"]:
                assert np.array_equal(
                    hierarchy[labels[f"label_fgd_{tool}"]], labels[f"label_md_{tool}"]
                )
            writer.add_series(
                sid,
                {c: x[:, i] for i, c in enumerate(channels)},
                time=np.arange(len(x), dtype=np.int32),
                labels=labels,
                meta={
                    "subject_id": sid.split("_")[0],
                    "task_name": "_".join(sid.split("_")[1:-1]).lower(),
                    "trial_number": int(sid.split("_")[-1]),
                    "source_signal_member": pin["name"],
                },
            )
            stats.add(sid, labels)
            for track, y in labels.items():
                states = y[np.r_[True, np.diff(y) != 0]]
                _, n = np.unique(states[states != 1], return_counts=True)
                substantive[track] += int(np.any(n > 1))
                for value, n in zip(*np.unique(y, return_counts=True), strict=True):
                    key = str(int(value))
                    counts[track][key] = counts[track].get(key, 0) + int(n)
            if shutil.disk_usage(raw).free < RESERVE:
                raise RuntimeError("18-GiB reserve breached")
    finish(
        args,
        spec,
        writer,
        stats,
        title="ROSMAG40: all 40 published kinematic feature sequences and bilateral gestures",
        source=SOURCE,
        sha256=sha256(PINS),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-20",
        description="All 40 released ROSMAG40 sequences, 72,843 source rows and all 34 published kinematic features. Four synchronous human gesture tracks retain maneuver descriptors (MD) and fine-grain descriptors (FGD) independently for PSM1 and PSM2. No videos or participant questionnaires included.",
        collection="Five pseudonymous users (X01, X02, X06, X07, X08), two bench surgical training tasks (pea on a peg, post and sleeve), four released trials per user/task. This is the complete provider-published 34-feature view: each PSM contributes orientation XYZW, linear/angular velocity and force/torque XYZ; distance and angle between tools are provider-derived. It is not a reconstruction of the 154/160-feature, 50-Hz original ROSMA sensor corpus.",
        annotation="The primary paper defines framewise two-column labels: PSM1 then PSM2. Pinned author MATLAB example directly pairs kinematic sequences with label columns, preserving row order. All 40 triplets have exactly matching row counts. MD has four classes and FGD six, with exact hierarchy F1→G1, F2/F3→G2, F4/F5→G3, F6→G4 at every row/tool. These are semantic levels and instrument tracks, not four independent raters; no separate annotator identity, repeat ratings or agreement statistic is released. Idle 1 is an ordinary annotated resting-tool state and remains scored; no missing or unknown labels occur. Default label_fgd_psm1 is a conventional choice of the first fine-grain instrument track, not a consensus or privileged annotator.",
        conversion="Require HTTP206 for exactly the 12,980,548-byte ZIP prefix containing all 120 selected members and no video members. Pin SHA256 of that prefix and every original TXT, verify local filenames, compression, CRC, native sizes and header schema; never acquire the full 3.98-GB archive or extract its video content. Parse numeric text, lowercase channel names, cast signal values once to float32, preserve every row and all labels. No new scaling, interpolation, quaternion normalization, temporal averaging or feature computation. Retain zero-based source_row_index. Video capture is nominally 15 fps in the primary paper, but released feature files contain no native timestamps or explicit synchronization/resampling recipe; do not assign original ROSMA50 Hz or claim an exact physical clock. sampling_rate_hz remains null.",
        limitations="Released features are a provider-selected, already processed view with two derived channels; missing raw positions, master-tool and joint channels are outside this published ROSMAG40 view. Decimal patterns suggest provider temporal aggregation, but no aggregation algorithm or bin origin is established, so none is reconstructed. Frame/row pairing follows the primary author loader, not signal-fitted offsets or annotation stretching. Nominal video cadence does not establish exact physical onset times. Zenodo description says22 videos whereas the actual archive and primary paper contain40; measured72,843 rows agrees with both. Some printed paper class-count/percentage entries contain typographical inconsistencies; measured literal counts are retained in metadata. Four tracks share the same scene and are not independent samples or annotators. All four tracks recur in 40/40 trials including idle; substantive recurrence excluding idle is 39/40 for each PSM1 level and 40/40 for each PSM2 level.",
        biases="Five users performing two constrained training tasks on one dVRK setup; task, subject and repeated trial correlations. Evaluate with subject-disjoint or documented task/trial splits, not random overlapping windows. This is bench robotic training, not patient surgery or clinical validation.",
        personal="Pseudonymous source user/trial IDs and tool motion only. No videos, faces, subject handedness, questionnaire, scores or demographic attributes are packaged.",
        citation="Rivas-Blanco I., López-Casado C., Herrera-López J.M., Cabrera Villa J., Pérez-del-Pulgar C. (2024). Instrument Detection and Descriptive Gesture Segmentation on a Robotic Surgical Maneuvers Dataset. Applied Sciences14(9):3701. doi:10.3390/app14093701. ROSMAG40 doi:10.5281/zenodo.10719748.",
        creators=[
            "Irene Rivas-Blanco",
            "Carmen López-Casado",
            "Juan María Herrera-López",
            "José Cabrera Villa",
            "Carlos Pérez-del-Pulgar",
        ],
        date_published="2024-02-27",
        null_states={t: [1] for t in TRACKS},
        info={
            "state_names": TRACKS,
            "annotators": [],
            "n_released_annotation_tracks": 4,
            "tracks": {
                t: {"level": t.split("_")[1], "instrument": t.split("_")[2]}
                for t in TRACKS
            },
            "source_files": pins,
            "reference_doi": "https://doi.org/10.3390/app14093701",
            "source_channel_names": pins["channels"],
            "source_video_nominal_fps": 15,
            "sampling_rate_status": "Unverified physical clock for released row-aligned features; native timestamps absent",
            "source_frame_origin": "zero-based released row index, not asserted original camera frame ID",
            "label_frame_counts": counts,
            "series_with_substantive_recurrence": substantive,
            "source_scope": "All 40 published 34-feature sequences and all 80 annotation files; original full ROSMA154/160 features not included",
            "channel_units": {
                c: "source native; physical unit not asserted by selected TXT header"
                for c in channels
            },
        },
    )


if __name__ == "__main__":
    main()
