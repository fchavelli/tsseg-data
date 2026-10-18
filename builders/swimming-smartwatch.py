"""Build native 30-Hz processed swimming sessions, without redistribution rights."""

from __future__ import annotations

import sys
import zipfile
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

ID = "swimming-smartwatch"
SOURCE = "https://github.com/brunnergino/swimming-recognition-lap-counting"
REVISION = "468ee355675b51fb3b9ad9d992ef7b807ae1af4f"
SHA256 = "d607802935eaca9504082c053f6d6f3308b0cf4c696fc47375cb4a4fbb395c12"
URL = f"https://codeload.github.com/brunnergino/swimming-recognition-lap-counting/zip/{REVISION}"
NATIVE = [
    f"{sensor}_{axis}" for sensor in ["ACC", "GYRO", "MAG"] for axis in range(3)
] + ["PRESS", "LIGHT"]
DERIVED = [
    f"{sensor}_{axes}"
    for sensor in ["ACC", "GYRO", "MAG"]
    for axes in ["012", "01", "02", "12"]
]
STATES = {
    0: "null_other_activity_including_rest",
    1: "freestyle",
    2: "breaststroke",
    3: "backstroke",
    4: "butterfly",
    5: "turn",
    6: "kick",
}
CONSTANTS_URL = "https://drive.usercontent.google.com/download?id=19ncqFANBR2aCAxOryMPyEVjnhPBYy9j8&export=download&confirm=t"
CONSTANTS_SHA = "e92a4d38b0a9c244fd0d66fbc98cc0d5b6119673f61385dd460e20e88f2f903f"


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    constants = fetch(
        CONSTANTS_URL, "constants-source.txt", CONSTANTS_SHA, args.raw_dir, ID
    )
    assert (
        "-1: 'Unknown'" in constants.read_text()
        and "6: 'Kick'" in constants.read_text()
    )
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=NATIVE + DERIVED,
        configs={"default": NATIVE, "full": NATIVE + DERIVED},
        sampling_rate_hz=30,
        time_column=("uptime_ns", pa.float64()),
        label_columns={"label_activity": pa.int32()},
        meta_columns={
            "swimmer_id": pa.string(),
            "source_file": pa.string(),
            "filename_predominant_style": pa.string(),
        },
    )
    stats = Statistics()
    nans = {c: 0 for c in spec.channels}
    source_rows = []
    swimmers = set()
    backward = 0
    duplicate = 0
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(
            n
            for n in archive.namelist()
            if n.endswith(".csv") and "/processed_30hz_relabeled/" in n
        )
        assert len(files) == 206
        for name in files:
            path = Path(name)
            swimmer = path.parent.name
            swimmers.add(swimmer)
            sid = f"swimmer-{swimmer}_{path.stem}"
            frame = pd.read_csv(archive.open(name))
            assert list(frame) == [
                "Unnamed: 0",
                "timestamp",
                *NATIVE,
                "label",
                *DERIVED,
            ], name
            assert frame.label.isin([-1, *STATES]).all(), name
            time = frame.timestamp.to_numpy(dtype=np.float64)
            assert np.isfinite(time).all()
            steps = np.diff(time)
            backward += int(np.count_nonzero(steps < 0))
            duplicate += int(np.count_nonzero(steps == 0))
            labels = {"label_activity": frame.label.to_numpy(dtype=np.int32)}
            signal = {c: frame[c].to_numpy(dtype=np.float32) for c in spec.channels}
            for c, values in signal.items():
                nans[c] += int(np.count_nonzero(~np.isfinite(values)))
            writer.add_series(
                sid,
                signal,
                labels=labels,
                time=time,
                meta={
                    "swimmer_id": swimmer,
                    "source_file": name.split("/data/", 1)[1],
                    "filename_predominant_style": path.stem.rsplit("_", 1)[0],
                },
            )
            stats.add(sid, labels)
            source_rows.append(
                {
                    "series_id": sid,
                    "source_row_id": frame.iloc[:, 0].to_numpy(dtype=np.int64).tolist(),
                }
            )
        assert len(swimmers) == 40
        pq.write_table(
            pa.Table.from_pylist(source_rows),
            args.out_dir / "source_rows.parquet",
            compression="zstd",
        )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Smartwatch swimming styles and turns, all processed sessions",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="LicenseRef-Unlicensed",
        license_url=f"{SOURCE}/tree/{REVISION}",
        license_evidence=f"{SOURCE}/tree/{REVISION}",
        description="All 206 processed 30-Hz sessions from 40 swimmers, eleven measured sensor channels and seven native activity states. Default excludes twelve redundant provider-derived norms, which remain in full. Local source-only builder: no source licence grants redistribution.",
        collection="Provider's preprocessed, labelled, resampled 30-Hz smartwatch recordings. Accelerometer, gyroscope and magnetometer xyz, ambient pressure and light retained. This is the released neural-network training input, not raw device streams.",
        annotation="README defines 0 null (any activity outside the four swim styles, including rest between laps), 1 freestyle, 2 breaststroke, 3 backstroke, 4 butterfly and 5 turn. Primary author-linked code constants define the additional released codes 6 Kick (44,047 samples) and -1 Unknown (77,943 samples). All seven nonnegative codes remain scored states; neither null nor turn means absent ground truth. The paper merged null/turn into transition but this conversion preserves the source distinction. Filename predominant style is metadata, never a substitute for per-sample labels. No independent annotator tracks or agreement statistic are provided.",
        conversion="One native CSV per series, source order and nanoseconds-of-device-uptime timestamps retained. All 11 sensor columns in default; full additionally retains the 12 precomputed L2 norms, without computing new features. Signals float32, timestamp float64 preserving the CSV numeric representation. Original pandas row IDs preserved in auxiliary source_rows.parquet. No further resampling, interpolation, normalization, style merging or session concatenation. Group evaluation by swimmer_id to avoid leakage.",
        limitations="Only provider-processed signals available; raw data, precise annotation uncertainty and annotator identity are absent. Source timestamp is device uptime rather than UTC. No independent clinical, safety or athlete-generalisation validity. Rights unverified: source public availability is not permission to redistribute.",
        biases="Forty swimmers in the provider's protocol; limited devices, pool conditions and styles; long rest/transition periods can dominate metrics.",
        personal="Pseudonymous swimmer IDs and source session filenames with epoch-like numbers retained for provenance; device uptime is retained. Do not attempt re-identification or infer private participant information.",
        citation="Brunner et al. (2019). Swimming Style Recognition and Lane Counting Using a Smartwatch. ISWC 2019. Primary paper link: https://dl.acm.org/citation.cfm?id=3347719.",
        creators=[
            "Gino Brunner",
            "Darya Melnyk",
            "Birkir Sigfusson",
            "Roger Wattenhofer",
        ],
        date_published="2019-11-01",
        null_states={"label_activity": [0, 5]},
        info={
            "hf_license": "other",
            "license_scope": "No LICENSE file or licence grant found in the complete pinned primary repository tree or README on 2026-10-18. Registry MIT attribution is unsupported. Tier C/source-only; no rehosting until author clarification.",
            "rehosting_allowed": False,
            "source_revision": REVISION,
            "primary_label_constants": {"url": CONSTANTS_URL, "sha256": CONSTANTS_SHA},
            "state_names": {"label_activity": STATES},
            "default_label": "label_activity",
            "swimmers": len(swimmers),
            "source_timestamp_backward_steps": backward,
            "source_timestamp_duplicate_steps": duplicate,
            "nonfinite_sensor_values": nans,
            "auxiliary": {
                "source_rows.parquet": "Original per-session pandas row identifiers, one native row list per series."
            },
        },
    )


if __name__ == "__main__":
    main()
