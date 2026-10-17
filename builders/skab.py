"""Build SKAB v0.9 with both binary anomalies and original CP markers."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "skab"
REVISION = "b2c0d46c2971dcbfe71e26087b6d231998bb91c2"
SOURCE = "https://github.com/waico/SKAB"
URL = f"https://codeload.github.com/waico/SKAB/zip/{REVISION}"
SHA256 = "45ac11b460e495ba2c1301c3f8e871b688b5ecfa6cd0770b4225594fe45efc80"
CHANNELS = {
    "accelerometer_1_rms": "Accelerometer1RMS",
    "accelerometer_2_rms": "Accelerometer2RMS",
    "current": "Current",
    "pressure": "Pressure",
    "temperature": "Temperature",
    "thermocouple": "Thermocouple",
    "voltage": "Voltage",
    "flow_rate_rms": "Volume Flow RateRMS",
}


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=list(CHANNELS),
        configs={"default": list(CHANNELS)},
        sampling_rate_hz=1,
        time_column=("timestamp_s", pa.int64()),
        label_columns={"label_anomaly": pa.int16()},
        cp_annotators=["source"],
        meta_columns={
            "source_file": pa.string(),
            "experiment_group": pa.string(),
            "dt_s_max": pa.int64(),
        },
    )
    stats = Statistics()
    cp_counts = {}
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(
            n
            for n in archive.namelist()
            if "/data/" in n and n.endswith(".csv") and "/anomaly-free/" not in n
        )
        assert len(files) == 34
        for name in files:
            frame = pd.read_csv(archive.open(name), sep=";")
            assert set(frame.anomaly.unique()) <= {0, 1}
            assert set(frame.changepoint.unique()) <= {0, 1}
            y = frame.anomaly.to_numpy(dtype=np.int16)
            cps = np.flatnonzero(frame.changepoint.to_numpy() == 1)
            assert np.all((cps > 0) & (cps < len(y)))
            t = (
                pd.to_datetime(frame.datetime)
                .to_numpy(dtype="datetime64[s]")
                .astype(np.int64)
            )
            assert np.all(np.diff(t) > 0)
            sid = name.split("/data/")[1][:-4]
            labels = {"label_anomaly": y}
            writer.add_series(
                sid,
                {
                    c: frame[source].to_numpy(dtype=np.float32)
                    for c, source in CHANNELS.items()
                },
                labels=labels,
                annotators=["source"],
                time=t,
                cps={"source": (cps, ["collective_anomaly"] * len(cps))},
                meta={
                    "source_file": name.split("/", 1)[1],
                    "experiment_group": sid.split("/")[0],
                    "dt_s_max": int(np.diff(t).max()),
                },
            )
            stats.add(sid, labels)
            cp_counts[sid] = len(cps)
    finish(
        args,
        spec,
        writer,
        stats,
        title="Skoltech Anomaly Benchmark (SKAB v0.9)",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="GPL-3.0",
        license_url="https://www.gnu.org/licenses/gpl-3.0.html",
        license_evidence=f"{SOURCE}/blob/{REVISION}/LICENSE",
        description="34 sensor experiments with injected collective anomalies, binary "
        "anomaly labels and every original changepoint marker (up to four per experiment).",
        collection="Eight sensors on a recirculating water testbed; controlled anomaly "
        "experiments in valve1, valve2 and other groups.",
        annotation="label_anomaly retains source anomaly (0 normal, 1 anomalous). "
        "cps_source retains every row marked changepoint=1, including transition "
        "boundaries omitted by the binary anomaly track. Markers are not separate "
        "human annotators. Some experiments have only two or three markers; "
        "no missing marker or semantic phase is invented. There is no null class.",
        conversion="Read 34 labelled source CSVs; exclude the separate anomaly-free "
        "training recording which contains no label columns. Cast sensors to "
        "float32 without normalisation or interpolation. Preserve source datetime "
        "as Unix seconds (source timezone unspecified). Sampling nominally 1 Hz; "
        "maximum timestamp gap is recorded per series. Original changepoints "
        "are 0-based positions, independent of changes in the anomaly track.",
        limitations="One collective anomaly per experiment; binary states provide limited "
        "state detection complexity. Gradual drifts and abrupt faults coexist. "
        "Experiments do not all contain four source CP markers.",
        biases="One laboratory water-loop testbed and protocol-induced anomalies.",
        personal="No human participants or personal attributes.",
        citation="Katser, Iurii D. and Kozitsin, Vyacheslav O. (2020). Skoltech Anomaly "
        "Benchmark (SKAB). https://doi.org/10.34740/KAGGLE/DSV/1693952",
        creators=["Katser, Iurii D.", "Kozitsin, Vyacheslav O."],
        date_published="2020",
        info={
            "reference_doi": "https://doi.org/10.34740/KAGGLE/DSV/1693952",
            "source_revision": REVISION,
            "label_origin": "protocol",
            "state_names": {"label_anomaly": {"0": "normal", "1": "anomaly"}},
            "cp_counts_source": cp_counts,
            "source_columns": CHANNELS,
            "time_description": "Source datetime converted to Unix seconds; timezone unspecified.",
            "default_cpd": "cps_source",
        },
    )


if __name__ == "__main__":
    main()
