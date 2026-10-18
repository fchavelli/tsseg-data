"""Build all native Bimacs body poses and separate left/right action tracks."""

from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "bimacs"
SOURCE = "https://bimanual-actions.humanoids.kit.edu/original_dataset"
TERMS = "https://bimanual-actions.humanoids.kit.edu/terms-of-use"
BASE = "https://bimanual-actions.humanoids.kit.edu/download/"
POSE_SHA = "e0978fb88f94a97ea61826c40e0b4e74f8ec088c5fb0bc8ddade734a2ac3193f"
LABEL_SHA = "0624c16ffe733ad57cea43620545801bba91881ec1e6a10b4118aee37c6ce0e0"
JOINTS = [
    "LAnkle",
    "LBigToe",
    "LEar",
    "LElbow",
    "LEye",
    "LHeel",
    "LHip",
    "LKnee",
    "LShoulder",
    "LSmallToe",
    "LWrist",
    "MidHip",
    "Neck",
    "Nose",
    "RAnkle",
    "RBigToe",
    "REar",
    "RElbow",
    "REye",
    "RHeel",
    "RHip",
    "RKnee",
    "RShoulder",
    "RSmallToe",
    "RWrist",
]
XY = [f"{joint}_{axis}_px" for joint in JOINTS for axis in ["x", "y"]]
CONF = [f"{joint}_confidence" for joint in JOINTS]
STATES = dict(
    enumerate(
        [
            "idle",
            "approach",
            "retreat",
            "lift",
            "place",
            "hold",
            "pour",
            "cut",
            "hammer",
            "saw",
            "stir",
            "screw",
            "drink",
            "wipe",
        ]
    )
)


