"""Preserve all native EEGMMIDB runs, EDF+ intervals and WFDB conversions."""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from wfdb.io.annotation import proc_ann_bytes  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.labels import runs  # noqa: E402
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "eegmmidb"
SOURCE = "https://physionet.org/content/eegmmidb/1.0.0/"
PROTOCOL = "https://archive.physionet.org/physiobank/database/eegmmidb/?C=M"
PIN_FILE = Path(__file__).parent / "checksums" / f"{ID}.json"
ELECTRODES = "fc5 fc3 fc1 fcz fc2 fc4 fc6 c5 c3 c1 cz c2 c4 c6 cp5 cp3 cp1 cpz cp2 cp4 cp6 fp1 fpz fp2 af7 af3 afz af4 af8 f7 f5 f3 f1 fz f2 f4 f6 f8 ft7 ft8 t7 t8 t9 t10 tp7 tp8 p7 p5 p3 p1 pz p2 p4 p6 p8 po7 po3 poz po4 po8 o1 oz o2 iz".split()
CHANNELS = [f"eeg_{name}_uv" for name in ELECTRODES]
STATES = {0: "T0_rest", 1: "T1_source_code", 2: "T2_source_code"}


def ceil(value):
    return -(-value.numerator // value.denominator)


def read_edf(path):
    """Decode calibrated EEG and literal TAL intervals; verify every record clock.

    No patient/recording fields, dates or absolute device clocks are exported.
    Fractions preserve source decimal times until mapping half-open intervals
    onto the native sample grid. All source EEG samples remain present.
    """
    data = path.read_bytes()
    fixed = data[:256]
    assert fixed[:8] == b"0       "
    nch = int(fixed[252:256])
    header_size = int(fixed[184:192])
    assert nch == 65 and header_size == 256 * (nch + 1)
    assert fixed[192:236].strip() == b"EDF+C"
    records = int(fixed[236:244])
    duration = Fraction(fixed[244:252].decode().strip())
    assert records > 0 and duration > 0
    variable = data[256:header_size]
    fields, pos = {}, 0
    for key, width in [
        ("label", 16),
        ("transducer", 80),
        ("dimension", 8),
        ("physical_min", 8),
        ("physical_max", 8),
        ("digital_min", 8),
        ("digital_max", 8),
        ("prefilter", 80),
        ("samples_per_record", 8),
        ("reserved", 32),
    ]:
        fields[key] = [
            variable[pos + j * width : pos + (j + 1) * width].decode("ascii").strip()
            for j in range(nch)
        ]
        pos += nch * width
    assert pos == len(variable)
    assert fields["label"][-1] == "EDF Annotations"
    assert [s.rstrip(".").lower() for s in fields["label"][:64]] == ELECTRODES
    counts = [int(v) for v in fields["samples_per_record"]]
    assert len(set(counts[:64])) == 1
    fs = Fraction(counts[0], 1) / duration
    step_ns = Fraction(10**9, 1) / fs
    assert step_ns.denominator == 1
    record_width = sum(counts)
    assert len(data) == header_size + records * record_width * 2
    digital = np.frombuffer(data, dtype="<i2", offset=header_size).reshape(
        records, record_width
    )
    headers, signals, offset = [], {}, 0
    for i, channel in enumerate(CHANNELS):
        h = {k: fields[k][i] for k in fields}
        assert h["dimension"] == "uV"
        lo, hi = float(h["physical_min"]), float(h["physical_max"])
        dlo, dhi = int(h["digital_min"]), int(h["digital_max"])
        assert np.isfinite([lo, hi]).all() and hi > lo and -32768 <= dlo < dhi <= 32767
        gain = (hi - lo) / (dhi - dlo)
        v = digital[:, offset : offset + counts[i]].reshape(-1).astype(np.float64)
        signals[channel] = (v * gain + (lo - gain * dlo)).astype(np.float32)
        offset += counts[i]
        headers.append(h)
    intervals = []
    for rec in range(records):
        begin = header_size + 2 * (rec * record_width + offset)
        block = data[begin : begin + 2 * counts[-1]]
        clocks = []
        for tal in block.split(b"\x00"):
            if not tal:
                continue
            pieces = tal.split(b"\x14")
            assert pieces[-1] == b""
            times = pieces[0].decode("ascii").split("\x15")
            texts = [v.decode("utf-8") for v in pieces[1:-1] if v]
            onset = Fraction(times[0])
            if not texts:
                assert len(times) == 1
                clocks.append(onset)
            else:
                assert len(times) == 2
                length = Fraction(times[1])
                assert length > 0
                for text in texts:
                    assert text in ["T0", "T1", "T2"]
                    intervals.append((onset, length, text))
        assert clocks == [rec * duration], (path.name, rec, clocks)
    assert intervals and all(
        a[0] <= b[0] for a, b in zip(intervals, intervals[1:], strict=False)
    )
    return signals, headers, fs, step_ns.numerator, intervals


def read_events(path):
    """Retain sample-zero NOTE annotations that wfdb.rdann discards as metadata.

    Use WFDB's binary byte-pair decoder before its definition filtering. This
    preserves genuine T0 at sample zero while dropping only the declared time
    resolution and the null annotation, based on their explicit contents.
    """
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8).reshape(-1, 2)
    samples, codes, _, _, _, notes = proc_ann_bytes(data, None)
    fs, events = None, []
    for sample, code, note in zip(samples, codes, notes, strict=True):
        if code == 0:
            assert not note
            continue
        assert code == 22
        if note.startswith("## time resolution: "):
            assert sample == 0 and fs is None
            fs = Fraction(note.split(": ", 1)[1])
            continue
        match = re.fullmatch(r"(T[012]) duration: ([0-9.]+)", note)
        assert match, (path.name, sample, note)
        events.append((int(sample), Fraction(match[2]), match[1]))
    assert fs is not None
    return fs, events


