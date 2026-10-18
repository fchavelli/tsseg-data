"""Build the 50 manually annotated, measured RIPE Atlas RTT traces."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import ChangePointStatistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "rtt-ripe-atlas-labelled"
REVISION = "d090227f1e6deb158ac0d5c06966318d5e163d83"
SOURCE = "https://github.com/WenqinSHAO/rtt"
URL = f"https://codeload.github.com/WenqinSHAO/rtt/zip/{REVISION}"
SHA256 = "4c653cf6f840bdf85816c77b1b5b73de01cb36ceebbe54a1ebca15119fac275b"
RIPE_TERMS = (
    "https://www.ripe.net/about-us/legal/ripe-atlas-service-terms-and-conditions/"
)


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=["rtt_ms"],
        configs={"default": ["rtt_ms"]},
        sampling_rate_hz=None,
        channel_type=pa.float64(),
        time_column=("timestamp", pa.timestamp("s")),
        cp_annotators=["source"],
        meta_columns={
            "source_file": pa.string(),
            "timestamp_format": pa.string(),
            "backward_steps": pa.int32(),
            "max_gap_s": pa.int32(),
        },
    )
    stats = ChangePointStatistics()
    time_formats = {}
    backward_steps = 0
    max_gap = 0
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        files = sorted(
            (
                name
                for name in archive.namelist()
                if "/dataset/real_trace_labelled/" in name and name.endswith(".csv")
            ),
            key=lambda name: int(Path(name).stem),
        )
        assert len(files) == 50, len(files)
        for name in files:
            frame = pd.read_csv(archive.open(name), sep=";")
            assert list(frame) == ["epoch", "rtt", "cp"], name
            sid = Path(name).stem
            assert frame.cp.isin([0, 1]).all(), sid
            values = frame.rtt.to_numpy(dtype=np.float64)
            assert np.isfinite(values).all(), sid
            source_time = frame.epoch.iloc[0]
            time_format = (
                "%Y-%m-%d %H:%M:%S" if source_time[4] == "-" else "%d/%m/%Y %H:%M"
            )
            time = pd.to_datetime(frame.epoch, format=time_format).to_numpy(
                dtype="datetime64[s]"
            )
            steps = np.diff(time.astype(np.int64))
            n_backward = int(np.count_nonzero(steps < 0))
            gap = int(steps.max())
            backward_steps += n_backward
            max_gap = max(max_gap, gap)
            time_formats[time_format] = time_formats.get(time_format, 0) + 1
            points = np.flatnonzero(frame.cp.to_numpy() == 1).astype(np.int32)
            assert np.all((points > 0) & (points < len(values))), sid
            cps = {"source": (points, ["manual_change"] * len(points))}
            writer.add_series(
                sid,
                {"rtt_ms": values},
                time=time,
                cps=cps,
                annotators=["source"],
                meta={
                    "source_file": name.split("/dataset/", 1)[1],
                    "timestamp_format": time_format,
                    "backward_steps": n_backward,
                    "max_gap_s": gap,
                },
            )
            stats.add(sid, len(values), {"source": points})

    assert stats.summary()["cp_annotations"]["source"]["change_points"] == 1047
    finish(
        args,
        spec,
        writer,
        stats,
        title="RIPE Atlas RTT manually labelled change points",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="LicenseRef-RIPE-Atlas-Terms",
        license_url=RIPE_TERMS,
        license_evidence=RIPE_TERMS,
        description="Fifty measured RIPE Atlas round-trip-time traces with 1,047 manually marked change points. Only the real_trace_labelled directory is converted.",
        collection="The authors collected 50 real RTT traces from RIPE Atlas measurements in 2016. The native trace order, RTT values in milliseconds and source timestamps are retained.",
        annotation="The source CSV cp column marks the observed row with 1 for a manually labelled change and 0 otherwise. Its positive row indices become cps_source. The author reports 1,047 changes across 50 traces. No semantic state labels are supplied. Artificial ground-truth and artificially labelled traces in the same archive are excluded.",
        conversion="Read only dataset/real_trace_labelled/*.csv from the pinned source archive; preserve RTT as float64, exact source row order and CP row indices. Parse the two source timestamp formats explicitly, retaining timezone-naive wall times without claiming UTC. Keep measured timestamp reversals and gaps; do not resample or interpolate. Native measurements are near four minutes apart, but the grid is irregular.",
        limitations="One RTT channel per trace and one released annotation track, without per-person annotation identities or agreement data. The source contains four small timestamp reversals and gaps up to 18,003 seconds; timezone is unspecified. CPs mark rows rather than exact physical onset. The RIPE NCC terms restrict commercial use of RIPE Atlas data; this builder is source-only pending redistribution clarification.",
        biases="The authors selected 50 RIPE Atlas traces of various forms; the probe and network coverage is not a representative sample of all Internet paths.",
        personal="No participant data are imported. RTT traces and source timestamps may reflect network infrastructure; no probe location or IP address is added.",
        citation="Shao, W., Rougier, J.-L., Paris, S., Devienne, F., and Viste, P. (2017). One-to-One Matching of RTT and Path Changes. ITC 29. arXiv:1709.04819.",
        creators=[
            "Shao, Wenqin",
            "Rougier, Jean-Louis",
            "Paris, Stéphane",
            "Devienne, François",
            "Viste, Philippe",
        ],
        date_published="2017",
        info={
            "hf_license": "other",
            "source_revision": REVISION,
            "license_scope": "The repository's MIT licence covers its code and documentation; RIPE Atlas measurements also follow the RIPE NCC service terms (version 3.5, article 4.5). Commercial use needs prior permission. Conservatively tier C/source-only; do not redistribute the converted data without clarification.",
            "rehosting_allowed": False,
            "label_origin": "human",
            "default_cpd": "cps_source",
            "cp_convention": "Zero-based index of the source CSV row marked cp=1; first sample of a new segment.",
            "time_description": "Timezone-naive source timestamps in two original formats; preserved as timestamp[s] without asserting UTC.",
            "time_formats": time_formats,
            "timestamp_backward_steps": backward_steps,
            "timestamp_max_gap_s": max_gap,
            "units": {"rtt_ms": "milliseconds"},
            "use_cases": "Offline change point detection against manually marked RTT changes; semantic state detection is unsupported.",
        },
    )


if __name__ == "__main__":
    main()
