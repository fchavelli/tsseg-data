"""Build every Daphnet FoG run; out-of-protocol source code 0 maps to -1."""

from __future__ import annotations

import re
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

ID = "daphnet-fog"
SOURCE = "https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait"
URL = "https://archive.ics.uci.edu/static/public/245/daphnet+freezing+of+gait.zip"
SHA256 = "27c6173b3acee75a69284903756b9011a00766c1bbb743c37fc884c5dbc39399"
CHANNELS = [
    f"{site}_{axis}"
    for site in ("ankle", "thigh", "trunk")
    for axis in ("forward", "vertical", "lateral")
]


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=64,
        time_column=("t_milliseconds", pa.int64()),
        label_columns={"label_freeze": pa.int16()},
        meta_columns={
            "subject": pa.string(),
            "run": pa.string(),
            "dt_ms_max": pa.int64(),
        },
    )
    stats = Statistics()
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(
            n for n in archive.namelist() if re.search(r"/S\d+R\d+\.txt$", n)
        )
        assert len(files) == 17
        for name in files:
            with archive.open(name) as stream:
                x = pd.read_csv(
                    stream, sep=r"\s+", header=None, dtype=np.int64
                ).to_numpy()
            assert x.shape[1] == 11 and set(np.unique(x[:, -1])) <= {0, 1, 2}
            y = x[:, -1].astype(np.int16)
            y[y == 0] = -1
            assert np.all(np.diff(x[:, 0]) > 0)
            sid = Path(name).stem
            subject, run = sid.split("R")
            labels = {"label_freeze": y}
            writer.add_series(
                sid,
                {c: x[:, i + 1].astype(np.float32) for i, c in enumerate(CHANNELS)},
                labels=labels,
                time=x[:, 0],
                meta={
                    "subject": subject,
                    "run": run,
                    "dt_ms_max": int(np.diff(x[:, 0]).max()),
                },
            )
            stats.add(sid, labels)
            print(sid, len(y), flush=True)
    finish(
        args,
        spec,
        writer,
        stats,
        title="Daphnet Freezing of Gait (all 17 runs)",
        source="https://doi.org/10.24432/C56K78",
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        description="All 17 source runs from ten Parkinson disease patients; nine acceleration axes at 64 Hz with freeze/non-freeze labels and out-of-protocol masks.",
        collection="Three wireless triaxial accelerometers at ankle, thigh and trunk/hip capture laboratory walking, turning and daily-living tasks at 64 Hz in Tel Aviv in 2008. Provider reports ethics approval and Helsinki compliance.",
        annotation="Video analysis labels 1=experiment/no freeze (standing, walking or turning) and 2=freeze. Source code 0 explicitly means outside the experiment (sensor setup, debriefing): map to -1, retain its samples, and never score it as a null state. Provider notes onset jitter of a few hundred milliseconds.",
        conversion="One series per original run, all nine accelerometer axes in mg, cast to float32; retain source millisecond timestamps and all rows. No filtering, interpolation or joins. Seventeen actual sensor logs, not the 29 total archive entries. Keep runs separate to avoid synthetic joins; group all runs by subject during evaluation as the source recommends.",
        limitations="Small disease-specific cohort and protocol selected to provoke freezing. Subjects 4 and 10 have no freeze events. Source release is a reduced version used in the cited analyses. Annotation boundary jitter and rounded millisecond timestamps limit precision.",
        biases="Patients with Parkinson disease in a controlled clinical setting; not representative of general gait or everyday prevalence.",
        personal="Pseudonymous patient/run IDs and clinical movement signals retained; no source video or direct identifiers included.",
        citation="Roggen, D., Plotnik, M., and Hausdorff, J. (2010). Daphnet Freezing of Gait. UCI. https://doi.org/10.24432/C56K78. Bächlin et al. (2010), Wearable Assistant for Parkinson's Disease Patients With the Freezing of Gait Symptom, IEEE TITB 14(2), 436–446.",
        creators=["Roggen, Daniel", "Plotnik, Meir", "Hausdorff, Jeff"],
        date_published="2013-03-06",
        info={
            "state_names": {"label_freeze": {1: "no freeze", 2: "freeze"}},
            "source_zero_label_policy": "0 outside experiment -> -1",
            "label_origin": "human",
        },
    )


if __name__ == "__main__":
    main()