def context(run):
    if run <= 2:
        return (
            "baseline",
            "eyes_open" if run == 1 else "eyes_closed",
            {
                0: "source_T0_rest",
                1: "unresolved_source_T1_in_baseline",
                2: "unresolved_source_T2_in_baseline",
            },
        )
    task = (run - 3) % 4
    mode = "execution" if task % 2 == 0 else "imagery"
    targets = ["left_fist", "right_fist"] if task < 2 else ["both_fists", "both_feet"]
    return (
        f"{mode}_{'unilateral_fists' if task < 2 else 'bilateral_fists_feet'}",
        None,
        {0: "inter_task_rest", 1: f"{mode}_{targets[0]}", 2: f"{mode}_{targets[1]}"},
    )


def make_spec():
    return DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=None,
        time_column=("time_ns", pa.int64()),
        label_columns={"label_source": pa.int8()},
        meta_columns={
            "subject_id": pa.string(),
            "run": pa.int8(),
            "paradigm": pa.string(),
            "baseline_context": pa.string(),
            "baseline_annotation_anomaly": pa.bool_(),
            "source_sampling_rate_hz": pa.float64(),
            "time_step_ns": pa.int64(),
            "source_edf": pa.string(),
            "state_meanings_json": pa.string(),
            "native_channel_headers_json": pa.string(),
            "edf_annotation_count": pa.int32(),
            "event_annotation_count": pa.int32(),
            "event_exact_match": pa.bool_(),
            "event_missing_edf_intervals": pa.int32(),
            "event_extra_intervals": pa.int32(),
            "annotation_conflict_samples": pa.int32(),
        },
    )


def describe_native_rates(root, rates):
    """Describe mixed regular native rates explicitly in the generated card.

    The shared card calls a missing global rate irregular. Here the global rate
    is absent because it differs between runs, each of which is uniformly timed.
    Update only the card digest after this dataset-specific wording adjustment.
    """
    card = root / "README.md"
    description = "; ".join(
        f"{float(rate):g} Hz ({count} runs)"
        for rate, count in sorted(rates.items(), key=lambda item: float(item[0]))
    )
    text = card.read_text()
    text = text.replace(
        "| Sampling | irregular or unspecified |",
        f"| Sampling | Native per series: {description} |",
    )
    text = text.replace("| irregular |", "| native per series (see index) |")
    card.write_text(text)
    sums = root / "SHA256SUMS"
    lines = []
    for line in sums.read_text().splitlines():
        digest, relative = line.split("  ", 1)
        if relative == "README.md":
            digest = sha256(card)
        lines.append(f"{digest}  {relative}")
    sums.write_text("\n".join(lines) + "\n")


