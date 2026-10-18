"""Build native neonatal EEG and all three independent seizure annotations."""

from __future__ import annotations

import itertools
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from scipy.io import loadmat  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.labels import cohen_kappa  # noqa: E402
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "helsinki-neonatal-eeg"
SOURCE = "https://zenodo.org/records/4940267"
PIN_FILE = Path(__file__).parent / "checksums" / f"{ID}.json"
PINS = json.loads(PIN_FILE.read_text())
ELECTRODES = [
    "Fp1",
    "Fp2",
    "F3",
    "F4",
    "C3",
    "C4",
    "P3",
    "P4",
    "O1",
    "O2",
    "F7",
    "F8",
    "T3",
    "T4",
    "T5",
    "T6",
    "Fz",
    "Cz",
    "Pz",
]
NATIVE = [f"EEG {name}-REF" for name in ELECTRODES] + ["ECG EKG-REF", "Resp Effort-REF"]
CHANNELS = [f"eeg_{name.lower()}_ref_uv" for name in ELECTRODES] + [
    "ecg_ekg_uv",
    "resp_effort_uv",
]
DEFAULT_ELECTRODES = ["Fp1", "Fp2", "C3", "C4", "T3", "T4", "O1", "O2"]
DEFAULT = [f"eeg_{name.lower()}_ref_uv" for name in DEFAULT_ELECTRODES]
EXPERTS = ["A", "B", "C"]
ANNOTATIONS = [
    "annotations_2017_A_fixed.csv",
    "annotations_2017_B.csv",
    "annotations_2017_C.csv",
]
STATES = {0: "non_seizure", 1: "seizure"}


def read_header(path: Path):
    """Validate plain EDF record layout without requiring an annotation channel.

    Some sources declare EDF+C while containing only 21 ordinary signals.
    Keep this source flag; no missing annotation channel or gap is invented.
    """
    with path.open("rb") as f:
        fixed = f.read(256)
        assert fixed[:8] == b"0       "
        nch = int(fixed[252:256])
        size = int(fixed[184:192])
        assert nch == 21 and size == 256 * (nch + 1)
        variable = f.read(size - 256)
    fields = {}
    offset = 0
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
            variable[offset + j * width : offset + (j + 1) * width]
            .decode("ascii")
            .strip()
            for j in range(nch)
        ]
        offset += nch * width
    assert offset == len(variable)
    records = int(fixed[236:244])
    duration = float(fixed[244:252])
    reserved = fixed[192:236].decode("ascii").strip()
    assert records > 0 and duration > 0 and reserved in ["", "EDF+C"]
    headers = []
    for i in range(nch):
        h = {k: fields[k][i] for k in fields}
        for key in ["physical_min", "physical_max"]:
            h[key] = float(h[key])
        for key in ["digital_min", "digital_max", "samples_per_record"]:
            h[key] = int(h[key])
        assert -32768 <= h["digital_min"] < h["digital_max"] <= 32767
        assert np.isfinite([h["physical_min"], h["physical_max"]]).all()
        assert h["physical_min"] != h["physical_max"]
        h["sample_frequency"] = h["samples_per_record"] / duration
        headers.append(h)
    assert all(h["sample_frequency"] == 256 for h in headers)
    assert len({h["samples_per_record"] for h in headers}) == 1
    bytes_per_record = 2 * sum(h["samples_per_record"] for h in headers)
    assert path.stat().st_size == size + records * bytes_per_record
    return headers, records, duration, reserved, size


def read_signals(path: Path, headers, records, header_bytes):
    """Decode little-endian signed EDF int16 data with each source calibration."""
    digital = np.memmap(
        path,
        mode="r",
        dtype="<i2",
        offset=header_bytes,
        shape=(records, len(headers), headers[0]["samples_per_record"]),
    )
    result = []
    for i, h in enumerate(headers):
        gain = (h["physical_max"] - h["physical_min"]) / (
            h["digital_max"] - h["digital_min"]
        )
        offset = h["physical_min"] - gain * h["digital_min"]
        values = digital[:, i, :].reshape(-1).astype(np.float64)
        result.append((values * gain + offset).astype(np.float32))
    del digital
    return result


