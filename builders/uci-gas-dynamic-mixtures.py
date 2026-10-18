"""Build both gas-mixture recordings locally; conflicting source rights block rehosting."""

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

ID = "uci-gas-dynamic-mixtures"
SOURCE = "https://archive.ics.uci.edu/dataset/322/gas+sensor+array+under+dynamic+gas+mixtures"
URL = "https://archive.ics.uci.edu/static/public/322/gas+sensor+array+under+dynamic+gas+mixtures.zip"
SHA256 = "8b6323b801363e11343ba1a5a7718e76666b715e753b3a40dbdfd1838d953fe7"
TYPES = [
    "TGS2602",
    "TGS2602",
    "TGS2600",
    "TGS2600",
    "TGS2610",
    "TGS2610",
    "TGS2620",
    "TGS2620",
] * 2
CHANNELS = [f"sensor_{i:02d}_{kind}" for i, kind in enumerate(TYPES, 1)]
SCOPE = "UCI licence footer declares CC BY 4.0, while the same primary description restricts the data to research and explicitly excludes commercial use. Conflicting primary rights: conservatively tier C/source-only, no rehosting until clarified."


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=100,
        time_column=("t_seconds", pa.float64()),
        label_columns={"label_mixture": pa.int32()},
        meta_columns={
            "other_gas": pa.string(),
            "source_file": pa.string(),
            "dt_s_max": pa.float64(),
            "duplicate_timestamp_steps": pa.int64(),
        },
    )
    stats = Statistics()
    state_rows = []
    state_names = {}
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(
            n
            for n in archive.namelist()
            if n.endswith(".txt")
            and Path(n).stem in ["ethylene_CO", "ethylene_methane"]
        )
        assert len(files) == 2
        for name in files:
            with archive.open(name) as stream:
                x = pd.read_csv(
                    stream, sep=r"\s+", header=None, skiprows=1, dtype=np.float64
                ).to_numpy()
            assert x.shape[1] == 19 and np.isfinite(x).all()
            assert np.all(np.diff(x[:, 0]) >= 0)
            pairs, codes = np.unique(x[:, 1:3], axis=0, return_inverse=True)
            offset = len(state_rows)
            y = codes.astype(np.int32) + offset
            sid = Path(name).stem
            gas = "CO" if sid.endswith("_CO") else "methane"
            for i, (other, ethylene) in enumerate(pairs):
                code = offset + i
                state_rows.append(
                    {
                        "state": code,
                        "mixture": sid,
                        "other_gas": gas,
                        "other_gas_ppm": float(other),
                        "ethylene_ppm": float(ethylene),
                    }
                )
                state_names[code] = (
                    f"{sid}: {gas}={other:g} ppm, ethylene={ethylene:g} ppm"
                )
            labels = {"label_mixture": y}
            writer.add_series(
                sid,
                {c: x[:, i + 3].astype(np.float32) for i, c in enumerate(CHANNELS)},
                labels=labels,
                time=x[:, 0],
                meta={
                    "other_gas": gas,
                    "source_file": name,
                    "dt_s_max": float(np.diff(x[:, 0]).max()),
                    "duplicate_timestamp_steps": int(np.sum(np.diff(x[:, 0]) == 0)),
                },
            )
            stats.add(sid, labels)
            print(sid, len(y), len(pairs), flush=True)
            del x, y, codes, pairs
    pq.write_table(
        pa.Table.from_pylist(state_rows),
        args.out_dir / "mixture_states.parquet",
        compression="zstd",
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Gas sensor array under dynamic gas mixtures (source-only)",
        source="https://doi.org/10.24432/C5WP4C",
        sha256=SHA256,
        license_spdx="LicenseRef-UCI-Gas-Research-Terms",
        license_url=SOURCE,
        license_evidence=SOURCE,
        description="Both complete measured 16-sensor recordings at 100 Hz; reversible joint concentration-setpoint labels, locally built only because source licence terms conflict.",
        collection="Sixteen Figaro chemical sensors of four types record controlled ethylene/CO and ethylene/methane exposures continuously for approximately twelve hours each at UC San Diego. Native sampling is 100 Hz.",
        annotation="Ground truth is the commanded concentration pair, not a prediction of the delayed sensor response. Exact source setpoint pairs become categorical joint states, scoped to mixture identity. Both concentrations zero denotes a real zero-exposure protocol state, not null or missing. Every original concentration pair is recoverable through mixture_states.parquet; no hand-chosen CPs or discretisation thresholds.",
        conversion="All source rows, original centisecond timestamps (including duplicates/gaps) and all sixteen sensor channels retained; signals cast to float32 without filtering/resampling. Source columns 2 and 3 are setpoints used only as labels, not predictor channels. Preserve native sensor readings; do not apply the optional source resistance conversion. No artificial splitting or concatenation. Archive SHA256 pinned; exact setpoint levels retained as float64 in auxiliary.",
        limitations="Two long laboratory experiments and a fixed sensor array; ground truth measures exposure commands and precedes slow physical sensor response. Repeated mixture states may be dominated by predefined pure-gas/zero-exposure patterns. Conflicting research-only/non-commercial description and CC BY footer require rights clarification before redistribution.",
        biases="Controlled gas-delivery platform, selected concentration ranges and repeated sensor types; field deployment and other analytes are not represented.",
        personal="Chemical sensor measurements and commanded exposure levels; no participant data.",
        citation="Fonollosa, J. (2015). Gas sensor array under dynamic gas mixtures. UCI Machine Learning Repository. https://doi.org/10.24432/C5WP4C. Fonollosa et al. (2015), Reservoir Computing compensates slow response of chemosensor arrays exposed to fast varying gas concentrations in continuous monitoring, Sensors and Actuators B 215.",
        creators=["Fonollosa, Jordi"],
        date_published="2015-03-19",
        info={
            "hf_license": "other",
            "license_scope": SCOPE,
            "rehosting_allowed": False,
            "license_tier": "C",
            "label_origin": "protocol",
            "state_names": {"label_mixture": state_names},
            "sensor_types_in_source_order": TYPES,
            "sampling": "Nominal 100 Hz; source centisecond timestamps contain duplicate steps and gaps, retained unchanged.",
            "setpoint_columns_in_source_order": ["other_gas_ppm", "ethylene_ppm"],
            "auxiliary": {
                "mixture_states.parquet": "Reversible mapping from categorical state to mixture identity and exact float64 commanded concentrations (ppm)."
            },
        },
    )


if __name__ == "__main__":
    main()
