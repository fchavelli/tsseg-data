"""Build all CNC mill experiments, preserving every source process-state string."""

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

ID = "cnc-mill-umich"
SOURCE = "https://www.kaggle.com/datasets/shasun/tool-wear-detection-in-cnc-mill"
URL = "https://www.kaggle.com/api/v1/datasets/download/shasun/tool-wear-detection-in-cnc-mill?datasetVersionNumber=4"
SHA256 = "28d0fc48295e1872d012dae32c413dc415453663d46292f3a952399842265cf0"


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source-v4.zip", SHA256, args.raw_dir, ID)
    stats = Statistics()
    with zipfile.ZipFile(raw) as archive:
        files = sorted(
            n
            for n in archive.namelist()
            if n.startswith("experiment_") and n.endswith(".csv")
        )
        assert len(files) == 18
        frames = {}
        for name in files:
            with archive.open(name) as stream:
                frames[name] = pd.read_csv(stream)
        channels = [c for c in frames[files[0]].columns if c != "Machining_Process"]
        assert len(channels) == 47
        states = sorted(
            set().union(*(set(d.Machining_Process) for d in frames.values()))
        )
        codes = {name: i for i, name in enumerate(states)}
        with archive.open("train.csv") as stream:
            experiments = pd.read_csv(stream).set_index("No")
        spec = DatasetSpec(
            id=ID,
            task="sd",
            channels=channels,
            configs={"default": channels},
            sampling_rate_hz=10,
            label_columns={"label_process": pa.int16()},
            meta_columns={
                "experiment": pa.int16(),
                "material": pa.string(),
                "feedrate_mm_s": pa.float64(),
                "clamp_pressure_bar": pa.float64(),
                "tool_condition": pa.string(),
                "machining_finalized": pa.string(),
                "passed_visual_inspection": pa.string(),
            },
        )
        with DatasetWriter(args.out_dir, spec) as writer:
            for name, data in frames.items():
                assert data.columns.tolist() == channels + ["Machining_Process"]
                assert not data.isna().any().any()
                number = int(Path(name).stem.split("_")[1])
                row = experiments.loc[number]
                values = data[channels].to_numpy(dtype=np.float32)
                assert np.isfinite(values).all()
                labels = {
                    "label_process": data.Machining_Process.map(codes).to_numpy(
                        dtype=np.int16
                    )
                }
                sid = Path(name).stem
                writer.add_series(
                    sid,
                    {c: values[:, i] for i, c in enumerate(channels)},
                    labels=labels,
                    meta={
                        "experiment": number,
                        "material": row.material,
                        "feedrate_mm_s": float(row.feedrate),
                        "clamp_pressure_bar": float(row.clamp_pressure),
                        "tool_condition": row.tool_condition,
                        "machining_finalized": row.machining_finalized,
                        "passed_visual_inspection": None
                        if pd.isna(row.passed_visual_inspection)
                        else row.passed_visual_inspection,
                    },
                )
                stats.add(sid, labels)
                print(sid, len(data), flush=True)
    finish(
        args,
        spec,
        writer,
        stats,
        title="University of Michigan CNC Mill Tool Wear (all experiments)",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        license_evidence=SOURCE,
        description="All 18 SMART-lab CNC machining experiments with 47 original numeric channels and exact process-state labels at 10 Hz.",
        collection="University of Michigan SMART testbed CNC mill machines wax blocks with an S-shaped pattern, varying tool condition, feed rate and clamp pressure. Rockwell Cloud Collector Agent Elastic records four motors (X/Y/Z/spindle) every 100 ms. Primary deposit by Sharon Sun, Kaggle version 4.",
        annotation="Machining_Process is the provider-defined per-sample operation label. Preserve all eleven exact strings, including distinct End and end spellings, Starting, Prep and Repositioning; no silent case alias. These are scored protocol states, not null/missing labels. Tool condition and inspection outcomes are experiment-level metadata, not dense segmentation ground truth. Missing visual inspection when machining was not completed remains metadata null.",
        conversion="One series per original experiment CSV; retain every row and all 47 numeric columns with source names, cast to float32 without filtering, interpolation or normalisation. No physical timestamp column is supplied; use documented 100-ms sampling interval without inventing timestamps. Preserve source train.csv conditions in index metadata. Both full and early-stopped experiments retained; source image excluded.",
        limitations="Eighteen short controlled experiments on wax, not long industrial operation. Provider flags inaccurate variables when feedrate=50, X position=198 or program number is nonzero; original values retained, no repair. Program/sequence/control channels may reveal the machining phase directly: assess sensitivity excluding these leakage-prone features. S1_OutputPower units are contradictory in README; no inferred unit correction. End/end spellings remain distinct until semantic equivalence is verified.",
        biases="One machine, one material and scripted tool paths; worn/unworn and clamping variations do not establish generalisation to other machining tasks.",
        personal="Industrial machine signals and experiment conditions; no participant or direct personal data.",
        citation="Sun, Sharon (2018). CNC Mill Tool Wear, University of Michigan SMART testbed. Kaggle, version 4. https://www.kaggle.com/datasets/shasun/tool-wear-detection-in-cnc-mill.",
        creators=["Sun, Sharon"],
        date_published="2018-04-06",
        info={
            "label_origin": "protocol",
            "state_names": {"label_process": dict(enumerate(states))},
            "source_version": 4,
            "source_columns": channels,
            "source_label_case_policy": "Exact strings, including End and end, retained separately.",
            "potential_label_leakage_channels": [
                c for c in channels if c.startswith("M1_")
            ],
            "source_known_quality_conditions": [
                "M1_CURRENT_FEEDRATE == 50",
                "X1_ActualPosition == 198",
                "M1_CURRENT_PROGRAM_NUMBER != 0",
            ],
        },
    )


if __name__ == "__main__":
    main()
