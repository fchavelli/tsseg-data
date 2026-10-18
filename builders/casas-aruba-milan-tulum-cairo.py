"""Build five CASAS event logs with reversible sets of simultaneous activities."""

from __future__ import annotations

import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "casas-aruba-milan-tulum-cairo"
SOURCE = "https://zenodo.org/records/17180309"
URL = "https://zenodo.org/api/records/17180309/files/new_labeled_data.zip/content"
SHA256 = "c7d97c44b2c121739f318fb37a8714e100eed88b7eab9dad753113478fd36296"
BINARY = {"ON": 1.0, "OFF": 0.0, "OPEN": 1.0, "CLOSE": 0.0, "CLOSED": 0.0}
FILES = ["aruba.txt", "cairo.txt", "milan.txt", "tulum1.txt", "tulum2.txt"]


def inspect(archive):
    """Pair exact source markers in row order, retaining every malformed marker."""
    channels = set()
    source = {}
    for name in FILES:
        markers, intervals, opened, uncertain, message_errors = [], [], {}, {}, []
        sensors = set()
        with archive.open(name) as stream:
            for i, raw in enumerate(stream):
                fields = raw.decode("utf8").split()
                assert len(fields) >= 4, (name, i, fields)
                channels.add(fields[2])
                sensors.add(fields[2])
                if fields[3] not in BINARY:
                    try:
                        numeric = float(fields[3])
                        assert np.isfinite(numeric)
                    except (ValueError, AssertionError):
                        message_errors.append(
                            {
                                "series_id": Path(name).stem,
                                "source_row": i,
                                "sensor": fields[2],
                                "source_message": fields[3],
                            }
                        )
                if len(fields) == 4:
                    continue
                activity, *action = fields[4:]
                text = " ".join(action)
                markers.append(
                    {
                        "series_id": Path(name).stem,
                        "source_row": i,
                        "activity": activity,
                        "action_source": text,
                    }
                )
                if action not in [["begin"], ["end"]]:
                    uncertain[activity] = i
                    continue
                if action == ["begin"]:
                    if activity in opened:
                        start, _ = opened[activity]
                        opened[activity] = (start, "repeated_begin")
                    else:
                        opened[activity] = (i, "paired")
                else:
                    if activity in opened:
                        start, status = opened.pop(activity)
                    elif activity in uncertain:
                        start, status = uncertain.pop(activity), "malformed_marker"
                    else:
                        start, status = i, "unmatched_end"
                    intervals.append(
                        {
                            "series_id": Path(name).stem,
                            "activity": activity,
                            "start_source_row": start,
                            "end_source_row_inclusive": i,
                            "status": status,
                        }
                    )
        n = i + 1
        for activity, (start, _) in opened.items():
            intervals.append(
                {
                    "series_id": Path(name).stem,
                    "activity": activity,
                    "start_source_row": start,
                    "end_source_row_inclusive": n - 1,
                    "status": "unmatched_begin",
                }
            )
        for activity, start in uncertain.items():
            intervals.append(
                {
                    "series_id": Path(name).stem,
                    "activity": activity,
                    "start_source_row": start,
                    "end_source_row_inclusive": n - 1,
                    "status": "malformed_unclosed",
                }
            )
        source[name] = (n, sensors, markers, intervals, message_errors)
    return sorted(channels), source