def main() -> None:
    args = parse_args(ID)
    pose_file = fetch(
        BASE + "bimacs_derived_data_body_pose.zip",
        "body-pose.zip",
        POSE_SHA,
        args.raw_dir,
        ID,
    )
    label_file = fetch(
        BASE + "bimacs_rgbd_data_ground_truth.zip",
        "ground-truth.zip",
        LABEL_SHA,
        args.raw_dir,
        ID,
    )
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=XY + CONF,
        configs={"default": XY, "full": XY + CONF},
        sampling_rate_hz=None,
        time_column=("frame_index", pa.int32()),
        label_columns={f"label_{hand}_hand": pa.int32() for hand in ["left", "right"]},
        meta_columns={
            "subject_id": pa.string(),
            "task_id": pa.string(),
            "take_id": pa.string(),
            "source_series_path": pa.string(),
            "zero_confidence_keypoints": pa.int32(),
        },
    )
    groups = defaultdict(list)
    intervals = []
    ambiguous_detections = []
    ambiguous_frames = 0
    stats = Statistics()
    zero_confidence = 0
    nonfinite = 0
    with zipfile.ZipFile(pose_file) as poses, zipfile.ZipFile(label_file) as actions:
        for name in poses.namelist():
            if name.endswith(".json"):
                path = Path(name)
                assert path.parent.name == "body_pose"
                trip = "/".join(path.parts[1:4])
                groups[trip].append((int(path.stem.removeprefix("frame_")), name))
        assert len(groups) == 540
        with DatasetWriter(args.out_dir, spec) as writer:
            for trip, frames in sorted(groups.items()):
                frames.sort()
                n = len(frames)
                assert [i for i, _ in frames] == list(range(n)), trip
                sid = trip.replace("/", "__")
                matrix = np.full((n, len(spec.channels)), np.nan, dtype=np.float32)
                for i, name in frames:
                    people = json.loads(poses.read(name))
                    assert 1 <= len(people) <= 5, name
                    if len(people) > 1:
                        ambiguous_frames += 1
                        for rank, detection in enumerate(people):
                            assert set(detection) == set(JOINTS), name
                            ambiguous_detections.append(
                                {
                                    "series_id": sid,
                                    "frame_index": i,
                                    "source_detection_index": rank,
                                    "coordinates_xy": [
                                        detection[joint][axis]
                                        for joint in JOINTS
                                        for axis in ["x", "y"]
                                    ],
                                    "confidences": [
                                        detection[joint]["confidence"]
                                        for joint in JOINTS
                                    ],
                                }
                            )
                        continue
                    person = people[0]
                    assert set(person) == set(JOINTS), name
                    matrix[i, :50] = [
                        person[joint][axis] for joint in JOINTS for axis in ["x", "y"]
                    ]
                    matrix[i, 50:] = [person[joint]["confidence"] for joint in JOINTS]
                    assert all(person[joint]["label"] == joint for joint in JOINTS)
                nonfinite += int(np.count_nonzero(~np.isfinite(matrix)))
                zero = int(np.count_nonzero(matrix[:, 50:] == 0))
                zero_confidence += zero
                source = json.loads(
                    actions.read(f"bimacs_rgbd_data_ground_truth/{trip}.json")
                )
                assert set(source) == {"left_hand", "right_hand"}
                labels = {}
                for hand, data in source.items():
                    assert len(data) % 2 == 1 and data[0] == 0 and data[-1] == n - 1, (
                        trip,
                        hand,
                        data[-1],
                        n,
                    )
                    bounds = data[::2]
                    assert np.all(np.diff(bounds) >= 0)
                    y = np.full(n, -1, dtype=np.int32)
                    for interval, (begin, end, state) in enumerate(
                        zip(bounds[:-1], bounds[1:], data[1::2], strict=True)
                    ):
                        assert state is None or state in STATES
                        y[begin:end] = -1 if state is None else state
                        intervals.append(
                            {
                                "series_id": sid,
                                "hand": hand,
                                "source_interval_index": interval,
                                "begin_frame": begin,
                                "end_frame_exclusive": end,
                                "source_state": state,
                            }
                        )
                    labels[f"label_{hand}"] = y
                subject, task, take = trip.split("/")
                writer.add_series(
                    sid,
                    {c: matrix[:, i] for i, c in enumerate(spec.channels)},
                    labels=labels,
                    time=np.arange(n, dtype=np.int32),
                    meta={
                        "subject_id": subject,
                        "task_id": task,
                        "take_id": take,
                        "source_series_path": trip,
                        "zero_confidence_keypoints": zero,
                    },
                )
                stats.add(sid, labels)
            table = pa.Table.from_pylist(intervals)
            pq.write_table(
                table, args.out_dir / "source_intervals.parquet", compression="zstd"
            )
            pq.write_table(
                pa.Table.from_pylist(ambiguous_detections),
                args.out_dir / "ambiguous_detections.parquet",
                compression="zstd",
            )
    finish(
        args,
        spec,
        writer,
        stats,
        title="KIT Bimanual Actions: all body poses and two hand-action tracks",
        source=SOURCE,
        sha256=POSE_SHA,
        license_spdx="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        license_evidence=TERMS,
        description="All 540 original KIT Bimanual Actions trials, with all 25 body-pose joints (50 x/y pixel coordinates) and native left/right action labels. Full additionally retains all 25 joint confidence scores. Frame indices are preserved; the native mixture of 15/30 fps is not replaced by an invented common rate.",
        collection="Six subjects perform nine kitchen/workshop tasks ten times each. OpenPose-derived 2D body keypoints from the provider are retained; no RGB-D images are downloaded or redistributed. Only body-pose and action-ground-truth source ZIPs are required. Separate fine hand poses and object tracking are outside this explicit body-pose view.",
        annotation="Provider annotates fourteen actions separately for left and right hands. These are different simultaneous label targets, not independent annotators, so no consensus or inter-annotator agreement is computed. The primary format defines alternating frame boundaries/action IDs, with start inclusive and end exclusive. All source intervals, including adjacent repeated IDs, are retained unchanged in source_intervals.parquet. Source null means no associated action and maps to missing -1, distinct from ordinary scored idle 0. No segments are inferred from pose or confidence.",
        conversion="One series per subject/task/take; numeric frame filenames sorted and asserted contiguous from zero, with annotation endpoint exactly equal to frame_count-1 for both hands, as verified in every source trial. Following the provider-documented exclusive end convention, the final frame remains unlabelled in each hand; the source does not justify extending it. Copy every native body-joint x/y and confidence as float32; zero coordinates at zero confidence are retained, not interpolated or silently converted to valid detections. Default is all 50 coordinates, full adds 25 confidences. The provider documentation says one person per frame, but 4,513 frames actually have 2–5 detections without subject identity. Their main coordinates/confidences are NaN instead of choosing an arbitrary person; every ambiguous detection is retained in auxiliary with frame and native detection rank, without assigning tracking identity. Manual action labels remain unchanged. Provider-derived dominantColor fields are excluded from this kinematic view. No smoothing, resampling, confidence threshold, or label merging. Preserve subject IDs for grouped evaluation. Source sampling_rate_hz=None because the primary source reports 83 recordings at 15 fps and others at 30, without identifying them in the two lightweight ZIPs; time column is frame index only.",
        limitations="Exact per-recording physical rate is not available in pose/annotation archives. It exists only in metadata.csv inside ~93 GiB of RGB-D archives; server ignores HTTP Range (returns 200), so retrieval was stopped before reading those bodies. Frame-based segmentation metrics remain possible; durations in seconds must not assume 30 fps. Pose estimates can fail; confidence zero means keypoint not detected. All body joints retained even if frequently invisible. This view excludes fine hand/object modalities and later category extensions.",
        biases="Small scripted six-person kitchen/workshop cohort with fixed camera and selected object tasks; limited generalisation to unconstrained activity. Pose failures and subject/task correlations can affect results.",
        personal="Derived human body positions and pseudonymous subject IDs retained, without raw images, face imagery, demographics or dominant colours. Do not attempt re-identification.",
        citation="Dreher, Christian R. G.; Wächter, Mirko; Asfour, Tamim (2020). Learning Object-Action Relations from Bimanual Human Demonstration Using Graph Networks. IEEE Robotics and Automation Letters 5(1):187–194. doi:10.1109/LRA.2019.2949221.",
        creators=["Christian R. G. Dreher", "Mirko Wächter", "Tamim Asfour"],
        date_published="2019-08-20",
        null_states={c: [0] for c in spec.label_columns},
        info={
            "state_names": {c: STATES for c in spec.label_columns},
            "default_label": "label_left_hand",
            "tracks": ["left_hand", "right_hand"],
            "reference_doi": "https://doi.org/10.1109/LRA.2019.2949221",
            "source_archives": {
                "body_pose": {
                    "url": BASE + "bimacs_derived_data_body_pose.zip",
                    "sha256": POSE_SHA,
                },
                "action_ground_truth": {
                    "url": BASE + "bimacs_rgbd_data_ground_truth.zip",
                    "sha256": LABEL_SHA,
                },
            },
            "annotation_final_frame_unlabelled": True,
            "source_endpoints_equal_frame_count_minus_one": True,
            "sampling_rate_status": "Mixed 15/30 fps; 83 low-rate trials unidentified without image metadata; frame index retained",
            "zero_confidence_keypoints": zero_confidence,
            "nonfinite_primary_projection_scalar_values": nonfinite,
            "ambiguous_person_frames": ambiguous_frames,
            "ambiguous_person_detections": len(ambiguous_detections),
            "auxiliary": {
                "ambiguous_detections.parquet": "All person detections from ambiguous frames, native source detection rank, 50 x/y coordinates in JOINTS order and 25 confidences; rank is not a persistent identity.",
                "source_intervals.parquet": "All native left/right half-open action intervals, unchanged source state IDs (including null), and source interval order.",
            },
        },
    )


if __name__ == "__main__":
    main()