def reserve_projection(
    root, writer, total_samples_upper, processed_samples, raw_remaining
):
    """Project remaining disk use from flushed samples and measured compression.

    Keep the worse of the isolated-run pilot and actual compression, with 25%
    margin. Pending rows remain in the remaining sample count. Reserve another
    64 MiB for index/card/Croissant/auxiliary/footer writes. Source cache bytes
    still to download are included separately; existing pilots are already in
    current filesystem usage and never counted as free storage.
    """
    part = writer.parts["default"]
    pending = sum(row["length"] for row in part.buf)
    flushed = processed_samples - pending
    disk_bytes = sum((root / name).stat().st_size for name in part.files)
    measured_ratio = disk_bytes / flushed if flushed else 0
    ratio = max(83.58856707317074, measured_ratio) * 1.25
    remaining = (
        max(0, total_samples_upper - flushed) * ratio + raw_remaining + 64 * 2**20
    )
    free = shutil.disk_usage(root).free
    projection = {
        "processed_samples": processed_samples,
        "flushed_samples": flushed,
        "written_signal_bytes": disk_bytes,
        "measured_bytes_per_sample": measured_ratio,
        "projected_remaining_bytes": remaining,
        "free_bytes": free,
        "projected_peak_free_bytes": free - remaining,
    }
    if free - remaining < 18 * 2**30:
        raise RuntimeError(
            f"Projected peak free {(free - remaining) / 2**30:.3f} GiB is below 18 GiB reserve"
        )
    return projection


