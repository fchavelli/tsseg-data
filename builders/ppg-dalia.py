"""Preserve synchronized PPG-DaLiA physiology at every native sampling rate."""

from __future__ import annotations

import json
import pickle
import shutil
import sys
import zipfile
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.labels import runs  # noqa: E402
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "ppg-dalia"
SOURCE = "https://archive.ics.uci.edu/dataset/495/ppg+dalia"
PIN_FILE = Path(__file__).parent / "checksums" / f"{ID}.json"
STATES = {
    0: "transient_period",
    1: "sitting",
    2: "stairs",
    3: "table_soccer",
    4: "cycling",
    5: "driving",
    6: "lunch_break",
    7: "walking",
    8: "working",
}


class _ArrayToken:
    def __new__(cls, *args, **kwargs):
        raise pickle.UnpicklingError("Direct ndarray construction is forbidden")


def _reconstruct(subtype, shape, dtype):
    if subtype is not _ArrayToken or shape != (0,) or dtype not in ["b", b"b"]:
        raise pickle.UnpicklingError("Unexpected NumPy reconstruction arguments")
    from numpy._core.multiarray import _reconstruct as reconstruct

    return reconstruct(np.ndarray, (0,), b"b")


def _dtype(*args):
    dtype = np.dtype(*args)
    if dtype.hasobject or dtype.fields or dtype.subdtype or dtype.kind not in "biufSU":
        raise pickle.UnpicklingError("Object/structured NumPy dtype is forbidden")
    return dtype


class RestrictedUnpickler(pickle.Unpickler):
    """Allow only the three numeric NumPy primitives used by the source files.

    No import, arbitrary constructor, persistent ID or object array is allowed.
    The ndarray class is represented by an uncallable token; reconstruction
    accepts only the empty-array recipe used before a numeric array state.
    """

    def find_class(self, module, name):
        allowed = {
            ("numpy.core.multiarray", "_reconstruct"): _reconstruct,
            ("numpy._core.multiarray", "_reconstruct"): _reconstruct,
            ("numpy", "ndarray"): _ArrayToken,
            ("numpy", "dtype"): _dtype,
        }
        if (module, name) not in allowed:
            raise pickle.UnpicklingError(f"Forbidden pickle global: {module}.{name}")
        return allowed[(module, name)]

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("Persistent pickle IDs are forbidden")


def load_subject(archive, name):
    """Read one bounded ZIP member in memory, without extracting any source file."""
    entry = archive.getinfo(name)
    assert 0 < entry.file_size < 3 * 2**30
    with archive.open(entry) as stream:
        subject = RestrictedUnpickler(stream, encoding="latin1").load()
        assert stream.read(1) == b""  # Consume EOF and check ZIP CRC.
    assert isinstance(subject, dict)
    assert set(subject) == {
        "subject",
        "signal",
        "activity",
        "label",
        "rpeaks",
        "questionnaire",
    }
    return subject


def numeric(values, columns):
    values = np.asarray(values)
    assert values.dtype.kind in "biuf" and values.ndim in [1, 2]
    if values.ndim == 1:
        values = values[:, None]
    assert values.shape[1] == columns and len(values) > 0
    return values


def native_schema(channels):
    return pa.schema(
        [
            ("series_id", pa.string()),
            ("sample_index", pa.int32()),
            *[(c, pa.float32()) for c in channels],
        ]
    )


class NativeWriter:
    """Roll shared native sensor tables at approximately 256 MiB."""

    def __init__(self, root, group, channels, rate, auxiliary):
        self.root, self.group, self.channels = root, group, channels
        self.rate, self.auxiliary = rate, auxiliary
        self.schema = native_schema(channels)
        self.part, self.writer, self.path = -1, None, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.writer is not None:
            self.writer.close()

    def write_table(self, table):
        if self.writer is None or self.path.stat().st_size >= 256 * 2**20:
            if self.writer is not None:
                self.writer.close()
            self.part += 1
            name = f"native_{self.group}-{self.part:05d}.parquet"
            self.path = self.root / name
            self.writer = pq.ParquetWriter(
                self.path,
                self.schema,
                compression="zstd",
                compression_level=9,
                use_dictionary=["series_id"],
                use_byte_stream_split=self.channels,
                write_statistics=["series_id", "sample_index"],
            )
            self.auxiliary[name] = (
                f"All subjects' {self.group} samples at native {self.rate} Hz; "
                "zero-based sample_index within series_id, no resampling or interpolation. "
                "Parts share this schema and concatenate in filename order."
            )
        self.writer.write_table(table)


