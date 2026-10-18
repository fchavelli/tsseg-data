"""Stream native CalMS21 task-1 JSON poses, confidences and manual labels."""

from __future__ import annotations

import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ijson  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "calms21"
SOURCE = "https://data.caltech.edu/records/s0vdx-0k302"
URL = "https://data.caltech.edu/api/records/s0vdx-0k302/files/task1_classic_classification.zip/content"
SHA256 = "f1cd2f46771cc3834020d187604da53e5ff330121f5a816146f14192fb0bf427"
README_URL = "https://data.caltech.edu/api/records/s0vdx-0k302/files/readme.md/content"
README_SHA = "e2d2c7945a92579a8efeeb6b4a2eddf87de31567cc5c62a2b781f813fad2b56d"
BODY_PARTS = [
    "nose",
    "left_ear",
    "right_ear",
    "neck",
    "left_hip",
    "right_hip",
    "tail_base",
]
MICE = ["resident", "intruder"]
POSE = [
    f"{mouse}_{part}_{axis}_px"
    for mouse in MICE
    for axis in ["x", "y"]
    for part in BODY_PARTS
]
SCORES = [f"{mouse}_{part}_confidence" for mouse in MICE for part in BODY_PARTS]
STATES = {0: "attack", 1: "investigation", 2: "mount", 3: "other"}


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "task1.zip", SHA256, args.raw_dir, ID)
    fetch(README_URL, "readme.md", README_SHA, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=POSE + SCORES,
        configs={"default": POSE, "full": POSE + SCORES},
        sampling_rate_hz=30,
        time_column=("frame_index", pa.int32()),
        label_columns={"label_behavior": pa.int32()},
        meta_columns={
            "source_sequence_id": pa.string(),
            "source_file": pa.string(),
            "source_annotator_id": pa.int32(),
            "source_split": pa.string(),
        },
    )
    stats = Statistics()
    counts, frames = Counter(), Counter()
    missing = {"pose": 0, "confidence": 0}
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        for split in ["train", "test"]:
            name = f"task1_classic_classification/calms21_task1_{split}.json"
            with archive.open(name) as stream:
                for key, record in ijson.kvitems(
                    stream, "annotator-id_0", use_float=True
                ):
                    assert key.startswith(f"task1/{split}/")
                    assert record["metadata"] == {
                        "annotator-id": 0,
                        "vocab": {v: k for k, v in STATES.items()},
                    }
                    pose = np.asarray(record["keypoints"], dtype=np.float32)
                    score = np.asarray(record["scores"], dtype=np.float32)
                    labels = np.asarray(record["annotations"])
                    n = len(labels)
                    assert pose.shape == (n, 2, 2, 7) and score.shape == (n, 2, 7)
                    assert np.isin(labels, list(STATES)).all()
                    assert np.all(
                        (score[np.isfinite(score)] >= 0)
                        & (score[np.isfinite(score)] <= 1)
                    )
                    missing["pose"] += int(np.count_nonzero(~np.isfinite(pose)))
                    missing["confidence"] += int(np.count_nonzero(~np.isfinite(score)))
                    channels = np.concatenate(
                        [pose.reshape(n, 28), score.reshape(n, 14)], axis=1
                    )
                    signal = {c: channels[:, i] for i, c in enumerate(spec.channels)}
                    y = {"label_behavior": labels.astype(np.int32)}
                    sid = key.replace("/", "__")
                    writer.add_series(
                        sid,
                        signal,
                        labels=y,
                        time=np.arange(n, dtype=np.int32),
                        split=split,
                        annotators=["0"],
                        meta={
                            "source_sequence_id": key,
                            "source_file": name,
                            "source_annotator_id": 0,
                            "source_split": split,
                        },
                    )
                    stats.add(sid, y)
                    counts[split] += 1
                    frames[split] += n
        assert counts == {"train": 70, "test": 19}
        assert frames == {"train": 507738, "test": 262107}
    finish(
        args,
        spec,
        writer,
        stats,
        title="CalMS21 task 1: all labelled mouse dyadic poses",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="All 89 CalMS21 task-1 sequences: 70 training and 19 test sequences, 769,845 frames at 30 Hz. Default retains all 28 native x/y pose coordinates for both mice; full additionally retains 14 native MARS keypoint confidence scores. Frame-level human behavior labels are preserved.",
        collection="Resident-intruder mouse assay, 30-fps top-view video with seven MARS-tracked body points per animal. Mouse 0 is the black resident; mouse 1 the white intruder. Provider order is nose, left ear, right ear, neck, left hip, right hip, tail base. Coordinate units are pixels. Paper appendix D.1 confirms 30 fps and 1024×570 camera resolution. Task-1 poses derive from measured video; no synthetic recordings or regenerated features.",
        annotation="Task 1 uses one expert, source annotator-id 0, for both train and test: attack=0, investigation=1, mount=2, other=3. Unless noted by source, behaviors refer to initiation by the resident black mouse. Other is an ordinary scored background class, not missing ground truth. No independent annotation tracks or agreement statistic are available within this subset. Tasks 2/3, other experts and unlabelled sequences are outside this builder's explicit task-1 scope.",
        conversion="Original JSON parsed directly from the ZIP using pinned ijson, one sequence at a time. No pickle or downloaded Python script is loaded or executed. Preserve original sequence keys and train/test split in index. Flatten native (frame, mouse, coordinate, body part) in C order, exactly matching documented channel names; score order is (mouse, body part). Values cast to float32, no centering, scaling, interpolation, confidence masking, smoothing or learned feature extraction. frame_index is the zero-based array index, not a measured absolute timestamp. Default poses and full poses+confidence share identical labels and sampling. Provider taskprog/TREBA/MARS engineered features and all video archives excluded.",
        limitations="Pose estimates can contain tracking errors; confidence is retained but not used to suppress frames. Task 1 alone cannot measure inter-annotator differences. Source sequence names are identifiers, not verified animal identities; preserve source split rather than inferring animal grouping. Other aggregates behaviors beyond the three events. No biological causal conclusions follow from benchmark classification.",
        biases="Selected laboratory mouse resident-intruder assays and trained expert conventions; excludes many natural behaviors, environments and species. Class imbalance and pose-estimation quality may influence results.",
        personal="Animal tracking only. Source pseudonymous sequence keys and numeric expert identifier retained; no human participant data or annotator names are supplied.",
        citation="Sun et al. (2021). The Multi-Agent Behavior Dataset: Mouse Dyadic Social Interactions. NeurIPS Datasets and Benchmarks. arXiv:2104.02710. CaltechDATA CalMS21 v1.0, doi:10.22002/D1.1991.",
        creators=[
            "Jennifer J. Sun",
            "Tomomi Karigo",
            "David J. Anderson",
            "Pietro Perona",
            "Yisong Yue",
            "Ann Kennedy",
        ],
        date_published="2021-06-07",
        null_states={"label_behavior": [3]},
        info={
            "state_names": {"label_behavior": STATES},
            "default_label": "label_behavior",
            "reference_doi": "https://doi.org/10.22002/D1.1991",
            "subset": "task1_classic_classification only",
            "annotators": ["0"],
            "source_split_sequences": dict(counts),
            "source_split_frames": dict(frames),
            "nonfinite_values": missing,
            "native_body_part_order": BODY_PARTS,
            "native_pose_dimensions": ["frame", "mouse", "coordinate_xy", "body_part"],
            "native_score_dimensions": ["frame", "mouse", "body_part"],
            "source_readme": {"url": README_URL, "sha256": README_SHA},
            "source_primary_md5": "8a02654fddae28614ee24a6a082261b8",
            "sampling_rate_evidence": "https://arxiv.org/html/2104.02710#A4.SS1",
        },
    )


if __name__ == "__main__":
    main()
