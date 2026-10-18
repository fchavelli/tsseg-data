"""Read the six original bee trajectories and label0 ground truth, source-only."""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "bee-dance"
SOURCE = "https://sites.cc.gatech.edu/~borg/ijcv_psslds/"
URL = SOURCE + "psslds.zip"
SHA256 = "9b1277fd38026570ecee6c5a5602439b0aae1264185abf41311ad6646387ccb0"
STATES = {0: "turn_left", 1: "turn_right", 2: "waggle"}
CHANNELS = {
    "x_image": "ximage.btf",
    "y_image": "yimage.btf",
    "heading_native": "timage.btf",
}


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "psslds.zip", SHA256, args.raw_dir, ID)
    assert (
        hashlib.md5(raw.read_bytes()).hexdigest() == "039843dc15c72fd5450eeb11c6e5599c"
    )
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=list(CHANNELS),
        configs={"default": list(CHANNELS)},
        channel_type=pa.float64(),
        sampling_rate_hz=None,
        time_column=("source_timestamp", pa.int64()),
        label_columns={"label_behavior": pa.int32()},
        meta_columns={
            "source_sequence": pa.int32(),
            "source_directory": pa.string(),
            "timestamp_first": pa.int64(),
            "timestamp_step": pa.int32(),
        },
    )
    stats = Statistics()
    auxiliary = []
    codes = {v: k for k, v in STATES.items()}
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        for number in range(1, 7):
            sid = f"sequence{number}"
            directory = f"psslds/zips/data/{sid}/btf/"
            signal = {
                c: np.asarray(
                    archive.read(directory + filename).decode().splitlines(),
                    dtype=np.float64,
                )
                for c, filename in CHANNELS.items()
            }
            names = archive.read(directory + "label0.btf").decode().splitlines()
            assert set(names) == set(codes)
            labels = {
                "label_behavior": np.array(
                    [codes[name] for name in names], dtype=np.int32
                )
            }
            n = len(names)
            assert all(len(v) == n and np.isfinite(v).all() for v in signal.values())
            time = np.asarray(
                archive.read(directory + "timestamp.btf").decode().splitlines(),
                dtype=np.int64,
            )
            assert len(time) == n and np.all(np.diff(time) == 33)
            for filename in [
                "id.btf",
                "framestamp.btf",
                "label1.btf",
                "lables_frame.txt",
                "turn_right1.txt",
                "waggle1.txt",
            ]:
                if directory + filename in archive.namelist():
                    auxiliary.append(
                        {
                            "series_id": sid,
                            "source_file": filename,
                            "text": archive.read(directory + filename).decode(),
                            "evaluation_status": "not used as ground truth; reference exclusively label0.btf",
                        }
                    )
            writer.add_series(
                sid,
                signal,
                time=time,
                labels=labels,
                meta={
                    "source_sequence": number,
                    "source_directory": directory,
                    "timestamp_first": int(time[0]),
                    "timestamp_step": 33,
                },
            )
            stats.add(sid, labels)
        pq.write_table(
            pa.Table.from_pylist(auxiliary),
            args.out_dir / "additional_native_fields.parquet",
            compression="zstd",
        )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Honey bee dance: six original tracked trajectories and GT labels",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="LicenseRef-Unlicensed",
        license_url=SOURCE,
        license_evidence=SOURCE,
        description="Six original automatically tracked honey-bee trajectories, with native image x/y, heading and three recurrent ground-truth behaviors from label0.btf. No model predictions replace expert labels. Local source-only builder: primary page requests citation but supplies no redistribution licence.",
        collection="Appearance-based video tracking of dancer bees in the provider's PS-SLDS study. Native ximage.btf, yimage.btf and timage.btf are synchronized by row; no synthetic paths or derived sine/cosine feature expansion. All six source sequences included.",
        annotation="Provider instruction.pdf section 4 explicitly identifies label0.btf as ground-truth labels at each tracked observation, distinguished from inferred result files. Exact source strings turn_left, turn_right and waggle mapped reversibly to codes 0, 1, 2. All are scored states; there is no null class or missing label. label1.btf exists only in sequences 1/2 but its purpose/author is undocumented, so it is preserved unscored auxiliary rather than falsely called a second expert or used for consensus. Algorithm outputs pssldsViterbi/sldsVA/sldsViterbi are excluded from labels. No independent annotator identity or agreement statistic can be established.",
        conversion="Parse only selected BTF text members inside pinned source ZIP, never extract or run included executables. Native coordinates and heading kept float64 with no angular transform, rotation, smoothing, scaling, interpolation or resampling. Native integer timestamp values retained: every step is 33, starting at 33 in sequences 1–3 and 0 in 4–6. Physical units are not established by the inspected source manual, so sampling_rate_hz=None rather than asserting unverified 30 Hz. Source tracking IDs, available one-based framestamps, undocumented label1 and additional interval-like text remain lossless unscored auxiliary. No annotations are inferred from those files.",
        limitations="Tracking noise, especially in sequences 1–3, is documented by the source. Heading units and physical timestamp rate remain unverified; do not assume a 33-unit step means exactly 1/30 second. Unknown label1 semantics preclude inter-annotator claims. Ground-truth annotation procedure/uncertainty is not fully specified. Reusing the same six trajectories from other packages is not independent validation.",
        biases="Six selected bee dance sequences, tracker and hive conditions; limited ecological generalisation. Image-plane orientation and source preprocessing can affect segmentation.",
        personal="Animal trajectories only, with source sequence and tracking IDs. No human participant or personal information included.",
        citation="Oh, Sang Min; Rehg, James M.; Balch, Tucker; Dellaert, Frank (2008). Learning and Inferring Motion Patterns using Parametric Segmental Switching Linear Dynamic Systems. International Journal of Computer Vision 77(1–3):103–124. doi:10.1007/s11263-007-0062-z.",
        creators=["Sang Min Oh", "James M. Rehg", "Tucker Balch", "Frank Dellaert"],
        date_published="2009-03-06",
        info={
            "hf_license": "other",
            "license_scope": "No licence grant found in the primary page, instruction manual or archive on 2026-10-18. Citation request is not redistribution permission. Tier C/source-only; no rehosting pending clarification.",
            "rehosting_allowed": False,
            "state_names": {"label_behavior": STATES},
            "default_label": "label_behavior",
            "reference_doi": "https://doi.org/10.1007/s11263-007-0062-z",
            "ground_truth_evidence": SOURCE + "instruction.pdf#page=3",
            "source_timestamp_unit": "unverified; native step 33",
            "sampling_rate_status": "Unverified physical units/rate; source integer timestamps retained",
            "date_published_scope": "Primary archive HTTP Last-Modified date; original paper May 2008",
            "overlap_with": {
                "tcpd": "sequence6 tracking appears as bee_waggle_6 with separate TCPD CP annotations and sine/cosine heading view; do not treat as independent signal"
            },
            "auxiliary": {
                "additional_native_fields.parquet": "Lossless source tracking IDs, available framestamps, undocumented label1 and interval-like texts. None are used as additional GT."
            },
        },
    )


if __name__ == "__main__":
    main()