def channel_key(label: str) -> str:
    """Resolve native capitalization/order variants without changing derivations."""
    return label.strip().upper().removesuffix("-REF")


def source(name, args):
    pin = PINS[name]
    if pin["sha256"] is None:
        raise RuntimeError(f"Unqualified source SHA256: {name}")
    return fetch(pin["url"], name, pin["sha256"], args.raw_dir, ID)


def main() -> None:
    args = parse_args(ID)
    annotations = [pd.read_csv(source(name, args)) for name in ANNOTATIONS]
    assert all(list(frame) == [str(i) for i in range(1, 80)] for frame in annotations)
    mat = loadmat(source("annotations_2017.mat", args))["annotat_new"][0]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": DEFAULT, "full": CHANNELS},
        sampling_rate_hz=256,
        time_column=("sample_index", pa.int32()),
        label_columns={f"label_{a}": pa.int8() for a in ["consensus", *EXPERTS]},
        meta_columns={
            "source_subject_id": pa.int32(),
            "source_file": pa.string(),
            "source_reserved_field": pa.string(),
            "source_data_records": pa.int32(),
            "source_record_duration_s": pa.float64(),
            "native_channel_headers_json": pa.string(),
        },
    )
    epoch_schema = pa.schema(
        [
            ("series_id", pa.string()),
            ("second", pa.int32()),
            *[(f"label_{a}", pa.int8()) for a in ["consensus", *EXPERTS]],
        ]
    )
    stats = Statistics()
    kappas, accuracies = [], []
    total_seconds = 0
    nonstandard_edf_plus = []
    source_layout_counts = {}
    disagreement_seconds = 0
    seizure_events = {a: 0 for a in EXPERTS}
    with (
        DatasetWriter(args.out_dir, spec) as writer,
        pq.ParquetWriter(
            args.out_dir / "epochs_1hz.parquet", epoch_schema, compression="zstd"
        ) as epoch_writer,
    ):
        for number in range(1, 80):
            if shutil.disk_usage(args.out_dir).free < 18 * 2**30:
                raise RuntimeError("Disk reserve below 18 GiB; stop before next EEG")
            name = f"eeg{number}.edf"
            sid = f"eeg{number}"
            raw = source(name, args)
            headers, records, duration, reserved, header_bytes = read_header(raw)
            values_native = read_signals(raw, headers, records, header_bytes)
            native_labels = [h["label"] for h in headers]
            layout = tuple(native_labels)
            source_layout_counts[layout] = source_layout_counts.get(layout, 0) + 1
            if reserved == "EDF+C":
                nonstandard_edf_plus.append(sid)
            positions = {channel_key(label): i for i, label in enumerate(native_labels)}
            assert len(positions) == len(NATIVE) and set(positions) == {
                channel_key(label) for label in NATIVE
            }, name
            assert all(h["dimension"] == "uV" for h in headers), name
            assert all(h["sample_frequency"] == 256 for h in headers), name
            n = records * headers[0]["samples_per_record"]
            assert all(len(values) == n for values in values_native) and n % 256 == 0, (
                name
            )
            seconds = n // 256
            epochs = {}
            for index, (a, frame) in enumerate(zip(EXPERTS, annotations, strict=True)):
                values = frame[str(number)]
                assert (
                    values.iloc[:seconds].notna().all()
                    and values.iloc[seconds:].isna().all()
                ), (name, a)
                y = values.iloc[:seconds].to_numpy(dtype=np.int8)
                assert np.isin(y, [0, 1]).all()
                assert mat[number - 1].shape == (3, seconds) and np.array_equal(
                    y, mat[number - 1][index]
                )
                epochs[f"label_{a}"] = y
                seizure_events[a] += int(np.count_nonzero(np.diff(np.r_[0, y]) == 1))
            votes = np.array(list(epochs.values()))
            same = np.all(votes == votes[0], axis=0)
            consensus = np.where(same, votes[0], -1).astype(np.int8)
            epochs = {"label_consensus": consensus, **epochs}
            total_seconds += seconds
            disagreement_seconds += int((~same).sum())
            for a, b in itertools.combinations(EXPERTS, 2):
                x, y = epochs[f"label_{a}"], epochs[f"label_{b}"]
                kappas.append(cohen_kappa(x, y))
                accuracies.append(float((x == y).mean()))
            signal = {
                c: values_native[positions[channel_key(native)]]
                for c, native in zip(CHANNELS, NATIVE, strict=True)
            }
            labels = {c: np.repeat(values, 256) for c, values in epochs.items()}
            writer.add_series(
                sid,
                signal,
                labels=labels,
                time=np.arange(n, dtype=np.int32),
                annotators=EXPERTS,
                meta={
                    "source_subject_id": number,
                    "source_file": name,
                    "source_reserved_field": reserved,
                    "source_data_records": records,
                    "source_record_duration_s": duration,
                    "native_channel_headers_json": json.dumps(headers),
                },
            )
            epoch_writer.write_table(
                pa.Table.from_pydict(
                    {
                        "series_id": [sid] * seconds,
                        "second": np.arange(seconds, dtype=np.int32),
                        **epochs,
                    },
                    schema=epoch_schema,
                )
            )
            stats.add(sid, labels)
            print(
                f"[{number}/79] {sid}: {seconds} seconds, all 21 native channels",
                flush=True,
            )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Helsinki neonatal EEG: all 79 recordings and three seizure experts",
        source=SOURCE,
        sha256=sha256(PIN_FILE),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-19",
        description="All 79 original neonatal recordings at native 256 Hz: default includes eight bilateral frontal, central, temporal and occipital EEG electrodes (Fp1/Fp2/C3/C4/T3/T4/O1/O2); full preserves all 19 EEG electrodes plus released ECG and respiration channels (21 total). Three independent 1-Hz binary expert seizure annotations retained; derived strict consensus scores only unanimous seconds.",
        collection="Term-neonate recordings from Helsinki University Hospital NICU, released by Stevenson, Tapani, Lauronen and Vanhatalo. Primary EDF headers contain 19 referential EEG, ECG and respiration at 256 Hz; every recording header was audited. Native calibrated microvolt values retained, including source recording pauses, zero blocks, artefacts and outliers, without extra filtering or rereferencing.",
        annotation="Three independent expert tracks A/B/C annotate seizure presence every second, codes 0 non-seizure and 1 seizure. Both are scored states; no null class. Source version 4 replaces A CSV with A_fixed only to remove extra values outside the first three recordings; all actual-duration CSV labels are checked against the released MAT and match. The paper describes experienced experts viewing a bipolar montage and ECG, with one-second timing; A/B/C identities are kept as source codes. Derived label_consensus is the common expert code when all three agree, otherwise -1; disagreement is unknown only for this consensus reference, never erased from individual experts. This strict unanimity follows the paper's use of all-three-expert consensus; it is not clinical adjudication or majority voting. Native 1-Hz epochs retained separately and repeated for the 256-Hz signals. Boundary precision is one second, not a sample-exact physiological onset.",
        conversion="Download only 79 EDF and four annotation files, all SHA-pinned with primary published MD5 provenance. Read EDF little-endian int16 records directly with source per-channel physical/digital calibration in float64, then cast values to float32; check record counts, per-channel samples, record duration and exact file size. Preserve the source reserved EDF/EDF+C flag. Three files (eeg4, eeg29, eeg50) declare EDF+C without an annotation channel and are rejected by strict pyedflib; these contain the same 21 numeric streams and are decoded without inventing absent annotations. Numeric decoding was checked against pyedflib on eeg1/eeg2/eeg3/eeg5 across all three native layouts, with identical float32 values in every channel. Keep every native sample and channel in source record order on the nominal 256-Hz grid. No demography, clinical diagnoses, ECG/respiration removal in full, resampling, gap repair, signal normalization or event-based cropping. CSV column 1–79 maps explicitly to EEG1–79; first data row is the first one-second interval, trailing NaN cells outside the recording are excluded only after exact duration checks. The light default retains Fp1/Fp2/C3/C4/T3/T4/O1/O2 without rereferencing, reducing duplicated storage; full retains all 21 native channels. Native channel order/case varies across three layouts: map names case-insensitively after removing only the -REF suffix, never align by column position. All 21 channels, including ECG and respiration, have EDF-header physical dimension uV in all 79 files. Source patient text and clinical CSV not copied; signal calibration headers retained without patient information. Use participant-level splits; source has one recording per numbered neonate.",
        limitations="Consensus disagreement is intentionally unscored in the derived track, while all expert labels remain evaluable. Many records have no seizure and class imbalance can make sample agreement high. One-second expert timing does not support subsecond boundary accuracy. EDF record counters and duration define the nominal grid; source headers do not establish the physical durations of pauses or other missing acquisition periods. Source EEG contains recording pauses and high-amplitude artefacts; no new artefact masking is applied. Referential EEG is not converted to the bipolar montage illustrated in the source paper. Default has eight EEG electrodes for storage and compute convenience; experts viewed broader spatial context, so focal seizures may be poorly represented in this reduced view. Use full for analyses requiring the complete clinical observation context. Clinical diagnostic validity is not established by these benchmark labels.",
        biases="Single NICU and expert team, term neonates with selected clinical presentations, historical acquisition and limited cohort size; cannot assume generalisation to premature infants, other sites or devices.",
        personal="Sensitive neonatal health signals and pseudonymous numbered study IDs retained. Clinical-information spreadsheet, EDF patient text, demographic attributes and absolute recording dates/times excluded from output; no linkage to individuals is attempted.",
        citation="Stevenson, Nathan J.; Tapani, Karoliina; Lauronen, Leena; Vanhatalo, Sampsa (2019). A dataset of neonatal EEG recordings with seizure annotations. Scientific Data 6:190039. doi:10.1038/sdata.2019.39. Data version 4: doi:10.5281/zenodo.4940267.",
        creators=[
            "Nathan Stevenson",
            "Karoliina Tapani",
            "Leena Lauronen",
            "Sampsa Vanhatalo",
        ],
        date_published="2018-06-05",
        info={
            "state_names": {c: STATES for c in spec.label_columns},
            "default_label": "label_consensus",
            "annotators": EXPERTS,
            "label_origin": "human",
            "reference_doi": "https://doi.org/10.1038/sdata.2019.39",
            "epoch_seconds": 1,
            "source_files": PINS,
            "source_version": "4.0 (corrected A CSV)",
            "native_channel_names": NATIVE,
            "nonstandard_edf_plus_without_annotations": nonstandard_edf_plus,
            "source_layouts": [
                {"native_channel_names": list(layout), "recordings": count}
                for layout, count in source_layout_counts.items()
            ],
            "native_units": {c: "uV" for c in CHANNELS},
            "default_electrodes": DEFAULT_ELECTRODES,
            "channel_alignment": "case-insensitive names, optional -REF suffix; three original layouts preserved in per-record headers",
            "native_epoch_seconds": total_seconds,
            "consensus_disagreement_seconds": disagreement_seconds,
            "source_seizure_events_per_expert": seizure_events,
            "agreement": {
                "unit": "1-Hz source labels; mean of three expert pairs per recording",
                "pairs": len(kappas),
                "mean_cohen_kappa": float(np.mean(kappas)),
                "mean_sample_agreement": float(np.mean(accuracies)),
                "constant_agreeing_pair_kappa": 1.0,
            },
            "auxiliary": {
                "epochs_1hz.parquet": "Every native one-second A/B/C label and derived strict unanimous consensus; disagreement -1 only in consensus, with zero-based source second index."
            },
        },
    )


if __name__ == "__main__":
    main()
