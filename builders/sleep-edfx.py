"""Preserve complete Sleep-EDFx recordings and all native-rate PSG channels."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import pyedflib  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "sleep-edfx"
SOURCE = "https://physionet.org/content/sleep-edfx/1.0.0/"
BASE = "https://physionet-open.s3.amazonaws.com/sleep-edfx/1.0.0/"
PIN_FILE = Path(__file__).parent / "checksums" / f"{ID}.json"
PINS = json.loads(PIN_FILE.read_text())
HIGH = {
    "EEG Fpz-Cz": "eeg_fpz_cz",
    "EEG Pz-Oz": "eeg_pz_oz",
    "EOG horizontal": "eog_horizontal",
    "EMG submental": "emg_submental_100hz",
}
DEFAULT = list(HIGH.values())[:3]
STATES = {
    0: "Wake",
    1: "R&K_stage_1",
    2: "R&K_stage_2",
    3: "R&K_stage_3",
    4: "R&K_stage_4",
    5: "REM",
    6: "Movement_time",
}
LABELS = {
    "Sleep stage W": 0,
    **{f"Sleep stage {i}": i for i in range(1, 5)},
    "Sleep stage R": 5,
    "Movement time": 6,
    "Sleep stage ?": -1,
}


def read_hypnogram(path: Path):
    """Decode EDF+ annotation TALs using the fixed EDF header clock.

    Seven ST hypnograms have stale EDF+ Recordingfield dates one day before
    their fixed startdates. Preserve each discrepancy and
    use the fixed startdate/time fields consistently for signal alignment.
    No patient field is decoded or copied.
    """
    data = path.read_bytes()
    assert data[:8] == b"0       "
    assert int(data[252:256]) == 1
    assert int(data[184:192]) == 512
    assert data[256:272].strip() == b"EDF Annotations"
    assert int(data[236:244]) == 1
    assert len(data) == 512 + 2 * int(data[472:480])
    day, month, year = map(int, data[168:176].decode("ascii").split("."))
    year += 1900 if year >= 85 else 2000
    hour, minute, second = map(int, data[176:184].decode("ascii").split("."))
    start = datetime(year, month, day, hour, minute, second)
    recording_date = data[88:168].decode("ascii").split()[1]
    date_conflict = recording_date != start.strftime("%d-%b-%Y").upper()
    onsets, durations, descriptions = [], [], []
    for tal in data[512:].split(b"\x00"):
        if not tal:
            continue
        fields = tal.split(b"\x14")
        assert fields[-1] == b""
        texts = [f.decode("utf-8") for f in fields[1:-1] if f]
        if not texts:
            continue  # Mandatory timekeeping TAL has no description.
        onset, duration = fields[0].split(b"\x15")
        for text in texts:
            onsets.append(float(onset))
            durations.append(float(duration))
            descriptions.append(text)
    assert descriptions
    return start, (onsets, durations, descriptions), recording_date, date_conflict


def main() -> None:
    args = parse_args(ID)
    records = sorted(name for name in PINS if name.endswith("-PSG.edf"))
    assert len(records) == 197
    hypnograms = {
        Path(name).name[:6]: name for name in PINS if name.endswith("-Hypnogram.edf")
    }
    assert len(hypnograms) == 197
    assert set(hypnograms) == {Path(name).name[:6] for name in records}
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=list(HIGH.values()),
        configs={"default": DEFAULT, "full": list(HIGH.values())},
        sampling_rate_hz=100,
        time_column=("sample_index", pa.int32()),
        label_columns={"label_sleep_stage": pa.int8()},
        meta_columns={
            "cohort": pa.string(),
            "subject_id": pa.string(),
            "night_id": pa.string(),
            "source_psg": pa.string(),
            "source_hypnogram": pa.string(),
            "scorer_code": pa.string(),
            "source_start_datetime": pa.string(),
            "hypnogram_start_datetime": pa.string(),
            "hypnogram_recordingfield_date": pa.string(),
            "hypnogram_header_date_conflict": pa.bool_(),
            "native_100hz_channels": pa.list_(pa.string()),
            "native_channel_headers_json": pa.string(),
        },
    )
    slow_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("native_channel", pa.string()),
            ("sampling_rate_hz", pa.float64()),
            ("unit", pa.string()),
            ("n_samples", pa.int64()),
            ("values", pa.list_(pa.float32())),
        ]
    )
    interval_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("source_annotation_index", pa.int32()),
            ("onset_s", pa.float64()),
            ("duration_s", pa.float64()),
            ("description", pa.string()),
            ("hypnogram_start_offset_s", pa.float64()),
            ("begin_sample_clipped", pa.int64()),
            ("end_sample_clipped", pa.int64()),
            ("state_code", pa.int8()),
        ]
    )
    stats = Statistics()
    slow_counts = {}
    channels_seen = {}
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "native_slow_signals.parquet",
            slow_schema,
            compression="zstd",
        ) as slow_writer,
        pq.ParquetWriter(
            args.out_dir / "source_intervals.parquet",
            interval_schema,
            compression="zstd",
        ) as interval_writer,
    ):
        for index, name in enumerate(records, 1):
            if shutil.disk_usage(args.out_dir).free < 22 * 2**30:
                raise RuntimeError(
                    "Disk reserve below 22 GiB; stop before next EDF pair"
                )
            stem = Path(name).stem.removesuffix("-PSG")
            hyp_name = hypnograms[stem[:6]]
            raw = fetch(BASE + name, name, PINS[name], args.raw_dir, ID)
            hyp_file = fetch(
                BASE + hyp_name, hyp_name, PINS[hyp_name], args.raw_dir, ID
            )
            cohort = "SC" if stem.startswith("SC") else "ST"
            hyp_start, annotations, recording_date, date_conflict = read_hypnogram(
                hyp_file
            )
            with pyedflib.EdfReader(str(raw)) as edf:
                start = edf.getStartdatetime()
                offset = (hyp_start - start).total_seconds()
                native_labels = edf.getSignalLabels()
                rates = edf.getSampleFrequencies()
                nsamples = edf.getNSamples()
                n = int(nsamples[native_labels.index("EEG Fpz-Cz")])
                assert abs(edf.getFileDuration() * 100 - n) < 1e-6
                signal = {
                    c: np.full(n, np.nan, dtype=np.float32) for c in spec.channels
                }
                high_present = []
                for channel, (label, rate) in enumerate(
                    zip(native_labels, rates, strict=True)
                ):
                    channels_seen.setdefault(label, set()).add(float(rate))
                    values = edf.readSignal(channel).astype(np.float32)
                    assert len(values) == int(nsamples[channel])
                    if rate == 100:
                        assert label in HIGH and len(values) == n
                        signal[HIGH[label]] = values
                        high_present.append(label)
                    else:
                        assert (
                            rate in [1, 10] and abs(len(values) / rate - n / 100) < 1e-6
                        )
                        slow_counts[f"{label}@{rate:g}Hz"] = slow_counts.get(
                            f"{label}@{rate:g}Hz", 0
                        ) + len(values)
                        slow_writer.write_table(
                            pa.Table.from_pylist(
                                [
                                    {
                                        "series_id": stem,
                                        "native_channel": label,
                                        "sampling_rate_hz": float(rate),
                                        "unit": edf.getPhysicalDimension(channel),
                                        "n_samples": len(values),
                                        "values": values,
                                    }
                                ],
                                schema=slow_schema,
                            )
                        )
                assert high_present[:3] == list(HIGH)[:3]
                y = np.full(n, -1, dtype=np.int8)
                covered = np.zeros(n, dtype=bool)
                onsets, durations, texts = annotations
                intervals = []
                for j, (onset, duration, text) in enumerate(
                    zip(onsets, durations, texts, strict=True)
                ):
                    assert text in LABELS, (stem, text)
                    assert duration >= 0
                    first = (offset + float(onset)) * 100
                    last = (offset + float(onset) + float(duration)) * 100
                    assert (
                        abs(first - round(first)) < 1e-6
                        and abs(last - round(last)) < 1e-6
                    )
                    a, b = (
                        max(0, min(n, int(round(first)))),
                        max(0, min(n, int(round(last)))),
                    )
                    assert not covered[a:b].any(), (stem, j)
                    y[a:b] = LABELS[text]
                    covered[a:b] = True
                    intervals.append(
                        {
                            "series_id": stem,
                            "source_annotation_index": j,
                            "onset_s": float(onset),
                            "duration_s": float(duration),
                            "description": text,
                            "hypnogram_start_offset_s": float(offset),
                            "begin_sample_clipped": a,
                            "end_sample_clipped": b,
                            "state_code": LABELS[text],
                        }
                    )
                interval_writer.write_table(
                    pa.Table.from_pylist(intervals, schema=interval_schema)
                )
                labels = {"label_sleep_stage": y}
                writer.add_series(
                    stem,
                    signal,
                    labels=labels,
                    time=np.arange(n, dtype=np.int32),
                    annotators=[Path(hyp_name).name[7]],
                    meta={
                        "cohort": cohort,
                        "subject_id": f"{cohort}-{stem[3:5]}",
                        "night_id": stem[5],
                        "source_psg": name,
                        "source_hypnogram": hyp_name,
                        "scorer_code": Path(hyp_name).name[7],
                        "source_start_datetime": start.isoformat(),
                        "hypnogram_start_datetime": hyp_start.isoformat(),
                        "hypnogram_recordingfield_date": recording_date,
                        "hypnogram_header_date_conflict": date_conflict,
                        "native_100hz_channels": high_present,
                        "native_channel_headers_json": json.dumps(
                            edf.getSignalHeaders()
                        ),
                    },
                )
                stats.add(stem, labels)
            print(
                f"[{index}/197] {stem}: {n} samples; source labels retained", flush=True
            )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Sleep-EDF Expanded: all 197 complete native PSG recordings",
        source=SOURCE,
        sha256=hashlib.sha256(PIN_FILE.read_bytes()).hexdigest(),
        license_spdx="ODC-By-1.0",
        license_url="https://opendatacommons.org/licenses/by/1-0/",
        license_evidence=SOURCE,
        description="All 153 Sleep Cassette and 44 Sleep Telemetry recordings, without sleep-window cropping. Default includes both 100-Hz EEG derivations and EOG; full adds native 100-Hz EMG where recorded. Every slower channel remains at its native 1/10-Hz rate in auxiliary. Native seven R&K sleep/movement states retained, unknown/unscored samples -1.",
        collection="Whole-night home Sleep Cassette recordings (1987–1991) and hospital Sleep Telemetry recordings (1994, placebo/temazepam crossover). Provider-calibrated EEG Fpz-Cz/Pz-Oz, horizontal EOG, submental EMG, respiration, temperature and marker signals retained at their actual EDF-header frequencies. The native ST marker is 10 Hz, contrary to the primary summary page's 1-Hz statement; all 197 headers were audited. No synthetic records.",
        annotation="Manual technician hypnograms follow Rechtschaffen & Kales staging. Keep Wake, stages 1/2/3/4, REM and Movement time as seven scored states; movement is annotated behavior, not absent truth. Only Sleep stage ? and intervals without any annotation remain -1. No N3/N4 merging, wake trimming or dense interpolation across unknown intervals. Technician code from the eighth filename character retained, but each recording has one released annotation track, so no independent per-recording agreement or consensus is available. Native EDF+ onsets/durations and original stage descriptions remain auxiliary, including portions beyond the recorded signal.",
        conversion="Decode PSG EDF with pinned pyedflib 0.1.42 and hypnogram EDF+ time-annotation lists directly; calibrated signal values cast to float32 with source calibration/channel headers retained. Match PSG/hypnogram by six-character recording prefix, align annotation seconds using the fixed EDF startdate/time fields, then expand half-open intervals onto the 100-Hz grid only within real PSG samples. Original annotation bounds preserved before clipping. Keep complete native day/night coverage and sample index. Default contains all common 100-Hz EEG/EOG channels; full additionally includes ST 100-Hz EMG, padded NaN where SC has only native 1-Hz EMG. Every 1-Hz SC channel and 10-Hz ST marker stored unresampled auxiliary with unit/rate/count. No filtering, scaling beyond EDF calibration, resampling, demographic extraction or record concatenation. Group evaluation by cohort/subject, not individual nights. Source files use official public S3 transport and every primary PhysioNet SHA256 is verified.",
        limitations="Large daytime wake portions in complete SC records and medication effects in ST can dominate comparisons; no artificial sleep-only windows are supplied. Historical R&K stages differ from modern AASM; stages 3/4 are deliberately separate. Unknown lead-in, gaps and source hypnogram portions beyond PSG coverage are not repaired. Seven ST hypnograms (ST7021JM, ST7071JA, ST7092JE, ST7131JR, ST7132JR, ST7141JE, ST7142JE) have stale EDF+ Recordingfield dates one day before their fixed startdates; alignment uses the fixed startdate/time and both clocks/conflict flags are retained. All 197 PSG/hypnogram fixed-clock offsets are zero. Auxiliary marker streams can encode device events; excluded from default/full physiological predictors. Source clock dates/times are retained as released, with no claim of original calendar accuracy. Padded missing dimensions are distinct from native missing signals.",
        biases="Age-selected historical cohorts, home versus hospital equipment, placebo/temazepam protocol and technician conventions limit transfer. Evaluation should report cohort, participant grouping and class imbalance.",
        personal="Human health recordings with pseudonymous recording/subject IDs and released recording start times. EDF patient text and subject age/sex spreadsheets are excluded from converted output; no demographics extracted. Do not attempt re-identification or use benchmark performance for diagnosis.",
        citation="Kemp, Zwinderman, Tuk, Kamphuisen & Oberyé (2000). Analysis of a sleep-dependent neuronal feedback loop: the slow-wave microcontinuity of the EEG. IEEE TBME 47(9):1185–1194. Sleep-EDF Expanded, doi:10.13026/C2X676. Pollard et al. (2026). PhysioNet as a global platform for biomedical research. Nature Health 1:792–795. doi:10.1038/s44360-026-00096-z.",
        creators=["Bob Kemp"],
        date_published="2013-10-24",
        null_states={"label_sleep_stage": [6]},
        info={
            "state_names": {"label_sleep_stage": STATES},
            "default_label": "label_sleep_stage",
            "reference_doi": "https://doi.org/10.13026/C2X676",
            "source_files_sha256": PINS,
            "source_transport": BASE,
            "cohort_recordings": {"SC": 153, "ST": 44},
            "native_channel_rates": {k: sorted(v) for k, v in channels_seen.items()},
            "native_slow_sample_counts": slow_counts,
            "source_expansion": "197-record expansion documented in March 2018; PhysioNet version page retains 1.0.0/2013 publication date",
            "auxiliary": {
                "native_slow_signals.parquet": "All native 1-Hz SC and 10-Hz ST streams, calibrated values, channel name/unit/rate/count; align sample k at k/rate seconds from the PSG start.",
                "source_intervals.parquet": "All original EDF+ annotations, unchanged onset/duration/description, header-clock offset and explicitly clipped 100-Hz evaluation bounds.",
            },
        },
    )


if __name__ == "__main__":
    main()
