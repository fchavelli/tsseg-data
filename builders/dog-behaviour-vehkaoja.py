"""Retain native dual-IMU dog tests, tasks and simultaneous video annotations."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.labels import runs  # noqa: E402
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "dog-behaviour-vehkaoja"
SOURCE = "https://data.mendeley.com/datasets/vxhx934tbn/4"
PIN_FILE = Path(__file__).parent / "checksums" / f"{ID}.json"
OVERLAP_FILE = PIN_FILE.with_name(f"{ID}-bebe-overlap.json")
CHANNELS = [
    f"{sensor}{place}_{axis}"
    for sensor in ["A", "G"]
    for place in ["Back", "Neck"]
    for axis in "xyz"
]
ANNOTATIONS = ["Task", "Behavior_1", "Behavior_2", "Behavior_3", "PointEvent"]
UNDEFINED = "<undefined>"
TECHNICAL = {"Synchronization", "Extra_Synchronization"}
TOTAL_SAMPLES = 10_611_068
RESERVE = 18 * 2**30


def source_tests(path):
    """Stream the single CSV into complete, contiguous DogID/TestNum groups."""
    seen, pieces, current = set(), [], None
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == ["DogMoveData.csv"]
        with archive.open("DogMoveData.csv") as stream:
            for chunk in pd.read_csv(stream, chunksize=262144, keep_default_na=False):
                assert (
                    list(chunk.columns)
                    == ["DogID", "TestNum", "t_sec"] + CHANNELS + ANNOTATIONS
                )
                # Each pair must be contiguous even within a parser chunk.
                pairs = chunk[["DogID", "TestNum"]].to_numpy()
                cuts = np.r_[
                    0,
                    np.flatnonzero(np.any(pairs[1:] != pairs[:-1], axis=1)) + 1,
                    len(chunk),
                ]
                for start, end in zip(cuts[:-1], cuts[1:], strict=True):
                    pair = tuple(int(v) for v in pairs[start])
                    if pair != current:
                        if current is not None:
                            yield current, pd.concat(pieces, ignore_index=True)
                        assert pair not in seen, f"Noncontiguous source test: {pair}"
                        seen.add(pair)
                        current, pieces = pair, []
                    pieces.append(chunk.iloc[start:end].copy())
            if current is not None:
                yield current, pd.concat(pieces, ignore_index=True)
        # Exhausting ZipExtFile verifies the member CRC, including the final test.


def make_spec():
    return DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=100,
        time_column=("time_ns", pa.int64()),
        label_columns={"label_behavior": pa.int16(), "label_task": pa.int8()},
        meta_columns={
            "dog_id": pa.int16(),
            "test_number": pa.int8(),
            "source_first_row": pa.int64(),
            "source_last_row_exclusive": pa.int64(),
            "source_time_start_s": pa.float64(),
            "source_time_end_s": pa.float64(),
            "overlap_group": pa.string(),
            "bebe_series_id": pa.string(),
            "signal_sha256_float32": pa.string(),
            "bebe_signals_exact_match": pa.bool_(),
        },
    )


def reserve_projection(root, writer, processed):
    part = writer.parts["default"]
    disk_bytes = sum((root / name).stat().st_size for name in part.files)
    pending = sum(row["length"] for row in part.buf)
    flushed = processed - pending
    actual_ratio = disk_bytes / flushed if flushed else 0
    # Prefix pilot measured 35.16 bytes/sample; use a 55-byte floor plus 25%.
    needed = max(0, TOTAL_SAMPLES - flushed) * max(55, actual_ratio) * 1.25 + 64 * 2**20
    free = shutil.disk_usage(root).free
    if free - needed < RESERVE:
        raise RuntimeError("Projected peak free below 18-GiB reserve")
    return {
        "processed_samples": processed,
        "free_bytes": free,
        "projected_peak_free_bytes": free - needed,
        "measured_bytes_per_sample": actual_ratio,
    }


def main():
    args = parse_args(ID)
    raw = args.raw_dir / ID
    raw.mkdir(parents=True, exist_ok=True)
    pins = json.loads(PIN_FILE.read_text())
    missing = sum(p["bytes"] for name, p in pins.items() if not (raw / name).exists())
    if shutil.disk_usage(raw).free - missing - 2**30 < RESERVE:
        raise RuntimeError(
            "Source plus conservative 1-GiB output budget breaches reserve"
        )
    files = {
        name: fetch(pin["url"], name, pin["sha256"], args.raw_dir, ID)
        for name, pin in pins.items()
    }
    assert all(files[name].stat().st_size == pin["bytes"] for name, pin in pins.items())
    overlaps = json.loads(OVERLAP_FILE.read_text())
    schema = pa.schema(
        [("series_id", pa.string()), ("start", pa.int32()), ("end", pa.int32())]
        + [(c, pa.string()) for c in ANNOTATIONS]
    )
    spec, stats = make_spec(), Statistics()
    tasks, combinations, atomic = {}, {}, set()
    processed, animals, simultaneous = 0, set(), Counter()
    annotation_spans, bark_episodes, bark_samples = 0, 0, 0
    source_categories = {c: set() for c in ANNOTATIONS}
    projections, recurrence = [], []
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "source_annotations.parquet", schema, compression="zstd"
        ) as annotations,
    ):
        projections.append(reserve_projection(args.out_dir, writer, 0))
        for (dog, test), frame in source_tests(files["DogMoveData_csv_format.zip"]):
            sid, n = f"dog_{dog:02}_test_{test}", len(frame)
            assert test in [1, 2] and n > 0
            animals.add(dog)
            times = frame["t_sec"].to_numpy(dtype=np.float64)
            time_ns = np.rint(times * 10**9).astype(np.int64)
            assert np.isfinite(times).all() and np.allclose(
                times, time_ns / 10**9, rtol=0, atol=1e-10
            )
            assert np.array_equal(time_ns, np.arange(n, dtype=np.int64) * 10_000_000)
            signals = {c: frame[c].to_numpy(dtype=np.float32) for c in CHANNELS}
            assert all(np.isfinite(v).all() for v in signals.values())
            fingerprint = hashlib.sha256()
            for channel in CHANNELS:
                fingerprint.update(signals[channel].astype("<f4", copy=False).tobytes())
            match = overlaps[f"{dog}:{test}"]
            assert (
                n == match["samples"]
                and fingerprint.hexdigest() == match["sha256_float32_channels"]
            )
            for c in ANNOTATIONS:
                source_categories[c].update(frame[c].unique())
            codes, tuples = pd.factorize(
                pd.MultiIndex.from_frame(frame[ANNOTATIONS]), sort=False
            )
            task_lut, behavior_lut, behavior_keys = [], [], []
            for task, *other in tuples:
                if task != UNDEFINED and task not in tasks:
                    tasks[task] = len(tasks)
                task_lut.append(tasks.get(task, -1))
                combination = tuple(sorted(set(other[:3]) - {UNDEFINED}))
                atomic.update(combination)
                if combination and combination not in combinations:
                    combinations[combination] = len(combinations)
                behavior_lut.append(combinations.get(combination, -1))
                behavior_keys.append(combination)
            labels = {
                "label_behavior": np.array(behavior_lut, dtype=np.int16)[codes],
                "label_task": np.array(task_lut, dtype=np.int8)[codes],
            }
            values, starts, lengths = runs(codes)
            rows = []
            for value, start, length in zip(values, starts, lengths, strict=True):
                rows.append(
                    {
                        "series_id": sid,
                        "start": int(start),
                        "end": int(start + length),
                        **dict(zip(ANNOTATIONS, tuples[value], strict=True)),
                    }
                )
            annotations.write_table(pa.Table.from_pylist(rows, schema=schema))
            annotation_spans += len(rows)
            point_values = frame["PointEvent"].to_numpy()
            bark_samples += int(np.count_nonzero(point_values == "Bark"))
            bark_episodes += int(np.count_nonzero(runs(point_values)[0] == "Bark"))
            slot_count = np.count_nonzero(
                frame[["Behavior_1", "Behavior_2", "Behavior_3"]].to_numpy()
                != UNDEFINED,
                axis=1,
            )
            unique, counts = np.unique(slot_count, return_counts=True)
            simultaneous.update(
                {int(k): int(v) for k, v in zip(unique, counts, strict=True)}
            )
            episode_counts = {}
            for behavior in sorted(set().union(*map(set, behavior_keys)) - TECHNICAL):
                present = np.array(
                    [behavior in key for key in behavior_keys], dtype=bool
                )[codes]
                episode_counts[behavior] = int(present[0]) + int(
                    np.count_nonzero(present[1:] & ~present[:-1])
                )
            recurrence.append(
                {
                    "series_id": sid,
                    "substantive_positive_episodes": episode_counts,
                    "substantive_recurrent": any(
                        v > 1 for v in episode_counts.values()
                    ),
                }
            )
            writer.add_series(
                sid,
                signals,
                labels=labels,
                time=time_ns,
                meta={
                    "dog_id": dog,
                    "test_number": test,
                    "source_first_row": processed,
                    "source_last_row_exclusive": processed + n,
                    "source_time_start_s": float(times[0]),
                    "source_time_end_s": float(times[-1]),
                    "overlap_group": "bebe/vehkaoja_dogs",
                    "bebe_series_id": match["series_id"],
                    "signal_sha256_float32": fingerprint.hexdigest(),
                    "bebe_signals_exact_match": True,
                },
            )
            stats.add(sid, labels)
            processed += n
            projection = reserve_projection(args.out_dir, writer, processed)
            projections.append(projection)
            if len(stats.rows) % 10 == 0:
                print(
                    f"{len(stats.rows)}/62 tests, {processed} samples; projected peak free {projection['projected_peak_free_bytes'] / 2**30:.2f} GiB",
                    flush=True,
                )
    assert processed == TOTAL_SAMPLES and len(stats.rows) == 62 and len(animals) == 45
    (args.out_dir / "source_description.txt").write_bytes(
        files["Data_description.txt"].read_bytes()
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Dog movement: 62 native dual-IMU tests, tasks and simultaneous behaviors",
        source=SOURCE,
        sha256=sha256(PIN_FILE),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-19",
        date_published="2025-11-05",
        description="Complete primary CSV release: 10,611,068 native 100-Hz samples from 62 tests of 45 dogs, all 12 back/neck accelerometer and gyroscope channels. Retain instructed task separately from observed behavior, including every simultaneous behavior, original slot assignments and Bark point-event spans. All 62 sensor recordings exactly overlap BEBE vehkaoja_dogs after float32 conversion; this release adds original annotation coverage and task/event semantics, not independent sensor evaluation data.",
        collection="Pet dogs of middle-to-large size performed seven instructed tasks at the University of Helsinki: lying, sitting, standing, playing, trotting, walking and treat-searching. Forty-five dogs, with 17 repeated tests. ActiGraph GT9X Link six-axis sensors on the back harness and neck collar sampled at 100 Hz. Two cameras recorded tests for synchronized post-hoc annotation. Group repeated tests by dog; keep this dataset and BEBE vehkaoja_dogs in the same overlap group across training/evaluation.",
        annotation="Two distinct semantics: label_task preserves the literal instructed task, and label_behavior is an unordered set of all simultaneously annotated non-undefined behavior names, represented by a reversible integer category. Behaviors can co-occur; no arbitrary first-label choice, exclusive priority or majority vote. Empty behavior sets and undefined tasks become -1. Undefined unused slots do not remove otherwise observed behaviors. Original three ordered behavior slots, task strings and PointEvent are losslessly retained as contiguous half-open sample spans in source_annotations.parquet, including undefined spans. Bark spans are source point-event annotations; do not infer a sustained behavioral state or invent events from missing entries. Synchronization and Extra_Synchronization remain ordinary annotated technical states, explicitly identified; substantive episode recurrence excludes them. Source video behavior annotation resolution is about one second despite 100-Hz rasterized storage. Task and observed behavior are different semantics, not independent raters; agreement is not applicable.",
        conversion="Primary Mendeley v4 official SHA256/size pinned for complete CSV ZIP and description. CSV is declared equivalent in content to the MAT representation by the primary data paper; download only CSV, never duplicate MAT or extract the 1,985,551,732-byte CSV on disk. Stream bounded parser chunks into complete contiguous dog/test series; exhaust ZIP member to verify CRC. Preserve all source rows, header-based sensor positions, relative source timing and label strings. One float32 cast of numerical signals; no filtering, resampling, normalization, interval expansion, cropping, window joining or behavior rejection. Source decimal time matches an exact elapsed 10-ms grid for every test, stored as integer nanoseconds. Two dense canonical tracks plus original combined annotation spans. SHA256 comparison of every channel array in fixed order proves equality with the corresponding pinned BEBE build for all 62 tests; fingerprints and matching series IDs retained. No reduced-channel duplicate config.",
        limitations="All sensor data duplicates the BEBE dog cohort; annotation views add utility but must not inflate independent dataset or animal counts. Primary TXT claims 63 MAT rows, while released CSV and paper's 45+17 test design yield 62 nonempty test groups; no synthetic extra test created and MAT table-row discrepancy remains unresolved. TXT reverses neck X/Y row descriptions relative to CSV headers and paper Table 2; preserve explicit CSV columns without an inferred physical-axis correction. Provider physical units are not explicitly established by the audited description; retain values without unit conversion. Observed behavior combinations are set-valued; category changes may reflect only a co-occurring tag. Missing observations can separate episodes without proving a true transition. Technical synchronization labels are not animal behaviors. Annotation coverage is selective and does not verify intended-task compliance. PointEvent undefined values are retained literally, with no claim of exhaustive absence annotation. Source has 152,140 samples (1,521.4 s) with three annotation slots, whereas the paper says 15,214 s; retain measured source values without inventing the missing factor of ten. No independent annotator tracks are provided.",
        biases="Controlled indoor sporting hall, guided/leashed pet dogs, rewards and alternating short tasks. Middle-to-large dogs only; behavior coverage excludes ambiguous gait/handler-contact situations. Repeated tests and identical BEBE signals create leakage if split by test/window or collection entry instead of source dog and overlap group.",
        personal="Only pseudonymous dog/test IDs, sensor values, relative time and annotation strings exported. Animal breed/weight/age/sex table, owners, video recordings and absolute dates are not exported.",
        citation="Vehkaoja et al. (2025). Movement Sensor Dataset for Dog Behavior Classification, Mendeley Data v4, doi:10.17632/vxhx934tbn.4. Vehkaoja et al. (2022). Description of movement sensor dataset for dog behavior classification, Data in Brief 40:107822, doi:10.1016/j.dib.2022.107822. Kumpulainen et al. (2021). Dog behaviour classification with movement sensors placed on the harness and the collar, Applied Animal Behaviour Science 241:105393, doi:10.1016/j.applanim.2021.105393.",
        creators=[
            "Antti Vehkaoja",
            "Sanni Somppi",
            "Heini Törnqvist",
            "Anna Valldeoriola Cardó",
            "Pekka Kumpulainen",
            "Heli Väätäjä",
            "Päivi Majaranta",
            "Veikko Surakka",
            "Miiamaaria Kujala",
            "Outi Vainio",
        ],
        info={
            "default_label": "label_behavior",
            "state_names": {
                "label_task": {code: name for name, code in tasks.items()},
                "label_behavior": {
                    code: " + ".join(names) for names, code in combinations.items()
                },
            },
            "behavior_sets": {
                code: list(names) for names, code in combinations.items()
            },
            "atomic_behavior_names": sorted(atomic),
            "technical_only_behavior_codes": [
                code for names, code in combinations.items() if set(names) <= TECHNICAL
            ],
            "technical_annotation_names": sorted(TECHNICAL),
            "substantive_episode_recurrence": recurrence,
            "series_with_substantive_recurrence": sum(
                r["substantive_recurrent"] for r in recurrence
            ),
            "source_categories": {c: sorted(v) for c, v in source_categories.items()},
            "source_annotation_spans": annotation_spans,
            "bark_contiguous_source_spans": bark_episodes,
            "bark_source_samples": bark_samples,
            "simultaneous_annotation_slots_samples": dict(sorted(simultaneous.items())),
            "source_files": pins,
            "overlap_groups": {
                "bebe/vehkaoja_dogs": {
                    "series": 62,
                    "samples": TOTAL_SAMPLES,
                    "float32_sensor_arrays_exact_match": True,
                    "bebe_source_archive_sha256": "9242635dd620363b81ffa699ec0befe9835144a5fe8d6735301131e07456635c",
                    "fingerprint_manifest_sha256": sha256(OVERLAP_FILE),
                }
            },
            "annotation_tracks_are_independent_raters": False,
            "reference_doi": "https://doi.org/10.1016/j.dib.2022.107822",
            "time_description": "Exact relative source time in nanoseconds; 10-ms grid at 100 Hz, starts at zero per test.",
            "label_descriptions": {
                "label_behavior": "Reversible unordered set of simultaneous original behavior annotations",
                "label_task": "Instructed task, independently of observed behavior",
            },
            "storage_sizing": {
                "reserve_bytes": RESERVE,
                "pilot_samples": 24778,
                "pilot_bytes_per_sample": 35.15945596900476,
                "projection_floor_bytes_per_sample": 55,
                "projection_margin": 0.25,
                "metadata_buffer_bytes": 64 * 2**20,
                "rolling_projections": projections,
            },
            "auxiliary": {
                "source_annotations.parquet": "Lossless literal task, three ordered behavior slots and PointEvent strings as half-open sample spans; includes undefined entries and technical synchronization labels."
            },
        },
    )


if __name__ == "__main__":
    main()
