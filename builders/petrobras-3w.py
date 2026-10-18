"""Build all measured 3W 2.0.0 instances; generated origins require explicit opt-in."""

from __future__ import annotations

import configparser
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "petrobras-3w"
SOURCE = "https://figshare.com/articles/dataset/3W_Dataset_2_0_0/29205836/1"
URL = "https://ndownloader.figshare.com/files/55019255"
SHA256 = "c037a6a9d5dcc9b2add7b9ea413f5cff367c57bad3a93faac1d1d32da27fcbea"
ORIGINS = {"WELL": "real", "SIMULATED": "simulated", "DRAWN": "hand-drawn"}
OPERATIONAL = {
    0: "Open",
    1: "Shut-In",
    2: "Flushing Diesel",
    3: "Flushing Gas",
    4: "Bullheading",
    5: "Closed With Diesel",
    6: "Closed With Gas",
    7: "Restart",
    8: "Depressurization",
}


def main():
    def extra(parser):
        parser.add_argument(
            "--include-generated",
            action="store_true",
            help="Include simulated/hand-drawn instances; default selects only all 1,119 measured instances.",
        )

    args = parse_args(ID, extra=extra)
    raw = fetch(URL, "source-v2.zip", SHA256, args.raw_dir, ID)
    stats = Statistics()
    selected = Counter()
    all_origins = Counter()
    source_observation_counts = Counter()
    with zipfile.ZipFile(raw) as archive:
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read_string(archive.read("dataset.ini").decode())
        assert cfg["VERSION"]["DATASET"] == "2.0.0"
        descriptions = dict(cfg["PARQUET_FILE_PROPERTIES"])
        channels = [c for c in descriptions if c not in ["timestamp", "class", "state"]]
        assert len(channels) == 27
        event_names = {
            int(cfg[section]["LABEL"]): cfg[section]["DESCRIPTION"]
            for section in map(
                str.strip, cfg["EVENTS"]["NAMES"].replace("\n", "").split(",")
            )
            if section
        }
        classes = {
            **event_names,
            **{
                100 + i: f"transient toward {name}"
                for i, name in event_names.items()
                if i
            },
        }
        spec = DatasetSpec(
            id=ID,
            task="cpd",
            channels=channels,
            configs={"default": channels},
            sampling_rate_hz=1,
            time_column=("t_timestamp", pa.timestamp("ns")),
            label_columns={"label_class": pa.int16(), "label_state": pa.int16()},
            meta_columns={
                "source_origin": pa.string(),
                "well_id": pa.string(),
                "event_type_source": pa.int16(),
                "source_file": pa.string(),
                "signal_nan_share": pa.float64(),
                "n_channels_with_data": pa.int32(),
                "non_unit_timestamp_steps": pa.int64(),
            },
        )
        files = sorted(n for n in archive.namelist() if n.endswith(".parquet"))
        for name in files:
            origin = ORIGINS[Path(name).stem.split("_")[0].split("-")[0]]
            all_origins[origin] += 1
            source_observation_counts[origin] += pq.ParquetFile(
                io.BytesIO(archive.read(name))
            ).metadata.num_rows
        assert all_origins == {"real": 1119, "simulated": 1089, "hand-drawn": 20}
        with DatasetWriter(args.out_dir, spec) as writer:
            for name in files:
                stem = Path(name).stem
                origin = ORIGINS[stem.split("_")[0].split("-")[0]]
                if origin != "real" and not args.include_generated:
                    continue
                data = pq.read_table(io.BytesIO(archive.read(name))).to_pandas()
                assert set(data.columns) == set(channels) | {"class", "state"}
                time = data.index.to_numpy(dtype="datetime64[ns]")
                assert not np.isnat(time).any()
                values = data[channels].to_numpy(dtype=np.float32, na_value=np.nan)
                labels = {}
                for source, allowed in [("class", classes), ("state", OPERATIONAL)]:
                    y = data[source].to_numpy(dtype=np.int16, na_value=-1)
                    known = data[source].notna().to_numpy()
                    assert np.equal(data[source][known].astype(float), y[known]).all()
                    assert set(np.unique(y)) <= set(allowed) | {-1}
                    labels["label_" + source] = y
                event = int(Path(name).parent.name)
                sid = f"{event}/{stem}"
                writer.add_series(
                    sid,
                    {c: values[:, i] for i, c in enumerate(channels)},
                    labels=labels,
                    time=time,
                    meta={
                        "source_origin": origin,
                        "well_id": stem.split("_")[0] if origin == "real" else None,
                        "event_type_source": event,
                        "source_file": name,
                        "signal_nan_share": float(np.isnan(values).mean()),
                        "n_channels_with_data": int(
                            np.sum(~np.isnan(values).all(axis=0))
                        ),
                        "non_unit_timestamp_steps": int(
                            np.sum(np.diff(time) != np.timedelta64(1, "s"))
                        ),
                    },
                )
                stats.add(sid, labels)
                selected[origin] += 1
                print(sid, len(data), origin, flush=True)
                del data, values, labels, time
    finish(
        args,
        spec,
        writer,
        stats,
        title="3W Dataset 2.0.0 (measured instances by default)",
        source="https://doi.org/10.6084/m9.figshare.29205836.v1",
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description=f"3W v2.0.0: {dict(selected)} instances, all 27 original channels and independent event-class/operational-state label tracks at 1 Hz.",
        collection="Measured offshore-well records released by Petrobras. Provider interpolated PIMS measurements to 1 Hz before release. Default selects all 1,119 measured instances; simulated and hand-drawn origins are excluded unless explicitly requested.",
        annotation="Preserve both expert-labelled tracks: class 0=normal, 1..9=steady undesirable event, 101..109=transient; operational state codes 0..8 as primary Table 5. Code 0 means Open in state track and normal operation in class track: both ordinary states, not null. Provider defines NaN as Unknown for either track: convert only these missing labels to -1. Validators adjudicate source labels; separate independent annotator tracks are not provided.",
        conversion="Read one archived Parquet instance at a time, without extraction to a global raw table. All 27 source channels cast to float32; original timestamp index, rows, signal NaNs, frozen values and outliers retained. No interpolation, imputation, normalisation or artificial concatenation. Preserve folder event type, source filename, origin and pseudonymous well ID. Optional --include-generated adds simulated/hand-drawn rows with explicit source_origin and RAI synthetic flag; use a separate --out directory to retain the measured build. Archive verified with primary MD5 on acquisition and pinned SHA256 on every build.",
        limitations="Measured instances contain extensive missing/frozen channels. Default class track has no state recurrence in measured data and is classified CPD; operational-status recurrence is reported separately and supports SD only in a small subset. Valve channels can directly inform operational status, so channel selection affects difficulty. Generated origins must not be silently mixed into measured evaluation. Source 1-Hz interpolation is not new independent measurement.",
        biases="One operator, selected offshore-well events and expert curation; generalisation to other equipment or prevalence requires assessment.",
        personal="Pseudonymous well identifiers, machine signals and timestamps; no direct personal or geographic identifiers added.",
        citation="Vargas, R. (2025). 3W Dataset 2.0.0. Figshare, version 1. https://doi.org/10.6084/m9.figshare.29205836.v1. Vargas et al. (2026), Scientific Data 13, 949. https://doi.org/10.1038/s41597-026-07225-z.",
        creators=["Vargas, Ricardo"],
        date_published="2025-05-31",
        synthetic=args.include_generated,
        info={
            "label_origin": "expert",
            "source_version": "2.0.0",
            "source_origin_counts": dict(all_origins),
            "source_origin_sample_counts": dict(source_observation_counts),
            "track_tasks": {"label_class": "cpd", "label_state": "sd"},
            "selected_origin_counts": dict(selected),
            "include_generated": args.include_generated,
            "state_names": {"label_class": classes, "label_state": OPERATIONAL},
            "label_descriptions": {
                "label_class": "Normal, transient and steady undesirable event class.",
                "label_state": "Well operational status, separate from event class.",
            },
            "source_channel_descriptions": {c: descriptions[c] for c in channels},
            "reference_doi": "https://doi.org/10.1038/s41597-026-07225-z",
            "source_null_label_policy": "Only missing NaN labels -> -1; class 0 and operational state 0 remain ordinary states.",
        },
    )


if __name__ == "__main__":
    main()