def write_native(writer, sid, signals):
    """Append bounded row groups to one shared table per native-rate stream."""
    lengths = {len(v) for v in signals.values()}
    assert len(lengths) == 1
    n = lengths.pop()
    for start in range(0, n, 262144):
        stop = min(start + 262144, n)
        data = {
            "series_id": pa.array([sid] * (stop - start)),
            "sample_index": pa.array(np.arange(start, stop, dtype=np.int32)),
            **{
                c: pa.array(v[start:stop], type=pa.float32())
                for c, v in signals.items()
            },
        }
        writer.write_table(pa.table(data, schema=writer.schema))
    return n


def main():
    args = parse_args(ID)
    pins = json.loads(PIN_FILE.read_text())
    raw = fetch(
        pins["data.zip"]["url"],
        "data.zip",
        pins["data.zip"]["sha256"],
        args.raw_dir,
        ID,
    )
    fetch(
        pins["readme.pdf"]["url"],
        "readme.pdf",
        pins["readme.pdf"]["sha256"],
        args.raw_dir,
        ID,
    )
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["wrist_bvp"],
        configs={"default": ["wrist_bvp"]},
        sampling_rate_hz=64,
        time_column=("sample_index", pa.int32()),
        label_columns={"label_activity": pa.int8()},
        meta_columns={
            "subject_id": pa.string(),
            "source_member": pa.string(),
            "native_lengths_json": pa.string(),
            "native_durations_s_json": pa.string(),
        },
    )
    activity_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("sample_index_4hz", pa.int32()),
            ("label_activity", pa.int8()),
        ]
    )
    reference_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("window_index", pa.int32()),
            ("window_start_s", pa.int32()),
            ("window_end_s", pa.int32()),
            ("heart_rate_bpm", pa.float64()),
        ]
    )
    peak_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("source_rpeak_index", pa.int64()),
        ]
    )
    stats = Statistics()
    auxiliary = {
        "activity_4hz.parquet": "Original protocol activity at 4 Hz; all nine codes including transient period 0.",
        "heart_rate_reference.parquet": "Source ECG-derived HR for 8-second windows shifted 2 seconds; not segmentation ground truth.",
        "rpeaks.parquet": "Source corrected ECG R-peak indices preserved literally; index origin not inferred, not segmentation labels.",
    }
    native_counts, source_dtypes, recurrence_without_transient = {}, {}, []
    rates = {
        "wrist_bvp": 64,
        "wrist_acc": 32,
        "wrist_slow": 4,
        "chest": 700,
        "activity": 4,
    }
    with (
        ExitStack() as stack,
        zipfile.ZipFile(raw) as archive,
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "activity_4hz.parquet", activity_schema, compression="zstd"
        ) as activity_writer,
        pq.ParquetWriter(
            args.out_dir / "heart_rate_reference.parquet",
            reference_schema,
            compression="zstd",
        ) as reference_writer,
        pq.ParquetWriter(
            args.out_dir / "rpeaks.parquet", peak_schema, compression="zstd"
        ) as peak_writer,
    ):
        group_channels = {
            "wrist_acc": [f"wrist_acc_{axis}" for axis in "xyz"],
            "wrist_slow": ["wrist_eda", "wrist_temperature"],
            "chest": [
                "chest_ecg",
                "chest_respiration",
                *[f"chest_acc_{axis}" for axis in "xyz"],
            ],
        }
        native_writers = {}
        for group, channels in group_channels.items():
            native_writers[group] = stack.enter_context(
                NativeWriter(args.out_dir, group, channels, rates[group], auxiliary)
            )
        members = [n for n in archive.namelist() if n.endswith(".pkl")]
        assert set(members) == {f"PPG_FieldStudy/S{i}/S{i}.pkl" for i in range(1, 16)}
        for i in range(1, 16):
            if shutil.disk_usage(args.out_dir).free < 18 * 2**30:
                raise RuntimeError("Disk reserve below 18 GiB")
            sid = f"S{i}"
            member = f"PPG_FieldStudy/{sid}/{sid}.pkl"
            data = load_subject(archive, member)
            assert str(data["subject"]) in [sid, str(i)]
            assert set(data["signal"]) == {"wrist", "chest"}
            wrist, chest = data["signal"]["wrist"], data["signal"]["chest"]
            assert set(wrist) == {"ACC", "BVP", "EDA", "TEMP"}
            assert set(chest) == {"ACC", "ECG", "Resp", "EDA", "EMG", "Temp"}
            bvp = numeric(wrist["BVP"], 1)[:, 0]
            wa, eda, temp = (
                numeric(wrist["ACC"], 3),
                numeric(wrist["EDA"], 1),
                numeric(wrist["TEMP"], 1),
            )
            ca, ecg, resp = (
                numeric(chest["ACC"], 3),
                numeric(chest["ECG"], 1),
                numeric(chest["Resp"], 1),
            )
            activity = numeric(data["activity"], 1)[:, 0]
            assert np.isin(activity, list(STATES)).all()
            activity = activity.astype(np.int8)
            assert len(eda) == len(temp)
            assert len(ca) == len(ecg) == len(resp)
            streams = {
                "wrist_acc": {
                    f"wrist_acc_{axis}": wa[:, j] for j, axis in enumerate("xyz")
                },
                "wrist_slow": {"wrist_eda": eda[:, 0], "wrist_temperature": temp[:, 0]},
                "chest": {
                    "chest_ecg": ecg[:, 0],
                    "chest_respiration": resp[:, 0],
                    **{f"chest_acc_{axis}": ca[:, j] for j, axis in enumerate("xyz")},
                },
            }
            lengths = {"wrist_bvp": len(bvp), "activity": len(activity)}
            for group, signals in streams.items():
                lengths[group] = write_native(native_writers[group], sid, signals)
            for group, n in lengths.items():
                native_counts[group] = native_counts.get(group, 0) + n
            source_dtypes[sid] = {
                "wrist_bvp": str(bvp.dtype),
                **{
                    g: {c: str(v.dtype) for c, v in signals.items()}
                    for g, signals in streams.items()
                },
            }
            source_dtypes[sid].update(
                {
                    k: str(np.asarray(data[k]).dtype)
                    for k in ["activity", "label", "rpeaks"]
                }
            )
            positions = np.arange(len(bvp), dtype=np.int64) // 16
            labels = np.full(len(bvp), -1, dtype=np.int8)
            valid = positions < len(activity)
            labels[valid] = activity[positions[valid]]
            writer.add_series(
                sid,
                {"wrist_bvp": bvp},
                labels={"label_activity": labels},
                time=np.arange(len(bvp), dtype=np.int32),
                meta={
                    "subject_id": sid,
                    "source_member": member,
                    "native_lengths_json": json.dumps(lengths),
                    "native_durations_s_json": json.dumps(
                        {g: n / rates[g] for g, n in lengths.items()}
                    ),
                },
            )
            activity_writer.write_table(
                pa.table(
                    {
                        "series_id": [sid] * len(activity),
                        "sample_index_4hz": np.arange(len(activity), dtype=np.int32),
                        "label_activity": activity,
                    },
                    schema=activity_schema,
                )
            )
            hr = numeric(data["label"], 1)[:, 0].astype(np.float64)
            assert np.isfinite(hr).all()
            windows = np.arange(len(hr), dtype=np.int32)
            reference_writer.write_table(
                pa.table(
                    {
                        "series_id": [sid] * len(hr),
                        "window_index": windows,
                        "window_start_s": 2 * windows,
                        "window_end_s": 2 * windows + 8,
                        "heart_rate_bpm": hr,
                    },
                    schema=reference_schema,
                )
            )
            peaks = np.asarray(data["rpeaks"]).reshape(-1)
            assert (
                peaks.dtype.kind in "iuf"
                and np.isfinite(peaks).all()
                and np.equal(peaks, np.floor(peaks)).all()
            )
            peak_writer.write_table(
                pa.table(
                    {
                        "series_id": [sid] * len(peaks),
                        "source_rpeak_index": peaks.astype(np.int64),
                    },
                    schema=peak_schema,
                )
            )
            values = runs(activity)[0]
            _, counts = np.unique(values[values > 0], return_counts=True)
            recurrence_without_transient.append(
                {"series_id": sid, "recurrent": bool(np.any(counts > 1))}
            )
            stats.add(sid, {"label_activity": labels})
            del data, streams, ca, ecg, resp, chest, wrist
            print(f"[{i}/15] {sid}: native lengths {lengths}", flush=True)
    finish(
        args,
        spec,
        writer,
        stats,
        title="PPG-DaLiA: all 15 synchronized recordings and native multivariate streams",
        source=SOURCE,
        sha256=sha256(PIN_FILE),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-19",
        description="All 15 provider-synchronized recordings: default native 64-Hz wrist BVP with protocol activity labels; every other genuine channel is retained in native-rate auxiliary tables (wrist ACC 32 Hz, EDA/TEMP 4 Hz; chest ECG/respiration/ACC 700 Hz). Eleven genuine physiological/motion channels in total; no new resampling.",
        collection="Bosch daily-life field protocol with Empatica E4 on the non-dominant wrist and RespiBAN chest device; eight activities and annotated transient periods. The released synchronized pickle files already include provider tap-based alignment and marginal clock-drift correction through sparse sample deletions. Preserve these released values, not a newly synchronized or resampled reconstruction. S6 contains only the provider's valid first approximately 1.5 hours.",
        annotation="Protocol activities at 4 Hz: 1 sitting, 2 stairs, 3 table soccer, 4 cycling, 5 driving, 6 lunch, 7 walking, 8 working. Source README section II explicitly defines 0 as transient periods between activities: retain it as an ordinary scored state. Map each native BVP sample to its containing source quarter-second interval, without interpolation; any samples beyond available annotation remain -1. Original 4-Hz activity retained. ECG-derived HR references (8-second windows, 2-second shifts) and manually checked R-peak indices are separate auxiliary reference measurements, never segmentation ground truth. Source R-peak indices retained literally without inferring an undocumented zero/one-based origin.",
        conversion="Primary UCI data.zip is SHA256-pinned, also qualified against its exact byte count and the CRC in the primary wrapper ZIP. Read one pickle member in a restricted unpickler: only numeric NumPy reconstruction/dtype primitives, with arbitrary globals, object arrays and persistent IDs forbidden; ZIP CRC checked at EOF. No source pickle is extracted or executed. Validate numeric shapes, state vocabulary and native per-stream lengths. Preserve all 11 genuine channels; cast signal values to float32, with source dtypes recorded. Exclude chest EDA/EMG/TEMP because primary README III.1/III.3 calls them dummy data. Default is BVP at 64 Hz; every other sensor remains unchanged at its native rate in flat auxiliary sample tables, indexed from zero. Source synchronized streams share the declared origin; any end-duration discrepancies are preserved. No further synchronization, resampling, filtering, physiological scaling, common-duration trimming or gap repair. Patient questionnaires and raw absolute device timestamps excluded. Preserve all source HR labels and corrected R-peaks separately. Evaluate by participant.",
        limitations="Activity is protocol truth rather than independent frame-level expert annotation. Quarter-second protocol timing does not imply sample-exact physiological or behavioral boundaries. All 15 recordings have recurrent transient state 0, and none has a recurring substantive activity (1–8). This supports protocol boundary CPD but offers weak substantive SD recurrence; report both the ordinary-state recurrence metric and the metric excluding transient 0. The default BVP view alone omits motion/ECG context; native auxiliary tables retain all multivariate information. ECG-based HR is derived reference information, not an independent activity annotator. Provider synchronization deleted sparse clock-drift samples before release; original unsynchronized H5/E4 streams are not a second aligned ground truth. Chest channels preserve source numerical units where the primary documentation does not establish engineering units. S6 has shorter valid coverage due to a hardware problem.",
        biases="Small healthy-adult cohort, one research-campus protocol and particular wearable placement/devices. Ordered activities and transition periods can reveal protocol position; generalization to unconstrained daily-life behavior or clinical populations is not established.",
        personal="Human physiological recordings with pseudonymous subject IDs. Do not export questionnaires, age, gender, anthropometrics, skin type, fitness or absolute device timestamps. No identifying linkage is attempted.",
        citation="Reiss, A.; Indlekofer, I.; Schmidt, P.; Van Laerhoven, K. (2019). Deep PPG: Large-Scale Heart Rate Estimation with Convolutional Neural Networks. Sensors 19(14):3079. doi:10.3390/s19143079. PPG-DaLiA, UCI Machine Learning Repository, doi:10.24432/C53890.",
        creators=["Attila Reiss", "Ina Indlekofer", "Philip Schmidt"],
        date_published="2019-07-29",
        null_states={"label_activity": [0]},
        info={
            "label_origin": "protocol",
            "state_names": {"label_activity": STATES},
            "default_label": "label_activity",
            "epoch_seconds": 0.25,
            "source_files": pins,
            "native_sampling_rates_hz": rates,
            "native_total_samples_per_stream": native_counts,
            "source_signal_dtypes": source_dtypes,
            "n_native_genuine_channels": 11,
            "state_recurrence_without_transient": recurrence_without_transient,
            "dummy_source_modalities_excluded": [
                "chest/EDA",
                "chest/EMG",
                "chest/Temp",
            ],
            "auxiliary": auxiliary,
        },
    )


if __name__ == "__main__":
    main()
