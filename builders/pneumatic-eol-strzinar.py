"""Build 156 native CSV triplets without forcing sensor clocks to align."""

from __future__ import annotations

import hashlib
import json
import sys
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
from tsseg_data.sources import fetch  # noqa: E402

ID = "pneumatic-eol-strzinar"
SOURCE = "https://data.mendeley.com/datasets/ypzswhhzh9/3"
MANIFEST = Path(__file__).parent / "checksums" / "pneumatic-eol-strzinar.json"
MANIFEST_SHA256 = "6057e8bf5fb001b1d6f5ff88c5dfeb409cbafceca8579df0d1f2ec2e9e9e1f97"
PREFIXES = {
    "pressure_bar": "Dump_long_100Hz_line_pressure_",
    "current_a": "Dump_long_100Hz_hall_sensor_",
    "state": "Dump_long_PLCstate_dt",
}

PLC_FILENAME_KEYS = {
    "20231002_123229": "20231002_123228",
    "20231129_103036": "20231129_103035",
}


def read_csv(path, date, column):
    frame = pd.read_csv(path, sep=";")
    assert frame.columns.tolist() == ["Time", column]
    time = pd.to_datetime(
        date + " " + frame.Time, format="%Y%m%d %H:%M:%S.%f"
    ).to_numpy(dtype="datetime64[ns]")
    values = frame[column].to_numpy()
    assert np.isfinite(values).all()
    return time, values