def dense_sets(n, intervals, codes):
    """Inclusive source marker rows; ambiguous source intervals are unscored."""
    events = defaultdict(list)
    mask = np.zeros(n + 1, dtype=np.int32)
    for row in intervals:
        start, end = row["start_source_row"], row["end_source_row_inclusive"] + 1
        assert 0 <= start < end <= n
        if row["status"] == "paired":
            events[start].append((row["activity"], 1))
            events[end].append((row["activity"], -1))
        else:
            mask[start] += 1
            mask[end] -= 1
    y = np.full(n, -1, dtype=np.int16)
    active = Counter()
    points = sorted(set(events) | {0, n})
    for start, end in zip(points[:-1], points[1:], strict=True):
        for activity, delta in events[start]:
            active[activity] += delta
        activities = tuple(sorted(k for k, v in active.items() if v > 0))
        if activities:
            if activities not in codes:
                codes[activities] = len(codes)
            y[start:end] = codes[activities]
    ambiguous = np.cumsum(mask[:-1]) > 0
    y[ambiguous] = -1
    return y, int(ambiguous.sum())


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    stats, codes, all_markers, all_intervals, all_message_errors = (
        Statistics(),
        {},
        [],
        [],
        [],
    )
    with zipfile.ZipFile(raw) as archive:
        assert set(archive.namelist()) == set(FILES)
        sensors, sources = inspect(archive)
        channels = [f"sensor_{s}" for s in sensors]
        spec = DatasetSpec(
            id=ID,
            task="sd",
            channels=channels,
            configs={"default": channels},
            time_column=("t_timestamp", pa.timestamp("ns")),
            label_columns={"label_activity_set": pa.int16()},
            meta_columns={
                "site": pa.string(),
                "source_file": pa.string(),
                "n_source_channels": pa.int32(),
                "timestamp_reversals": pa.int64(),
                "max_timestamp_reversal_s": pa.float64(),
                "ambiguous_samples": pa.int64(),
            },
        )
        with DatasetWriter(args.out_dir, spec) as writer:
            for name in FILES:
                n, local_sensors, markers, intervals, message_errors = sources[name]
                with archive.open(name) as stream:
                    frame = pd.read_csv(
                        stream,
                        sep=r"\s+",
                        header=None,
                        usecols=[0, 1, 2, 3],
                        names=["date", "time", "sensor", "value"],
                        dtype=str,
                        keep_default_na=False,
                    )
                assert len(frame) == n
                times = pd.to_datetime(
                    frame["date"] + " " + frame["time"], format="mixed"
                ).to_numpy(dtype="datetime64[ns]")
                assert not np.isnat(times).any()
                dt = np.diff(times).astype("timedelta64[ns]").astype(np.int64)
                values = pd.to_numeric(
                    frame["value"].replace(BINARY), errors="coerce"
                ).to_numpy(dtype=np.float32)
                assert np.array_equal(
                    np.flatnonzero(np.isnan(values)),
                    [r["source_row"] for r in message_errors],
                )
                signal = {}
                sensor_values = frame["sensor"].to_numpy()
                for sensor, channel in zip(sensors, channels, strict=True):
                    signal[channel] = np.full(n, np.nan, dtype=np.float32)
                    if sensor in local_sensors:
                        ix = sensor_values == sensor
                        signal[channel][ix] = values[ix]
                y, ambiguous = dense_sets(n, intervals, codes)
                sid = Path(name).stem
                labels = {"label_activity_set": y}
                writer.add_series(
                    sid,
                    signal,
                    labels=labels,
                    time=times,
                    meta={
                        "site": "tulum" if sid.startswith("tulum") else sid,
                        "source_file": name,
                        "n_source_channels": len(local_sensors),
                        "timestamp_reversals": int(np.sum(dt < 0)),
                        "max_timestamp_reversal_s": max(0.0, float(-dt.min() / 1e9)),
                        "ambiguous_samples": ambiguous,
                    },
                )
                stats.add(sid, labels)
                all_markers.extend(markers)
                all_intervals.extend(intervals)
                all_message_errors.extend(message_errors)
                print(
                    sid,
                    n,
                    len(local_sensors),
                    int(np.sum(dt < 0)),
                    ambiguous,
                    flush=True,
                )
                del frame, signal, values, times, y
    pq.write_table(
        pa.Table.from_pylist(all_markers),
        args.out_dir / "markers.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(all_intervals),
        args.out_dir / "intervals.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(all_message_errors),
        args.out_dir / "invalid_messages.parquet",
        compression="zstd",
    )
    activity_interval_counts = {
        Path(name).stem: dict(
            Counter(row["activity"] for row in value[3] if row["status"] == "paired")
        )
        for name, value in sources.items()
    }
    finish(
        args,
        spec,
        writer,
        stats,
        title="CASAS Aruba, Cairo, Milan and Tulum (five native event logs)",
        source="https://doi.org/10.5281/zenodo.17180309",
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="Five native irregular event streams from four homes, including both Tulum sessions; sparse sensor updates and reversible simultaneous-activity sets.",
        collection="Official CASAS deposit by Diane Cook with WSU data collectors; longitudinal community-home ambient PIR motion, door and temperature sensors. External observer activity annotations. Original WSU dataset index points to the CASAS Zenodo collection.",
        annotation="Exact begin/end marker strings and row offsets retained in markers.parquet; paired intervals in intervals.parquet. Endpoint rows included in an activity. Simultaneous activities are preserved as a reversible set-valued joint state (state_activity_sets), never resolved by selecting one activity. Empty annotated sets are unlabelled -1, not Other. Unpaired, malformed or repeated begin/end intervals are masked conservatively with -1; source strings are never repaired. Unmatched end with no identifiable start masks its own row only; its unknown preceding extent cannot be recovered.",
        conversion="Retain all five source files separately and all events in original file order, including nonmonotonic and duplicate timestamps. Preserve nanosecond timestamps. One channel per sensor ID; only the sensor observed at an event is populated, every other channel is NaN. No forward fill, interpolation, inferred off value or regular grid. ON/OPEN=1, OFF/CLOSE/CLOSED=0; numeric temperature values unchanged. Non-numeric malformed sensor messages (such as ONc) are retained verbatim in invalid_messages.parquet and represented as NaN for that observed sensor; no spelling correction is inferred. Sensor IDs are local to each home: identical IDs across sites do not imply identical locations. No event sorting, deletion or forced synchronisation. Source intervals are evaluated by source row order; this is an event-index segmentation task, not uniformly sampled physical time.",
        limitations="Sparse events, partial annotation and simultaneous multi-resident activities. The main integer label is a reversible encoding of an entire activity set, not a projection to one activity; use auxiliary intervals for individual-activity evaluation. Timestamp disorder is retained and reported per file. Tulum2 has malformed begin begin/begub markers and repeated/unmatched markers: ambiguous intervals are unscored, not corrected. Endpoint convention is explicit because deposit does not specify event endpoint inclusion. Site-specific sensor layouts and long unannotated gaps limit direct cross-home comparison.",
        biases="Only four community homes with differing residents, pets, layouts and sensors; highly personal routines and nonrepresentative activity prevalence.",
        personal="Pseudonymous home/sensor IDs, original event dates/times and inferred home activities retained. These reveal sensitive routines; direct resident identifiers, floorplans and videos are not included.",
        citation="Cook, D. (2025). CASAS Smart Home dataset (aruba, cairo, milan, tulum), v1. Zenodo. https://doi.org/10.5281/zenodo.17180309. Cook, Crandall, Thomas and Krishnan (2013), CASAS: A smart home in a box, IEEE Computer 46(7), 62–69.",
        creators=["Cook, Diane"],
        date_published="2025-09-23",
        info={
            "label_origin": "human",
            "individual_activity_interval_counts": activity_interval_counts,
            "invalid_sensor_message_count": len(all_message_errors),
            "anomalous_interval_count": sum(
                row["status"] != "paired" for row in all_intervals
            ),
            "state_names": {
                "label_activity_set": {v: " + ".join(k) for k, v in codes.items()}
            },
            "state_activity_sets": {v: list(k) for k, v in codes.items()},
            "binary_message_encoding": BINARY,
            "sampling": "irregular events in original source row order; no physical rate asserted",
            "annotation_interval_convention": "source rows begin..end inclusive; ambiguous spans masked",
            "source_files": FILES,
            "auxiliary": {
                "invalid_messages.parquet": "Malformed sensor messages preserved verbatim with source event row and sensor ID; numeric signal value is NaN.",
                "markers.parquet": "Every exact source marker, activity name and original event row (zero-based).",
                "intervals.parquet": "All paired and anomalous intervals; exact activity identity and inclusive source row bounds.",
            },
        },
    )


if __name__ == "__main__":
    main()