def main():
    args = parse_args(ID)
    pins = json.loads(PIN_FILE.read_text())
    raw_root = args.raw_dir / ID
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_remaining = sum(
        p["bytes"] for name, p in pins.items() if not (raw_root / name).exists()
    )

    def source(name):
        nonlocal raw_remaining
        p = pins[name]
        missing = not (raw_root / name).exists()
        if (
            missing
            and shutil.disk_usage(raw_root).free - p["bytes"] < 18 * 2**30 + 64 * 2**20
        ):
            raise RuntimeError("Source download would breach 18-GiB reserve")
        path = fetch(p["url"], name, p["sha256"], args.raw_dir, ID)
        if missing:
            raw_remaining -= p["bytes"]
        return path

    records = source("RECORDS").read_text().splitlines()
    source("SHA256SUMS.txt")
    assert records == [
        f"S{s:03}/S{s:03}R{r:02}.edf" for s in range(1, 110) for r in range(1, 15)
    ]
    spec = make_spec()
    interval_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("source_annotation_index", pa.int32()),
            ("onset_s", pa.float64()),
            ("duration_s", pa.float64()),
            ("source_code", pa.string()),
            ("begin_sample_clipped", pa.int32()),
            ("end_sample_clipped", pa.int32()),
        ]
    )
    event_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("source_annotation_index", pa.int32()),
            ("sample_index", pa.int32()),
            ("duration_s", pa.float64()),
            ("source_code", pa.string()),
            ("exact_edf_interval_match", pa.bool_()),
        ]
    )
    stats = Statistics()
    comparison, rates, baseline_stats = [], {}, {"series": 0, "missing_samples": 0}
    baseline_stats["non_rest_source_codes_series"] = []
    total_intervals, total_events = 0, 0
    state_recurrence = []
    total_samples_upper = sum(pins[name]["bytes"] for name in records) / 128
    processed_samples, storage_projections = 0, []
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "edf_intervals.parquet", interval_schema, compression="zstd"
        ) as iw,
        pq.ParquetWriter(
            args.out_dir / "wfdb_events.parquet", event_schema, compression="zstd"
        ) as ew,
    ):
        storage_projections.append(
            reserve_projection(
                args.out_dir, writer, total_samples_upper, 0, raw_remaining
            )
        )
        for i, name in enumerate(records):
            if shutil.disk_usage(args.out_dir).free < 18 * 2**30 + 64 * 2**20:
                raise RuntimeError(
                    "Disk reserve would fall below 18 GiB after buffered writes"
                )
            path = source(name)
            signals, headers, fs, step, intervals = read_edf(path)
            event_fs, events = read_events(source(name + ".event"))
            assert event_fs == fs
            n = len(signals[CHANNELS[0]])
            sid = path.stem
            subject, run = sid[:4], int(sid[-2:])
            paradigm, baseline, meanings = context(run)
            labels = np.full(n, -1, dtype=np.int8)
            conflicts = np.zeros(n, dtype=bool)
            rows = []
            edf_keys = Counter(
                (onset * fs, duration, text) for onset, duration, text in intervals
            )
            event_keys = Counter(
                (Fraction(sample), duration, text) for sample, duration, text in events
            )
            for j, (onset, duration, text) in enumerate(intervals):
                begin, end = (
                    max(0, min(n, ceil(onset * fs))),
                    max(0, min(n, ceil((onset + duration) * fs))),
                )
                state = int(text[1])
                conflicts[begin:end] |= (labels[begin:end] != -1) & (
                    labels[begin:end] != state
                )
                labels[begin:end] = state
                rows.append(
                    {
                        "series_id": sid,
                        "source_annotation_index": j,
                        "onset_s": float(onset),
                        "duration_s": float(duration),
                        "source_code": text,
                        "begin_sample_clipped": begin,
                        "end_sample_clipped": end,
                    }
                )
            labels[conflicts] = -1
            if baseline is not None:
                if any(text != "T0" for _, _, text in intervals):
                    baseline_stats["non_rest_source_codes_series"].append(sid)
                baseline_stats["series"] += 1
                baseline_stats["missing_samples"] += int(np.count_nonzero(labels == -1))
            iw.write_table(pa.Table.from_pylist(rows, schema=interval_schema))
            if events:
                ew.write_table(
                    pa.Table.from_pylist(
                        [
                            {
                                "series_id": sid,
                                "source_annotation_index": j,
                                "sample_index": sample,
                                "duration_s": float(duration),
                                "source_code": text,
                                "exact_edf_interval_match": (
                                    Fraction(sample),
                                    duration,
                                    text,
                                )
                                in edf_keys,
                            }
                            for j, (sample, duration, text) in enumerate(events)
                        ],
                        schema=event_schema,
                    )
                )
            missing, extra = (
                sum((edf_keys - event_keys).values()),
                sum((event_keys - edf_keys).values()),
            )
            comparison.append(
                {
                    "series_id": sid,
                    "edf_intervals": len(intervals),
                    "event_intervals": len(events),
                    "missing_edf_intervals": missing,
                    "extra_event_intervals": extra,
                    "exact_match": missing == extra == 0,
                }
            )
            total_intervals += len(intervals)
            total_events += len(events)
            rates[str(float(fs))] = rates.get(str(float(fs)), 0) + 1
            writer.add_series(
                sid,
                signals,
                labels={"label_source": labels},
                time=np.arange(n, dtype=np.int64) * step,
                meta={
                    "subject_id": subject,
                    "run": run,
                    "paradigm": paradigm,
                    "baseline_context": baseline,
                    "baseline_annotation_anomaly": baseline is not None
                    and any(text != "T0" for _, _, text in intervals),
                    "source_sampling_rate_hz": float(fs),
                    "time_step_ns": step,
                    "source_edf": name,
                    "state_meanings_json": json.dumps(meanings),
                    "native_channel_headers_json": json.dumps(headers),
                    "edf_annotation_count": len(intervals),
                    "event_annotation_count": len(events),
                    "event_exact_match": missing == extra == 0,
                    "event_missing_edf_intervals": missing,
                    "event_extra_intervals": extra,
                    "annotation_conflict_samples": int(conflicts.sum()),
                },
            )
            stats.add(sid, {"label_source": labels})
            segment_states = runs(labels)[0]
            state_counts = {
                str(state): int(np.count_nonzero(segment_states == state))
                for state in STATES
            }
            state_recurrence.append(
                {
                    "series_id": sid,
                    "state_segment_counts": state_counts,
                    "substantive_recurrence": any(
                        state_counts[str(state)] > 1 for state in [1, 2]
                    ),
                }
            )
            processed_samples += n
            projection = reserve_projection(
                args.out_dir,
                writer,
                total_samples_upper,
                processed_samples,
                raw_remaining,
            )
            if (i + 1) % 70 == 0 or i + 1 == len(records):
                storage_projections.append(projection)
                print(
                    f"[{i + 1}/{len(records)}] {sid}; native rates {rates}; free {projection['free_bytes'] / 2**30:.2f} GiB; projected peak free {projection['projected_peak_free_bytes'] / 2**30:.2f} GiB",
                    flush=True,
                )
    finish(
        args,
        spec,
        writer,
        stats,
        title="EEGMMIDB: all 109 subjects, 1,526 native 64-channel runs",
        source=SOURCE,
        sha256=sha256(PIN_FILE),
        license_spdx="ODC-By-1.0",
        license_url="https://opendatacommons.org/licenses/by/1-0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-19",
        description="All 1,526 native EEG runs from 109 participants, including both provider-designated baseline runs per subject. The single default config preserves all 64 calibrated EEG channels. A second light view is omitted to avoid duplicate physical storage and preserve the local 18-GiB disk reserve; this is a storage exception, with no source channels removed. Native rates are preserved per series, including 128 Hz where actually declared, rather than forcing the nominal 160 Hz. Exact elapsed nanoseconds provide the native time grid.",
        collection="BCI2000 64-electrode 10-10 EEG acquired by W. A. Sarnacki at the Wadsworth Center BCI R&D Program. Each of 109 volunteers completed 14 runs: R01 eyes-open resting baseline, R02 eyes-closed resting baseline, then three repetitions of four visually cued motor execution/imagery paradigms. Preserve all original samples and all 64 EEG channels in the default config. Evaluate by participant; keep repeat runs from one participant together.",
        annotation="Canonical ground truth is the literal EDF+ annotation channel, with explicit onset and duration. T0 is rest, an ordinary scored state. T1/T2 meanings depend on the run: R03/07/11 execution left/right fist; R04/08/12 imagery left/right fist; R05/09/13 execution both fists/both feet; R06/10/14 imagery both fists/both feet. The primary archived protocol gives this mapping. Keep raw codes 0/1/2; run paradigm and state_meanings_json prevent pooling incompatible target meanings. R01/R02 retain their literal source codes, with eyes-open/closed protocol context in metadata. Normally they contain only T0, but S089R01/R02 contain T0 for 0.1 s followed by T1 for 60.05 s. Preserve this provider annotation anomaly, flag it and leave the T1 semantic meaning unresolved; infer no baseline task identity. Fill half-open annotation intervals on the native sample grid using exact rational source decimal times. Samples outside all explicit durations, including EDF padding tails, remain -1; conflicting intervals remain -1. Preserve every original EDF interval. Independently preserve the source .event conversion and measure exact onset/code/duration matches; this is a conversion comparison, not agreement between annotators. The WFDB conversion may omit source intervals, so it never replaces EDF ground truth.",
        conversion="All 1,526 EDF and 1,526 .event files SHA256/size checked against the primary PhysioNet manifest and official S3 inventory; RECORDS and SHA256SUMS also pinned. Direct little-endian EDF int16 decoding validates exact file length, every channel header/calibration and the timekeeping TAL of every data record. Apply each native physical calibration, cast once to float32 uV. Strip only channel-name padding dots for semantic names; retain full source channel/calibration headers in index. Explicit elapsed nanoseconds use the native rate per run; dataset/config rate is null because rates differ between runs. No resampling, filtering, normalization, epoch cropping, source run rejection or joining across runs. WFDB byte-pair decoding preserves genuine NOTE annotations at sample zero, unlike rdann's definition filtering. Export no patient/recording text, absolute dates or demographics.",
        limitations="Protocol cues mark intended behavior rather than independently verified movement or neural state. Published decimal cue times can fall between native samples and create tiny gaps or overlaps; conflicting sample labels remain unscored. T1/T2 are run-dependent and must not be treated as a universal shared task identity. Rest recurrence and task-target recurrence are measured within each run; ordinary baselines have no substantive state transitions. S089R01/R02 have unexpected source T1 annotations despite their baseline protocol context; they retain raw codes with unresolved task semantics, and must not be interpreted as labelled motor tasks. Real 128-Hz runs, short/long runs, EDF padding and source conversion omissions are preserved and reported, without rejecting participants or runs. The sole default config retains every 64-channel signal, with no reduced-channel view or duplicate physical copy. EDF+ is canonical because source .event conversions can drop annotations despite the primary page's equivalence claim. No independent annotation tracks exist. Pseudonymous EEG can be sensitive; no identity or clinical interpretation is attempted.",
        biases="Volunteer cohort, one site and cued laboratory motor/imagery tasks. Repetitions share participants, electrode placement and session context. Intended motor imagery may not be confirmed physiologically; do not equate protocol class with successful imagery. Randomly splitting windows or runs across participants would leak participant/session information.",
        personal="Pseudonymous subject IDs and EEG recordings retained. Patient/recording header text, absolute dates and demographic information excluded; no identifying linkage attempted.",
        citation="Schalk, G. (2009). EEG Motor Movement/Imagery Dataset (v1.0.0). PhysioNet. doi:10.13026/C28G6P. Schalk et al. (2004). BCI2000: A General-Purpose Brain-Computer Interface System. IEEE TBME 51(6):1034–1043. Pollard et al. (2026). PhysioNet as a global platform for biomedical research. Nature Health 1:792–795. doi:10.1038/s44360-026-00096-z.",
        creators=[
            "Gerwin Schalk",
            "W. A. Sarnacki",
            "Aditya Joshi",
            "D. J. McFarland",
            "J. R. Wolpaw",
        ],
        date_published="2009-09-09",
        null_states={"label_source": [0]},
        info={
            "label_origin": "protocol",
            "state_names": {"label_source": STATES},
            "label_descriptions": {
                "label_source": "Literal EDF+ T0/T1/T2; T1/T2 semantic meaning depends on run metadata."
            },
            "default_label": "label_source",
            "reference_doi": "https://doi.org/10.13026/C28G6P",
            "time_description": "Elapsed nanoseconds on native regular grid; source_sampling_rate_hz and time_step_ns in index per series; no absolute time.",
            "source_files": pins,
            "source_protocol": PROTOCOL,
            "native_rate_series_counts": rates,
            "source_annotation_comparison": comparison,
            "baseline_statistics": baseline_stats,
            "state_recurrence": state_recurrence,
            "storage_sizing": {
                "single_native_64_channel_config": True,
                "pilot_runs": 14,
                "pilot_actual_bytes_per_sample": 65.7446277147389,
                "pilot_max_isolated_bytes_per_sample": 83.58856707317074,
                "projection_margin": 0.25,
                "metadata_buffer_bytes": 64 * 2**20,
                "reserve_bytes": 18 * 2**30,
                "rolling_projections": storage_projections,
            },
            "series_with_substantive_recurrence": sum(
                row["substantive_recurrence"] for row in state_recurrence
            ),
            "edf_interval_count": total_intervals,
            "wfdb_event_count": total_events,
            "auxiliary": {
                "edf_intervals.parquet": "All original EDF+ onset/duration/code intervals and their clipped native-sample spans; canonical source ground truth.",
                "wfdb_events.parquet": "Literal source WFDB conversion events, preserving sample-zero NOTE entries and source duration; exact EDF match flag. Not a second annotator or replacement ground truth.",
            },
        },
    )

    describe_native_rates(args.out_dir, rates)


if __name__ == "__main__":
    main()