def main():
    args = parse_args(ID)
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == MANIFEST_SHA256
    pins = json.loads(MANIFEST.read_text())
    keys = sorted(
        name.removeprefix(PREFIXES["pressure_bar"]).removesuffix(".csv")
        for name in pins
        if name.startswith(PREFIXES["pressure_bar"])
    )
    assert len(keys) == 156 and len(pins) == 3 * len(keys)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["pressure_bar", "current_a"],
        configs={"default": ["pressure_bar", "current_a"]},
        time_column=("t_timestamp", pa.timestamp("ns")),
        label_columns={"label_plc_state": pa.int16()},
        meta_columns={
            "source_date": pa.string(),
            "n_pressure": pa.int64(),
            "n_current": pa.int64(),
            "n_plc_events": pa.int32(),
            "has_nonzero_state_recurrence": pa.bool_(),
        },
    )
    stats = Statistics()
    journal = []
    observed = set()
    nonzero_recurrence = []
    native_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("channel", pa.string()),
            ("sampling_rate_hz", pa.float64()),
            ("length", pa.int64()),
            ("timestamp_ns", pa.list_(pa.int64())),
            ("values", pa.list_(pa.float32())),
            ("timestamp_reversals", pa.int64()),
            ("duplicate_timestamps", pa.int64()),
        ]
    )
    timestamp_reversals = 0
    duplicate_timestamps = 0
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "native_sensors.parquet", native_schema, compression="zstd"
        ) as native_writer,
    ):
        for key in keys:
            native_rows = []
            native = {}
            for channel, prefix in PREFIXES.items():
                source_key = (
                    PLC_FILENAME_KEYS.get(key, key) if channel == "state" else key
                )
                name = prefix + source_key + ".csv"
                pin = pins[name]
                path = fetch(pin["url"], name, pin["sha256"], args.raw_dir, ID)
                native[channel] = read_csv(
                    path, key[:8], "PLC state" if channel == "state" else "Value"
                )
            state_t, state_v = native["state"]
            assert state_t[0] < native["pressure_bar"][0].max()
            assert state_t[-1] > native["pressure_bar"][0].min()
            assert np.equal(state_v, np.floor(state_v)).all()
            assert np.all(state_v >= 0) and np.all(state_v < 32768)
            state_v = state_v.astype(np.int16)
            observed.update(state_v.tolist())
            # Preserve original order separately; outer join never drops duplicate samples.
            frames = {}
            for channel, (ts, values) in native.items():
                timestamp_ns = ts.astype(np.int64)
                occurrences = (
                    pd.Series(timestamp_ns).groupby(timestamp_ns).cumcount().to_numpy()
                )
                frames[channel] = pd.DataFrame(
                    {
                        "timestamp_ns": timestamp_ns,
                        "occurrence": occurrences,
                        channel: values,
                    }
                ).set_index(["timestamp_ns", "occurrence"])
                if channel != "state":
                    native_rows.append(
                        {
                            "series_id": key,
                            "channel": channel,
                            "sampling_rate_hz": 100.0,
                            "length": len(ts),
                            "timestamp_ns": timestamp_ns.tolist(),
                            "values": values.astype(np.float32).tolist(),
                            "timestamp_reversals": int(
                                np.sum(np.diff(timestamp_ns) < 0)
                            ),
                            "duplicate_timestamps": int(len(ts) - len(np.unique(ts))),
                        }
                    )
            native_writer.write_table(
                pa.Table.from_pylist(native_rows, schema=native_schema)
            )
            timestamp_reversals += sum(r["timestamp_reversals"] for r in native_rows)
            duplicate_timestamps += sum(r["duplicate_timestamps"] for r in native_rows)
            combined = (
                frames["pressure_bar"]
                .join(frames["current_a"], how="outer")
                .sort_index()
            )
            time = (
                combined.index.get_level_values("timestamp_ns")
                .to_numpy()
                .astype("datetime64[ns]")
            )
            signal = {
                c: combined[c].to_numpy(dtype=np.float32)
                for c in ["pressure_bar", "current_a"]
            }
            assert np.all(np.diff(state_t) > np.timedelta64(0, "ns"))
            previous = np.searchsorted(state_t, time, side="right") - 1
            y = np.full(len(time), -1, dtype=np.int16)
            known = previous >= 0
            y[known] = state_v[previous[known]]
            values, _, _ = runs(y)
            _, counts = np.unique(values[(values > 0)], return_counts=True)
            nonzero = bool(np.any(counts > 1))
            nonzero_recurrence.append(nonzero)
            writer.add_series(
                key,
                signal,
                labels={"label_plc_state": y},
                time=time,
                meta={
                    "source_date": key[:8],
                    "n_pressure": len(native["pressure_bar"][0]),
                    "n_current": len(native["current_a"][0]),
                    "n_plc_events": len(state_t),
                    "has_nonzero_state_recurrence": nonzero,
                },
            )
            stats.add(key, {"label_plc_state": y})
            for i, (t, state) in enumerate(zip(state_t, state_v, strict=True)):
                journal.append(
                    {
                        "series_id": key,
                        "source_event_idx": i,
                        "timestamp_ns": int(t.astype(np.int64)),
                        "plc_state": int(state),
                    }
                )
            print(key, len(time), len(state_t), nonzero, flush=True)
    pq.write_table(
        pa.Table.from_pylist(journal),
        args.out_dir / "plc_events.parquet",
        compression="zstd",
    )
    if stats.summary()["tracks"]["label_plc_state"]["series_with_recurrence"] == 0:
        spec.task = "cpd"
    finish(
        args,
        spec,
        writer,
        stats,
        title="Pneumatic pressure and electrical current end-of-line test recordings",
        source="https://doi.org/10.17632/ypzswhhzh9.3",
        sha256=MANIFEST_SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="All 156 source recording triplets: native pressure/current measurements and timestamped PLC states, preserved on an exact irregular sensor timestamp union.",
        collection="Real manufacturing end-of-line station tests small electric drive assemblies over seven operating days, roughly 150 pieces. Pressure and hall-sensor electrical current are nominally 100 Hz; PLC log records internal state changes. Primary Mendeley Data version 3 by Stržinar and colleagues.",
        annotation="Source PLC journal defines protocol states. Primary CSV demonstration explicitly plots states steps-post: most recent state applies from its timestamp until next state change. Preserve all observed nonnegative codes, including 0 as an ordinary automate state, never null. Before first known state use -1. Preserve exact journal events separately. Labels are machine protocol, not independent human annotators.",
        conversion="Use all 468 CSV files as 156 matching triplets, never unpickle the segmented alternatives. Add source filename date to each time-of-day as the primary demo does. Two PLC filenames are one second earlier than their matching sensor filenames (20231002_123228 and 20231129_103035); explicit filename aliases select these journals and assert temporal overlap, without shifting timestamps. Sensor clocks differ slightly: retain every measurement at its exact native timestamp, outer-union both sensor clocks, fill unobserved channel with NaN. Original sensor order and every native sample retained in native_sensors.parquet. Main projection sorts by exact timestamp; repeated timestamps use stable per-stream occurrence ranks so no sample is dropped. No averaging, interpolation, nearest-neighbour alignment, sample deletion or synthetic concatenation. Main output is irregular, with native nominal sensor rates 100 Hz recorded separately; it must not be interpreted as uniformly sampled at 100 Hz. Pressure is bar and current A per primary demo. Last PLC state continues to recording end. No PLC-only observation is invented: an initial state recorded before either sensor starts remains in the auxiliary journal, without becoming an all-NaN principal sample.",
        limitations="Single test station and mostly fixed protocol order. Recurrence may be concentrated in idle state 0: nonzero-state recurrence is also measured separately. The exact union is sparse and irregular despite nominal 100-Hz sensors; uniform-grid methods require a separately declared preprocessing policy. PLC states are not directly descriptive action names; no semantic names invented.",
        biases="One manufacturing site, station and product family; protocol transitions may not generalise to faults or different machines.",
        personal="Industrial sensor measurements, machine-state codes and capture dates/times; no participant or direct personal information.",
        citation="Stržinar, Ž., Pregelj, B., Petrovčič, J., Škrjanc, I., and Dolanc, G. (2024). Pneumatic Pressure and Electrical Current Time Series in Manufacturing, version 3. Mendeley Data. https://doi.org/10.17632/ypzswhhzh9.3.",
        creators=[
            "Stržinar, Žiga",
            "Pregelj, Boštjan",
            "Petrovčič, Janko",
            "Škrjanc, Igor",
            "Dolanc, Gregor",
        ],
        date_published="2024-05-21",
        info={
            "label_origin": "protocol",
            "state_names": {
                "label_plc_state": {i: f"PLC state {i}" for i in sorted(observed)}
            },
            "source_version": 3,
            "state_detection_eligible": spec.task == "sd",
            "use_cases": "Change point detection; state recurrence is measured on actual sensor observations only. No PLC-only points are introduced.",
            "plc_filename_keys": PLC_FILENAME_KEYS,
            "native_nominal_sampling_rate_hz": {"pressure_bar": 100, "current_a": 100},
            "sampling": "exact irregular union of native sensor timestamps; PLC journal applied steps-post",
            "series_with_nonzero_state_recurrence": sum(nonzero_recurrence),
            "sensor_timestamp_reversals": timestamp_reversals,
            "sensor_duplicate_timestamps": duplicate_timestamps,
            "source_sha256_scope": "SHA256 of committed CSV transport manifest; every CSV has a primary Mendeley SHA256 pin.",
            "source_sha256_manifest": "builders/checksums/pneumatic-eol-strzinar.json",
            "auxiliary": {
                "native_sensors.parquet": "Every native sensor timestamp and value in original CSV row order; 100-Hz nominal rate, reversal and duplicate counts.",
                "plc_events.parquet": "Every original PLC state and exact source timestamp (Unix ns, no timezone asserted), with original event index.",
            },
        },
    )


if __name__ == "__main__":
    main()
