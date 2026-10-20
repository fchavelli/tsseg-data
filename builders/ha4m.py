"""Build all 217 native HA4M skeleton recordings and framewise action labels."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.ha4m import (  # noqa: E402
    CHANNELS,
    FIELDS,
    RESERVE,
    acquire,
    decode,
)
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "ha4m"
SOURCE = "https://doi.org/10.57760/sciencedb.01872"
REPOSITORY = "https://baltig.cnr.it/ISP/ha4m"
REVISION = "cc0b49cbf0bb39f63b368c5c4f10d0c27a6a452e"
PIN_FILE = Path(__file__).parent / "checksums/ha4m.json"
STATES = {
    0: "dont_care_transition_or_unexpected_event",
    1: "pick_place_carrier",
    2: "pick_place_gear_bearings",
    3: "pick_place_planet_gears",
    4: "pick_place_carrier_shaft",
    5: "pick_place_sun_shaft",
    6: "pick_place_sun_gear",
    7: "pick_place_sun_gear_bearing",
    8: "pick_place_ring_bear",
    9: "pick_block2_place_on_block1",
    10: "pick_place_cover",
    11: "pick_place_screws",
    12: "pick_place_allen_key_turn_screws_return_key_and_egt",
}


def fingerprint(x):
    """Canonical channel-major digest of the published float32 observations."""
    h = hashlib.sha256()
    for i in range(x.shape[1]):
        h.update(x[:, i].astype("<f4", copy=False).tobytes())
    return h.hexdigest()


def main():
    args = parse_args(ID)
    manifest = json.loads(PIN_FILE.read_text())
    pins = manifest["trials"]
    assert len(pins) == 217
    raw_root = args.raw_dir / ID
    raw_root.mkdir(parents=True, exist_ok=True)
    missing = sum(
        p["source_bytes"]
        for t, p in pins.items()
        if not (raw_root / f"{t}.zip.gz").exists()
    )
    output_floor = manifest["output_ratio_floor"]
    required = (
        missing * manifest["cache_ratio_floor"]
        + manifest["source_bytes"] * output_floor
    ) * 1.25 + 96 * 2**20
    if shutil.disk_usage(raw_root).free - required < RESERVE:
        raise RuntimeError(
            "Complete cached-source+output projection breaches18-GiB reserve"
        )
    corrections = manifest.get("corrected_label_associations", {})
    evidence = {}
    for trial, correction in corrections.items():
        pin = correction["author_ground_truth"]
        path = fetch(pin["url"], pin["filename"], pin["sha256"], args.raw_dir, ID)
        evidence[trial] = np.loadtxt(path, dtype=np.int64)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=30,
        time_column=("frame_id", pa.int32()),
        label_columns={"label_action": pa.int8()},
        meta_columns={
            "subject_id": pa.int16(),
            "trial_number": pa.int16(),
            "camera_serial": pa.string(),
            "source_native_frames": pa.int32(),
            "missing_skeleton_frames": pa.int32(),
            "ambiguous_pose_frames": pa.int32(),
            "unassigned_skeleton_blocks": pa.int32(),
            "missing_label_frames": pa.int32(),
            "duplicate_timestamps": pa.int32(),
            "timestamp_reversals": pa.int32(),
            "signal_sha256_float32": pa.string(),
            "source_label_trial": pa.string(),
        },
    )
    auxiliary_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("frame_id", pa.int32()),
            ("device_timestamp_us", pa.int64()),
            ("body_id", pa.int64()),
            ("source_action", pa.int8()),
            ("source_repetition", pa.int8()),
        ]
    )
    original_label_schema = pa.schema(
        [
            ("source_declared_trial", pa.string()),
            ("source_frame_id", pa.int32()),
            ("source_action", pa.int8()),
            ("source_repetition", pa.int8()),
        ]
    )
    unassigned_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("frame_id", pa.int32()),
            ("source_block_index", pa.int16()),
            ("source_body_id", pa.uint64()),
            ("reason", pa.string()),
            ("values", pa.list_(pa.float32())),
        ]
    )
    unassigned_count = 0
    stats = Statistics()
    projections, subject_ids, timestamp_counts, confidence_counts = (
        [],
        set(),
        Counter(),
        Counter(),
    )
    bytes_added, total_missing_skeletons, total_missing_labels = 0, 0, 0
    frame_count = 0
    substantive_recurrence = []
    source_instances, source_repetitions = Counter(), Counter()
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "source_frames.parquet", auxiliary_schema, compression="zstd"
        ) as auxiliary,
        pq.ParquetWriter(
            args.out_dir / "unassigned_skeletons.parquet",
            unassigned_schema,
            compression="zstd",
        ) as unassigned_writer,
        pq.ParquetWriter(
            args.out_dir / "original_labels.parquet",
            original_label_schema,
            compression="zstd",
        ) as original_label_writer,
    ):
        for trial, pin in pins.items():
            raw, source_labels, actual = acquire(
                raw_root, trial, pin["source_bytes"], pin
            )
            original = np.loadtxt(io.BytesIO(source_labels), dtype=np.int32)
            original_label_writer.write_table(
                pa.Table.from_pydict(
                    {
                        "source_declared_trial": [trial] * len(original),
                        "source_frame_id": original[:, 0],
                        "source_action": original[:, 1],
                        "source_repetition": original[:, 2],
                    },
                    schema=original_label_schema,
                )
            )
            label_trial = corrections.get(trial, {}).get("source_label_trial", trial)
            if label_trial != trial:
                label_pin = pins[label_trial]
                label_path = fetch(
                    label_pin["label_url"],
                    f"{label_trial}.Labels.txt",
                    label_pin["label_sha256"],
                    args.raw_dir,
                    ID,
                )
                source_labels = label_path.read_bytes()
                canonical_rows = np.loadtxt(io.BytesIO(source_labels), dtype=np.int64)
                assert np.array_equal(canonical_rows[:, 1], evidence[trial])
            x, timestamps, bodies, action, repetition, unassigned = decode(
                raw, source_labels
            )
            n = len(x)
            assert n == pin["frames"]
            assert len(unassigned) == pin["unassigned_skeleton_blocks"]
            observed = timestamps >= 0
            assigned = bodies >= 0
            time_diffs = np.diff(timestamps[observed])
            duplicates = int((time_diffs == 0).sum())
            reversals = int((time_diffs < 0).sum())
            timestamp_counts.update({"duplicates": duplicates, "reversals": reversals})
            conf, conf_n = np.unique(x[assigned, ::12], return_counts=True)
            confidence_counts.update(
                {str(float(k)): int(v) for k, v in zip(conf, conf_n, strict=True)}
            )
            missing_skeletons = int((~assigned).sum())
            missing_labels = int((action == -1).sum())
            total_missing_skeletons += missing_skeletons
            total_missing_labels += missing_labels
            starts = np.r_[
                0,
                np.flatnonzero(
                    (action[1:] != action[:-1]) | (repetition[1:] != repetition[:-1])
                )
                + 1,
            ]
            source_instances.update(int(v) for v in action[starts] if v >= 0)
            source_repetitions.update(int(v) for v in action[repetition > 0])
            subject = int(trial[3:6])
            subject_ids.add(subject)
            fid = np.arange(n, dtype=np.int32)
            writer.add_series(
                trial,
                {c: x[:, i] for i, c in enumerate(CHANNELS)},
                time=fid,
                labels={"label_action": action},
                meta={
                    "subject_id": subject,
                    "trial_number": int(trial[7:]),
                    "camera_serial": pin["camera"],
                    "source_native_frames": pin["native_frames"],
                    "missing_skeleton_frames": missing_skeletons,
                    "ambiguous_pose_frames": pin["ambiguous_frames"],
                    "unassigned_skeleton_blocks": len(unassigned),
                    "missing_label_frames": missing_labels,
                    "duplicate_timestamps": duplicates,
                    "timestamp_reversals": reversals,
                    "signal_sha256_float32": fingerprint(x),
                    "source_label_trial": label_trial,
                },
            )
            auxiliary.write_table(
                pa.Table.from_pydict(
                    {
                        "series_id": [trial] * n,
                        "frame_id": fid,
                        "device_timestamp_us": pa.array(timestamps, mask=~observed),
                        "body_id": pa.array(bodies, mask=~assigned),
                        "source_action": pa.array(action, mask=action == -1),
                        "source_repetition": pa.array(
                            repetition, mask=repetition == -1
                        ),
                    },
                    schema=auxiliary_schema,
                )
            )
            if unassigned:
                unassigned_writer.write_table(
                    pa.Table.from_pylist(
                        [{"series_id": trial, **row} for row in unassigned],
                        schema=unassigned_schema,
                    )
                )
                unassigned_count += len(unassigned)
            action_starts = np.r_[0, np.flatnonzero(action[1:] != action[:-1]) + 1]
            values = action[action_starts]
            _, counts = np.unique(values[values > 0], return_counts=True)
            substantive_recurrence.append(
                {"series_id": trial, "recurrent": bool(np.any(counts > 1))}
            )
            stats.add(trial, {"label_action": action})
            frame_count += n
            bytes_added += pin["source_bytes"]
            part = writer.parts["default"]
            pending_ids = {row["series_id"] for row in part.buf}
            pending_bytes = sum(pins[t]["source_bytes"] for t in pending_ids)
            flushed_source = bytes_added - pending_bytes
            disk = sum((args.out_dir / p).stat().st_size for p in part.files)
            ratio = max(output_floor, disk / flushed_source if flushed_source else 0)
            remaining = manifest["source_bytes"] - flushed_source
            free = shutil.disk_usage(raw_root).free
            projected = free - remaining * ratio * 1.25 - 96 * 2**20
            projections.append(
                {
                    "trial": trial,
                    "free_bytes": free,
                    "projected_peak_free_bytes": projected,
                }
            )
            if projected < RESERVE:
                raise RuntimeError(
                    "Rolling complete-view output projection breaches18-GiB reserve"
                )
            if len(stats.rows) % 10 == 0:
                print(
                    f"{len(stats.rows)}/217 trials; projected peak free={projected / 2**30:.3f}GiB",
                    flush=True,
                )
    assert len(stats.rows) == 217 and subject_ids == set(range(1, 42))
    recurrence_note = (
        f" State recurrence occurs in {stats.summary()['tracks']['label_action']['series_with_recurrence']}/{len(stats.rows)} recordings when ordinary null state 0 is included, "
        f"versus {sum(r['recurrent'] for r in substantive_recurrence)}/{len(stats.rows)} for substantive action classes 1–12 only. "
        "Repetition-index changes within a sustained action class are retained in source_frames.parquet and are distinct from semantic state transitions."
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="HA4M: all 217 native skeleton recordings and assembly action labels",
        source=SOURCE,
        sha256=sha256(PIN_FILE),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=f"{REPOSITORY}/-/blob/{REVISION}/LICENSE",
        license_verified_date="2026-10-20",
        description="All 217 assembly recordings from 41 subjects; all 32 native Kinect joints with 384 observations per frame (confidence, XYZ, quaternion and color/depth projections), plus original framewise action and repetition annotations. Invalid-ID and ambiguous multi-body pose blocks are preserved separately. Nominal 30 fps, actual source timestamps retained separately.",
        collection="Microsoft Azure Kinect recordings of 41 volunteers assembling an epicyclic gear train in two laboratories. Primary source paper reports217 recordings. The author-linked public ownCloud snapshot exposes exactly 217 matching trial folders, each with Skeletons and Labels.txt. All source file bytes are retained in a lossless compressed local cache until validation; no imagery or demographics are included. Skeleton coordinates are the provider's Azure Kinect Body Tracking SDK 1.1.2 estimates, not raw optical measurements.",
        annotation="One released manual framewise ground truth, cross-checked by two researchers using RGB video and wrist trajectories. Source action 0 denotes annotated transitions and unexpected events such as losing a component; retain as an ordinary scored null state. The paper excludes 0 only from its descriptive assembly statistics; a masked sensitivity analysis may follow that convention. Codes 1–12 are assembly actions. Action labels belong to source frames/trials, not individual SDK BodyIDs. Original repetition index 0–2 is preserved separately, not treated as another annotator or a new action taxonomy. Original IDU039V001/V002 annotation CSV associations are reversed relative to later primary-author GroundTruth: the complete action vector in each later trial file exactly equals the other original CC-BY CSV. Default swaps the two original CSV associations and retains their original action/repetition rows; source_label_trial records this mapping. This is explicit author-supported association evidence, not a guessed offset or length match. Both later GT files are SHA-pinned evidence only and are not packaged or rehosted because their repository has no explicit licence. Every original declared CSV row is preserved unchanged in original_labels.parquet. Missing annotation rows alone become -1. Frame IDs align label rows with skeleton observations, as documented by the source's common frame filenames and wrist-trajectory annotation checks. RGB/IR delay is described as much smaller on average than one frame; labels have nominal frame precision, not exact physical onset timing.",
        conversion="Keep all 384 numeric observations, in native joint order, cast once to float32. No smoothing, centering, coordinate conversion, quaternion normalization, resampling, confidence masking, selection of limbs, clipping, event cropping or joining trials. Preserve zero projections and low-confidence predictions. Source files may omit undetected skeletons: retain the union of frame IDs and label IDs, with NaN signals for missing skeleton frames and -1 only for absent labels. Frame IDs are the series grid at nominal 30 fps; source IR-device microsecond timestamps and body IDs are stored in source_frames.parquet, including duplicates and reversals. Do not infer missing timestamps. Each native block contains one observation of every joint 0–31. The main view requires a unique valid SDK body ID per frame. Preserve all blocks with SDK invalid ID 0xFFFFFFFF, including nonzero values, in unassigned_skeletons.parquet; frames with no valid ID get NaNs in the main view. For multiple valid IDs, leave all 384 main values NaN on that frame and preserve every valid and invalid block in the auxiliary table. Frame action labels remain unchanged; never choose an actor from body order, coverage or posture. Ordinary unique-valid blocks are represented once in main, with source BodyID in source_frames.parquet; every remaining block is stored once in auxiliary with frame, original block index, full ID and reason. The original numeric block order can be reconstructed by inserting the main block into the sole unused block index. One complete config avoids duplicate samples under the 18-GiB storage reserve. Download only bounded per-trial Skeletons ZIPs and Labels.txt from the author-linked share, never full-trial image archives. Generated ZIP envelopes have variable metadata and no useful compression: store them losslessly as gzip, with no second full on-disk ZIP. SHA256 pins cover deterministic sorted native member paths, length prefixes and original bytes, plus each literal Labels.txt; CRC and complete source byte counts are checked. All 217 trials are pinned before builder execution; qualification is a separate explicit command.",
        limitations="Provider skeleton estimates include occlusion, tracking artefacts, zero out-of-image projections and possible body-ID changes. A unique valid SDK ID does not establish participant identity; no person-specific action labels or cross-ID identity stitching are asserted. Source timestamps are not an exact strictly increasing 30-Hz clock. Nominal frame labels do not guarantee sub-frame synchronization. Missing detections, invalid-ID-only frames and ambiguous multi-valid-body frames have structural NaNs in main without interpolation; every published pose estimate remains available in auxiliary data for the latter cases. Single released ground truth prevents independent inter-rater agreement measurement. The paper reports 4,124 total action instances and separately 435 don't-care instances, while repository README reports 4,123 including don't-care: retain measured label statistics without repairing this source discrepancy. The live share is versionless; content hashes bind this 217-trial snapshot. Publication requires preserving a stable source snapshot or equivalent primary availability."
        + recurrence_note,
        biases="Small convenience cohort and two fixed laboratory setups; constrained assembly task, varying participant skill and action execution speed. Use subject-disjoint evaluation and disclose laboratory/camera context. Repeated trials from one subject are not independent subjects.",
        personal="Pseudonymous subject/trial and device IDs plus movement signals only. No RGB/depth imagery, faces, participant attributes, demographic tables or linkage to identities is included. Device-relative timestamps are retained, not wall-clock recording dates.",
        citation="Cicirelli G., Marani R., Romeo L., García Domínguez M., Heras J., Perri A.G., D'Orazio T. (2022). The HA4M dataset: Multi-Modal Monitoring of an assembly task for Human Action recognition in Manufacturing. Scientific Data 9:745. doi:10.1038/s41597-022-01843-z. Dataset doi:10.57760/sciencedb.01872.",
        creators=[
            "Grazia Cicirelli",
            "Roberto Marani",
            "Laura Romeo",
            "Manuel García Domínguez",
            "Jónathan Heras",
            "Anna Gina Perri",
            "Tiziana D'Orazio",
        ],
        date_published="2022-12-01",
        null_states={"label_action": [0]},
        info={
            "state_names": {"label_action": STATES},
            "default_label": "label_action",
            "annotators": [],
            "n_released_annotation_tracks": 1,
            "reference_doi": "https://doi.org/10.1038/s41597-022-01843-z",
            "source_repository": REPOSITORY,
            "source_repository_revision": REVISION,
            "source_files": manifest,
            "subjects": 41,
            "source_frames": frame_count,
            "corrected_label_associations": corrections,
            "substantive_action_recurrence": substantive_recurrence,
            "series_with_substantive_action_recurrence": sum(
                r["recurrent"] for r in substantive_recurrence
            ),
            "source_action_repetition_run_counts": dict(source_instances),
            "source_nonzero_repetition_frames_by_action": dict(source_repetitions),
            "native_joint_ids": list(range(32)),
            "native_observation_fields": FIELDS,
            "native_units": {
                c: (
                    "mm"
                    if c.rsplit("_", 1)[1] in ["x", "y", "z"]
                    else "pixel"
                    if "2d" in c
                    else "dimensionless"
                )
                for c in CHANNELS
            },
            "nominal_sampling_rate_hz": 30,
            "source_time_column": "source_frames.parquet:device_timestamp_us",
            "timestamp_counts": dict(timestamp_counts),
            "confidence_value_counts": dict(confidence_counts),
            "missing_skeleton_frames": total_missing_skeletons,
            "unassigned_skeleton_blocks": unassigned_count,
            "ambiguous_pose_frames": sum(p["ambiguous_frames"] for p in pins.values()),
            "source_skeleton_blocks": sum(
                p["source_skeleton_blocks"] for p in pins.values()
            ),
            "invalid_sdk_body_blocks": sum(
                p["invalid_sdk_blocks"] for p in pins.values()
            ),
            "invalid_body_id_reference": "https://microsoft.github.io/Azure-Kinect-Body-Tracking/release/1.1.x/k4abttypes_8h_source.html",
            "missing_label_frames": total_missing_labels,
            "disk_reserve_bytes": RESERVE,
            "disk_projections": projections,
            "auxiliary": {
                "original_labels.parquet": "Every literal original CC-BY annotation row with its original declared trial/frame IDs, action and repetition. Two original trial39 associations disagree with later primary-author evidence; default uses the documented association correction. No author feature GT file is rehosted.",
                "source_frames.parquet": "Every retained source frame ID, native device timestamp where present, valid body ID, literal action and repetition index. Null timestamp means no source skeleton file; null body means no valid SDK ID; null action/repetition means absent annotation.",
                "unassigned_skeletons.parquet": "Every native 32-joint block absent from the main array: invalid SDK-ID blocks and all valid blocks on ambiguous frames. Frame ID, full unsigned BodyID, original block index, reason, and all 384 values in channel order. Ordinary unique-valid main blocks are not duplicated.",
            },
        },
    )


if __name__ == "__main__":
    main()
