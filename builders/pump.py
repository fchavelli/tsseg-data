"""Build all 400 hydraulic end-of-line testing cycles from the Bosch source."""

from __future__ import annotations

import io
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

ID = "pump"
REVISION = "2e1765e35f37a214b371ebba18b5e66d104fca9f"
SOURCE = "https://github.com/boschresearch/Hydraulic-EoL-Testing"
URL = f"https://codeload.github.com/boschresearch/Hydraulic-EoL-Testing/zip/{REVISION}"
SHA256 = "05d11dfb0f79cd4c45a0a429b75ce110c0dbcd662d90c18f62479963c7e9f14e"


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    channels = [f"sensor_{i}" for i in range(1, 10)]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=channels,
        configs={"default": channels},
        sampling_rate_hz=100,
        time_column=("t_seconds", pa.float64()),
        label_columns={"label_state": pa.int16()},
        meta_columns={
            "source_file": pa.string(),
            "generation": pa.string(),
            "control_version": pa.string(),
            "tsb_seg_subset": pa.bool_(),
        },
    )
    stats = Statistics()
    states = set()
    with zipfile.ZipFile(raw) as archive:
        for member in sorted(n for n in archive.namelist() if n.endswith(".zip")):
            with zipfile.ZipFile(io.BytesIO(archive.read(member))) as cycle:
                csv = next(n for n in cycle.namelist() if n.endswith(".csv"))
                with cycle.open(csv) as stream:
                    values = pd.read_csv(stream, usecols=["State"]).State.to_numpy()
                assert np.all(np.isfinite(values))
                states.update(values.tolist())
    state_codes = sorted(states)
    groups = {}
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        members = sorted(n for n in archive.namelist() if n.endswith(".zip"))
        assert len(members) == 400
        for member in members:
            with zipfile.ZipFile(io.BytesIO(archive.read(member))) as cycle:
                csvs = [n for n in cycle.namelist() if n.endswith(".csv")]
                assert len(csvs) == 1
                with cycle.open(csvs[0]) as stream:
                    frame = pd.read_csv(stream)
            assert list(frame.columns)[:11] == [
                "t",
                *[f"Sensor {i}" for i in range(1, 10)],
                "State",
            ]
            assert all(
                c.startswith("predicted_states") for c in list(frame.columns)[11:]
            )
            y = np.searchsorted(state_codes, frame.State.to_numpy()).astype(np.int16)
            assert np.array_equal(np.asarray(state_codes)[y], frame.State.to_numpy())
            sid = Path(csvs[0]).stem
            _, generation, control, _ = sid.split("_")
            groups[generation + "_" + control] = (
                groups.get(generation + "_" + control, 0) + 1
            )
            t = frame.t.to_numpy()
            assert np.allclose(np.diff(t), 0.01, atol=1e-8)
            labels = {"label_state": y}
            writer.add_series(
                sid,
                {
                    c: frame[f"Sensor {i}"].to_numpy(dtype=np.float32)
                    for i, c in enumerate(channels, 1)
                },
                labels=labels,
                time=t,
                meta={
                    "source_file": member.split("/", 1)[1] + ":" + csvs[0],
                    "generation": generation,
                    "control_version": control,
                    "tsb_seg_subset": generation == "A" and control.startswith("DC"),
                },
            )
            stats.add(sid, labels)
            print(sid, len(y), flush=True)
    finish(
        args,
        spec,
        writer,
        stats,
        title="Hydraulic End-of-Line Testing (PUMP), all cycles",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=f"{SOURCE}/blob/{REVISION}/README.md#license",
        description="All 400 Bosch hydraulic pump testing cycles, nine anonymised sensors "
        "at 100 Hz and dense state labels; includes 280 cycles beyond TSB-SEG.",
        collection="Hydraulic pump end-of-line testing of two generations and three "
        "control types at Bosch; source sensors anonymised and standard-score normalised.",
        annotation="One manual operator annotation (PrecTime); source state codes are "
        "encoded reversibly, including short transitions and special start/end "
        "states. State meanings are confidential; no null-state identity is "
        "inferred from integers. All samples have labels.",
        conversion="Read the 400 nested CSV archives, preserve timestamps in seconds, "
        "cast nine sensor channels to float32. Sorted unique numeric source state codes "
        "(including noninteger 17.5) map to 0-based int16 IDs; state_source_codes reverses "
        "this mapping. Generation B predicted_states columns are excluded as model output. "
        "No interpolation, additional normalisation, smoothing or label merging. "
        "tsb_seg_subset identifies the 120 Generation A DC cycles. State codes "
        "must not be assumed semantically aligned across control types/generations.",
        limitations="Confidential sensor/state semantics; labels include very short "
        "segments and transitions. Source normalisation removes physical units. "
        "The collection includes defective pumps; no defect classification is inferred.",
        biases="One manufacturer and one industrial process family; generation and control "
        "type alter label vocabularies. Samples are testing cycles, not independent plants.",
        personal="No human participant data or personal attributes are included.",
        citation="Gaugel, S. and Reichert, M. (2023). PrecTime: A Deep Learning Architecture "
        "for Precise Time Series Segmentation in Industrial Manufacturing Operations. "
        "https://www.sciencedirect.com/science/article/pii/S0952197623002622",
        creators=["Gaugel, Stefan", "Reichert, Manfred"],
        date_published="2023",
        info={
            "reference_doi": "https://doi.org/10.48550/arXiv.2302.10182",
            "state_names": {
                "label_state": {
                    str(i): f"source state {s:g}" for i, s in enumerate(state_codes)
                }
            },
            "state_source_codes": {"label_state": dict(enumerate(state_codes))},
            "source_revision": REVISION,
            "groups": groups,
            "time_description": "Source time index, seconds.",
            "units": dict.fromkeys(channels, "standard score (source normalisation)"),
        },
    )


if __name__ == "__main__":
    main()
