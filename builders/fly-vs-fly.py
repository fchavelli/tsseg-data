"""Build the complete released articulated tracking view of Fly vs. Fly."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from tsseg_data.batch import Statistics, finish
from tsseg_data.build import parse_args
from tsseg_data.fly_vs_fly import (
    BEHAVIORS,
    CHANNELS,
    RESERVE,
    SOURCE_NAMES,
    TRACKS,
    acquire,
    checked,
    dense,
)
from tsseg_data.format import DatasetSpec, DatasetWriter
from tsseg_data.sources import sha256

ID = "fly-vs-fly"
SOURCE = "https://data.caltech.edu/records/zrznw-w7386"
PINS = Path(__file__).parent / "checksums/fly-vs-fly.json"


def main():
    args = parse_args(
        ID, extra=lambda p: p.add_argument("--pilot", action="store_true")
    )
    pins = json.loads(
        (Path("raw/fly-vs-fly-inventory.json") if args.pilot else PINS).read_text()
    )
    raw = args.raw_dir / ID
    if not args.pilot:
        acquire(raw, pins)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=None,
        time_column=("time_ns", pa.int64()),
        label_columns={t: pa.int8() for t in TRACKS},
        meta_columns={
            "subset": pa.string(),
            "source_track_member": pa.string(),
            "sampling_rate_hz": pa.float64(),
            "source_annotation_members": pa.list_(pa.string()),
        },
    )
    stats = Statistics()
    bout_rows = []
    flag_rows = []
    metadata = []
    split_metadata = []
    agreement = []
    positive_recurrence = {track: 0 for track in TRACKS}
    overlap_frames = {}
    with DatasetWriter(args.out_dir, spec) as writer:
        for archive in pins["archives"]:
            lookup = {p["name"]: p for p in archive["members"]}
            base = raw / archive["name"].removesuffix(".zip")
            split_pin = next(
                p for p in lookup.values() if p["name"].endswith("traintest.mat")
            )
            split = checked(base / split_pin["name"], split_pin)
            split_metadata.append(
                {
                    "archive": archive["name"],
                    "movienames": list(map(str, np.atleast_1d(split["movienames"]))),
                    "trainids": list(map(int, np.atleast_1d(split["trainids"]))),
                    "testids": list(map(int, np.atleast_1d(split["testids"]))),
                    "n_annotated_flies": int(split["n_flies"]),
                }
            )
            for pin in archive["members"]:
                if not pin["name"].endswith("_track.mat") or (
                    args.pilot and "/movie1/" not in pin["name"]
                ):
                    continue
                sid = (
                    pin["name"]
                    .removesuffix("_track.mat")
                    .replace("/", "__")
                    .replace(" ", "_")
                )
                trk = checked(base / pin["name"], pin)["trk"]
                assert list(trk["names"]) == SOURCE_NAMES and set(trk) == {
                    "names",
                    "data",
                    "flag_frames",
                }, (sid, list(trk))
                x = trk["data"]
                assert x.ndim == 3 and x.shape[0] == 2 and x.shape[2] == 17
                n = x.shape[1]
                rate = 200 if archive["name"].startswith("Boy") else 30
                flags = np.asarray(trk["flag_frames"])
                assert flags.ndim == 1 and set(np.unique(flags)) <= {0, 1}
                starts = np.flatnonzero(np.r_[True, flags[1:] != flags[:-1]])
                for start, end in zip(
                    starts, np.r_[starts[1:], len(flags)], strict=True
                ):
                    flag_rows.append(
                        {
                            "series_id": sid,
                            "start": int(start),
                            "end_exclusive": int(end),
                            "flag_frames": int(flags[start]),
                        }
                    )
                labels = {}
                members = []
                for annotation, suffix in [
                    ("primary", "_actions.mat"),
                    ("second", "_second_actions.mat"),
                ]:
                    name = pin["name"].replace("_track.mat", suffix)
                    action = (
                        checked(base / name, lookup[name]) if name in lookup else None
                    )
                    if action is not None:
                        members.append(name)
                    labels.update(
                        dense(
                            action, n, annotation, bout_rows, sid, int(split["n_flies"])
                        )
                    )
                for fly in range(1, int(split["n_flies"]) + 1):
                    for beh in BEHAVIORS:
                        first = labels[f"label_primary_fly{fly}_{beh}"]
                        second = labels[f"label_second_fly{fly}_{beh}"]
                        known = (first >= 0) & (second >= 0)
                        if known.any():
                            a = first[known]
                            b = second[known]
                            observed = float(np.mean(a == b))
                            p = float(np.mean(a == 1))
                            q = float(np.mean(b == 1))
                            expected = p * q + (1 - p) * (1 - q)
                            agreement.append(
                                {
                                    "series_id": sid,
                                    "fly": fly,
                                    "behavior": beh,
                                    "scored_frames": int(known.sum()),
                                    "accuracy": observed,
                                    "cohen_kappa": (observed - expected)
                                    / (1 - expected)
                                    if expected < 1
                                    else None,
                                }
                            )
                movie = Path(pin["name"]).parent.name
                # Courtship official split lists include cohort prefixes; never guess a match.
                movie_names = list(np.atleast_1d(split["movienames"]))
                relative = pin["name"].split("/", 1)[1].rsplit("/", 1)[0]
                candidates = [
                    i + 1
                    for i, name in enumerate(movie_names)
                    if str(name) in (movie, relative)
                ]
                selected = None
                if len(candidates) == 1:
                    i = candidates[0]
                    selected = (
                        "train"
                        if i in np.atleast_1d(split["trainids"])
                        else "test"
                        if i in np.atleast_1d(split["testids"])
                        else None
                    )
                writer.add_series(
                    sid,
                    {
                        c: x[f, :, j].astype(np.float32)
                        for (f, j), c in zip(
                            [(f, j) for f in range(2) for j in range(17)],
                            CHANNELS,
                            strict=True,
                        )
                    },
                    time=np.arange(n, dtype=np.int64) * 1_000_000_000 // rate,
                    labels=labels,
                    split=selected,
                    meta={
                        "subset": archive["name"].removesuffix(".zip"),
                        "source_track_member": pin["name"],
                        "sampling_rate_hz": float(rate),
                        "source_annotation_members": members,
                    },
                )
                stats.add(sid, labels)
                for track, y in labels.items():
                    positive_recurrence[track] += int(
                        np.count_nonzero((y == 1) & np.r_[True, y[1:] != y[:-1]]) > 1
                    )
                overlap_frames[sid] = {
                    f"{slot}_fly{fly}": int(
                        np.count_nonzero(
                            np.sum(
                                [
                                    labels[f"label_{slot}_fly{fly}_{b}"] == 1
                                    for b in BEHAVIORS
                                ],
                                axis=0,
                            )
                            > 1
                        )
                    )
                    for slot in ["primary", "second"]
                    for fly in [1, 2]
                }
                metadata.append(
                    {
                        "series_id": sid,
                        "n_frames": n,
                        "n_source_flag_frames": len(flags),
                        "flag_frame_length_difference": len(flags) - n,
                        "sampling_rate_hz": rate,
                        "nan_observations": int(np.isnan(x).sum()),
                        "flag_values": list(map(int, np.unique(flags))),
                    }
                )
                if shutil.disk_usage(raw).free < RESERVE:
                    raise RuntimeError("18-GiB reserve breached")
                print(sid, n, flush=True)
    if not args.pilot:
        assert len(stats.rows) == pins["expected_series"]
        assert sum(row["length"] for row in stats.rows) == pins["expected_samples"]
    pq.write_table(
        pa.Table.from_pylist(bout_rows),
        args.out_dir / "bouts.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(flag_rows),
        args.out_dir / "tracking-flags.parquet",
        compression="zstd",
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Fly vs. Fly: complete native two-fly articulated tracking view",
        source=SOURCE,
        sha256=sha256(PINS) if not args.pilot else "pilot",
        license_spdx="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-20",
        description="All released native track.mat trajectories and action bout files across Boy meets boy, Aggression and Courtship, with both flies and all 17 native fields per fly. Videos and derived feat.mat descriptors are outside this tracking view.",
        collection="Pairs of fruit flies in controlled laboratory arenas: two males in Boy meets boy and Aggression, male/female Courtship cohorts. Published trajectories are computer-vision estimates, not direct measurements of articulation. Retain all released tracking trials, including any outside official training/test lists.",
        annotation="Expert action bouts are one-based inclusive intervals, as implemented by the primary author visualizer. Preserve simultaneous behaviors as separate binary tracks per fly, behavior and released primary/second annotation file; no exclusive taxonomy or consensus. The official Courtship split declares n_flies=1: only fly1 is annotated; fly2 behavior tracks remain entirely -1 despite empty second-row cells. A behavior explicitly present in behs for an annotated fly has ordinary negative state 0 outside its positive bouts. Explicit unknown bouts mask every behavior to -1 for that fly. Absent behavior vocabulary or absent second annotation file is entirely -1. Second tracks are trial-local; no global annotator identity is asserted. Original bouts and certainty third column are retained without reinterpretation in bouts.parquet.",
        conversion="Fetch only exact bounded HTTP206 local-header/payload ranges from the three primary ZIPs; CRC, sizes and native SHA256 are pinned. MATLAB parsing loads numeric arrays only and never executes source code. Flatten fly1 then fly2 fields, cast once to float32 and preserve NaNs. No interpolation, smoothing, coordinate normalization or new feature extraction. Preserve every literal flag_frames entry as run intervals in tracking-flags.parquet with its own native length, without treating it as behavior ground truth. Five Courtship wild trials (4,5,10,13,17) contain 54,000 flag entries for 53,999 trajectory frames: preserve the extra terminal entry only in the auxiliary table; do not invent another trajectory frame. Native frame cadence is 200 fps for Boy meets boy and 30 fps for Aggression/Courtship according to the primary thesis; time_ns=floor(frame_index*1e9/fps), no absolute timestamps. Global sampling_rate_hz=null because cohorts have different rates; per-series rate is retained.",
        limitations="Tracking errors, missing poses, uncertain identities and source flag_frames remain unrepaired. The released flag_frames field differs from the current FlyTracker documentation five-column trk.flags format: no unsupported mapping is made. Missing behavior vocabulary cannot establish negative ground truth. Default label_primary_fly1_wing_extension is a convenience, not a consensus; it is unscored in the Aggression subset. Negative samples recur heavily; binary recurrence alone does not establish diverse substantive states. Multiple fly, behavior and annotation tracks share the same video and are correlated. Rounded nanosecond time encodes the documented nominal frame grid, not camera timing jitter. Concordance between released files compares overlapping scored binary labels only; independent rater status is unverified. Negative prevalence and shared scene correlation limit interpretation. Dataset source counts are measured from released members, not inferred from paper summaries.",
        biases="Laboratory fruit flies, selected social behaviors and genetic manipulation; controlled arenas and tracking software affect observations. Use source trial/cohort or original split partitions; never split correlated overlapping windows or two flies into independent random folds.",
        personal="Fruit-fly pose trajectories and pseudonymous movie/cohort names only; no human images or personal attributes.",
        citation="Eyjolfsdottir E., Branson S., Burgos-Artizzu X.P., Hoopfer E.D., Schor J., Anderson D.J., Perona P. (2014). Detecting social actions of fruit flies. ECCV. Dataset doi:10.22002/D1.1893.",
        creators=[
            "Eyrun Eyjolfsdottir",
            "Steve Branson",
            "Xavier P. Burgos-Artizzu",
            "Eric D. Hoopfer",
            "Jonathan Schor",
            "David J. Anderson",
            "Pietro Perona",
        ],
        date_published="2021-02-24",
        null_states={t: [0] for t in TRACKS},
        info={
            "state_names": {t: {0: "absent", 1: "present"} for t in TRACKS},
            "default_label": "label_primary_fly1_wing_extension",
            "annotators": [],
            "released_annotation_file_concordance": {
                "method": "Concordance between released files: per-trial/fly/behavior Cohen kappa and accuracy over overlapping scored frames; independence and rater identity unverified",
                "comparisons": agreement,
            },
            "official_splits": split_metadata,
            "auxiliary": {
                "bouts.parquet": "Every literal source bout with one-based inclusive frame endpoints and original certainty; preserves overlapping actions.",
                "tracking-flags.parquet": "Lossless run encoding of literal shared trk.flag_frames; zero-based half-open frame intervals.",
            },
            "tracks": {
                t: {
                    "annotation_slot": t.split("_")[1],
                    "fly": t.split("_")[2],
                    "behavior": t.split("_", 3)[3],
                }
                for t in TRACKS
            },
            "source_files": pins,
            "source_channel_names": SOURCE_NAMES,
            "series_details": metadata,
            "series_with_positive_recurrence": positive_recurrence,
            "frames_with_simultaneous_positive_behaviors": overlap_frames,
            "tracking_flags_semantics": "Literal source trk.flag_frames; no invented identity-swap interpretation",
            "source_thesis": "https://thesis.library.caltech.edu/10281/7/eyjolfsdottir_eyrun_2017.pdf",
            "source_scope": "All released track.mat, primary and second actions.mat and traintest.mat; excludes movies, derived feat.mat and AppleDouble metadata",
        },
    )


if __name__ == "__main__":
    main()
