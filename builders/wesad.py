"""Build all synchronized WESAD subjects locally; source terms forbid rehosting."""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa

from tsseg_data.batch import Statistics, finish
from tsseg_data.build import parse_args
from tsseg_data.format import DatasetSpec, DatasetWriter
from tsseg_data.sources import sha256
from tsseg_data.wesad import (
    CHEST,
    RESERVE,
    SIZE,
    SUBJECTS,
    WRIST,
    NativeWriter,
    acquire,
    channels,
    load_subject,
)

ID = "wesad"
SOURCE = "https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html"
PIN = Path(__file__).parent / "checksums/wesad.json"
STATES = {1: "baseline", 2: "stress", 3: "amusement", 4: "meditation"}
SCOPE = "Primary Siegen terms allow scientific, non-commercial use with attribution. No named open licence or explicit redistribution grant. Tier C, source-only builder and local build; do not rehost data, derived tables or source questionnaires. Conversion code is MIT."


def main():
    args = parse_args(
        ID, extra=lambda p: p.add_argument("--pilot", action="store_true")
    )
    raw = args.raw_dir / ID
    raw.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(raw).free - SIZE - 12 * 2**30 < RESERVE:
        raise RuntimeError("Source/output budget above18 GiB reserve unavailable")
    pin = json.loads(PIN.read_text())
    archive_path, _ = acquire(raw, pin["archive"])
    names = [name for values in CHEST.values() for name in values]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=names,
        configs={"default": names},
        sampling_rate_hz=700,
        channel_type=pa.float64(),
        time_column=("sample_index", pa.int64()),
        label_columns={"label_protocol": pa.int8()},
        meta_columns={
            "subject_id": pa.string(),
            "native_samples_wrist_acc": pa.int64(),
            "native_samples_wrist_bvp": pa.int64(),
            "native_samples_wrist_slow": pa.int64(),
        },
    )
    auxiliary, details, source_dtypes, stats = {}, [], {}, Statistics()
    quality_notes = {}
    selected = ["S15"] if args.pilot else SUBJECTS
    with ExitStack() as stack:
        archive = stack.enter_context(zipfile.ZipFile(archive_path))
        assert {n for n in archive.namelist() if n.endswith(".pkl")} == {
            f"WESAD/{sid}/{sid}.pkl" for sid in SUBJECTS
        }
        writer = stack.enter_context(DatasetWriter(args.out_dir, spec))
        streams = {
            group: stack.enter_context(
                NativeWriter(
                    args.out_dir,
                    f"wrist_{group}",
                    [name for names in mapping.values() for name in names],
                    rate,
                    auxiliary,
                )
            )
            for group, (rate, mapping) in WRIST.items()
        }
        native_protocol = stack.enter_context(
            NativeWriter(
                args.out_dir, "protocol", ["source_label"], 700, auxiliary, integer=True
            )
        )
        for sid in selected:
            if shutil.disk_usage(raw).free - 2**30 < RESERVE:
                raise RuntimeError("18 GiB reserve plus write buffer unavailable")
            data = load_subject(archive, sid)
            notes = archive.read(f"WESAD/{sid}/{sid}_readme.txt").decode("utf-8")
            additional = notes.split("### Additional notes ###", 1)[-1]
            quality_notes[sid] = [
                line.strip()
                for line in additional.splitlines()
                if "sensor" in line.lower() or "signal" in line.lower()
            ]
            chest = channels(data["signal"]["chest"], CHEST)
            n = len(next(iter(chest.values())))
            original = np.asarray(data["label"])
            assert (
                original.ndim == 1
                and len(original) == n
                and original.dtype.kind in "biuf"
            )
            assert np.isin(original, list(range(8))).all()
            codes = original.astype(np.int8)
            labels = np.where(np.isin(codes, [1, 2, 3, 4]), codes, -1).astype(np.int8)
            assert set(data["signal"]["wrist"]) == {"ACC", "BVP", "EDA", "TEMP"}
            counts, durations, dtypes, defects = {}, {"chest": n / 700}, {}, {}
            for group, (rate, mapping) in WRIST.items():
                wrist = channels(
                    {key: data["signal"]["wrist"][key] for key in mapping}, mapping
                )
                streams[group].write(sid, wrist)
                counts[group] = len(next(iter(wrist.values())))
                durations[f"wrist_{group}"] = counts[group] / rate
                for name, values in wrist.items():
                    dtypes[name] = str(values.dtype)
                    defects[name] = int(np.count_nonzero(~np.isfinite(values)))
            native_protocol.write(sid, {"source_label": codes})
            if shutil.disk_usage(raw).free - 2**30 < RESERVE:
                raise RuntimeError("18 GiB reserve plus write buffer unavailable")
            writer.add_series(
                sid,
                chest,
                labels={"label_protocol": labels},
                time=np.arange(n, dtype=np.int64),
                meta={
                    "subject_id": sid,
                    **{
                        f"native_samples_wrist_{group}": count
                        for group, count in counts.items()
                    },
                },
            )
            for name, values in chest.items():
                dtypes[name] = str(values.dtype)
                defects[name] = int(np.count_nonzero(~np.isfinite(values)))
            source_dtypes[sid] = {**dtypes, "source_label": str(original.dtype)}
            stats.add(sid, {"label_protocol": labels})
            details.append(
                {
                    "series_id": sid,
                    "native_samples_chest": n,
                    "native_samples_wrist": counts,
                    "native_durations_s": durations,
                    "source_code_counts": {
                        str(code): int(np.count_nonzero(codes == code))
                        for code in range(8)
                    },
                    "masked_samples": int(np.count_nonzero(labels == -1)),
                    "nonfinite_signal_counts": defects,
                }
            )
            print(sid, n, counts, details[-1]["source_code_counts"], flush=True)
            del data, chest, wrist, original, codes, labels
    if not args.pilot:
        assert len(stats.rows) == 15
    finish(
        args,
        spec,
        writer,
        stats,
        title="WESAD: complete synchronized native-rate physiology (source-only local build)",
        source=SOURCE,
        sha256=sha256(PIN),
        license_spdx="LicenseRef-Siegen-WESAD-Scientific-NonCommercial",
        license_url=SOURCE,
        license_evidence=SOURCE,
        license_verified_date="2026-10-21",
        description="Source-only local WESAD conversion: all15 released synchronized subjects, eight chest channels at native700Hz and all six wrist channels at native32/64/4Hz, with original protocol codes and an explicit evaluation mask. No resampling, learned features or rehosting.",
        collection="Primary Siegen archive linked from the authors' dataset page. Seventeen participants were recorded; S1 and S12 were excluded by the provider after sensor malfunction, leaving all15 released subjects. The selected complete view is every synchronized SX.pkl, not independent copies of unsynchronized RespiBAN TXT/E4 ZIP streams. Eight genuine chest channels (ACCxyz,ECG,EDA,EMG,respiration,temperature), all700Hz. Wrist ACCxyz32Hz, BVP64Hz, EDA/temperature4Hz remain separate native tables. Source double-tap synchronization supplies a common origin; retain native end lengths without common-duration trimming.",
        annotation="Primary archive README II.3 defines source700Hz protocol codes:0 not defined/transient,1 baseline,2 stress,3 amusement,4 meditation,5/6/7 ignored. Preserve every original code in native_protocol tables. The default evaluation label maps0 and5–7 to-1; keep1–4 literally, without treating undefined0 as rest or a negative state. No labels are interpolated to wrist streams. Protocol conditions are experimental schedule reference, not clinical diagnoses or independently observed sample-exact affect. Self-report questionnaire answers are a different reference and are not inferred as segmentation labels.",
        conversion="Exact primary ZIP size, provider MD5/SHA1 and local SHA256 pins; bounded32MiB HTTP206/Content-Range/ETag transfers with retries and reserve checks. Read one synchronized pickle member at a time through a restrictive numeric NumPy unpickler; no downloaded code, arbitrary globals, object arrays or persistent IDs. Consume ZIP EOF/CRC; never extract the17.58GB raw archive. Validate all subject IDs, keys, shapes, native channel counts and label vocabulary. Preserve numeric signal values losslessly as float64, including NaN/Inf if present; record original dtypes. No new calibration, filtering, normalization, sample deletion, resampling, synchronization or gap repair. Default chest sample_index is exact zero-based integer with physical time sample_index/700 seconds; auxiliary sample indices use their own explicit native rates. All subjects share table files, with normal one-hour chest chunks. Preserve each original700Hz code separately from the scored evaluation label. Exclude questionnaires, demographics, absolute device timestamps and unsynchronized alternative recordings.",
        limitations="Small induced-affect laboratory study; protocol boundaries do not prove instantaneous physiological or psychological state changes. Undefined/transient0 and source-ignore5–7 are unscored, and their original codes and per-code counts remain available. Report recurrence only over valid1–4, including repeated meditation when actually present. Native wrist tables are necessary for the complete14-channel view and do not share a fabricated common sample grid. Released synchronized stream durations may differ and remain unchanged. Source notes report incomplete chest-temperature sensor attachment for S2 and S17; retain these notes and readings without an invented quality mask. Provider synchronization and calibration have already affected the released numeric arrays; this conversion makes no additional correction or claim of access to an earlier waveform.",
        biases="Small controlled laboratory cohort and induced stress tasks limit generalization to unconstrained life and clinical populations. Split by participant; source provides no universal train/test assignment. Multiple channels within a participant are correlated modalities, not annotation raters.",
        personal="Source physiological recordings can convey personal characteristics. Package anonymous subject IDs and synchronized numeric signals/protocol codes only; exclude participant demographics, questionnaires and absolute timestamps. Local source-only artifact; source terms do not establish redistribution rights.",
        citation="Schmidt P., Reiss A., Duerichen R., Marberger C., Van Laerhoven K. (2018). Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection. ICMI2018,400–408. https://doi.org/10.1145/3242969.3242985",
        creators=[
            "Philip Schmidt",
            "Attila Reiss",
            "Robert Duerichen",
            "Claus Marberger",
            "Kristof Van Laerhoven",
        ],
        date_published="2018-10-16",
        null_states={},
        info={
            "hf_license": "other",
            "license_scope": SCOPE,
            "rehosting_allowed": False,
            "source_only": True,
            "label_origin": "protocol",
            "state_names": {"label_protocol": STATES},
            "annotators": [],
            "tracks": {
                "label_protocol": {
                    "semantics": "protocol condition, excluding native0/5–7; not an expert affect annotation"
                }
            },
            "native_sampling_rates_hz": {
                "chest": 700,
                "protocol": 700,
                **{f"wrist_{group}": rate for group, (rate, _) in WRIST.items()},
            },
            "native_chest_channels": names,
            "native_wrist_channels": {
                group: [name for names in mapping.values() for name in names]
                for group, (_, mapping) in WRIST.items()
            },
            "source_dtypes": source_dtypes,
            "source_sensor_quality_notes": quality_notes,
            "source_code_names": {
                "0": "not_defined_or_transient",
                **{str(k): v for k, v in STATES.items()},
                "5": "source_ignore",
                "6": "source_ignore",
                "7": "source_ignore",
            },
            "source_files": pin,
            "series_details": details,
            "auxiliary": auxiliary,
            "reference_doi": "https://doi.org/10.1145/3242969.3242985",
        },
    )


if __name__ == "__main__":
    main()
