"""Build Lund's article trials, corrected labels and unequal annotator copies."""

from __future__ import annotations

import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from scipy.io import loadmat  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "lund2013-eye"
REVISION = "3e12416ab3fd6254c81811cf03f8e5d67c5d7129"
SOURCE = "https://github.com/richardandersson/EyeMovementDetectorEvaluation"
URL = f"https://codeload.github.com/richardandersson/EyeMovementDetectorEvaluation/zip/{REVISION}"
SHA256 = "a6ebfaf3eb1a7bc4dcee64d6952c0b508eb2127f0174bf084d92297f4bb1eb1a"
CHANNELS = ["gaze_x_px", "gaze_y_px", "pupil_horizontal", "pupil_vertical"]
STATES = {
    1: "fixation",
    2: "saccade",
    3: "post_saccadic_oscillation",
    4: "smooth_pursuit",
    5: "blink",
    6: "undefined_other",
}


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=500,
        channel_type=pa.float64(),
        time_column=("source_timestamp_us", pa.float64()),
        label_columns={f"label_{a}": pa.int32() for a in ["consensus", "MN", "RA"]},
        meta_columns={
            "trial_id": pa.string(),
            "participant_id": pa.string(),
            "stimulus": pa.string(),
            "source_annotators": pa.list_(pa.string()),
            "source_files": pa.list_(pa.string()),
            "alignment": pa.string(),
            "corrected_MN": pa.bool_(),
            "view_distance_m": pa.float64(),
            "screen_width_m": pa.float64(),
            "screen_height_m": pa.float64(),
            "screen_width_px": pa.int32(),
            "screen_height_px": pa.int32(),
        },
    )
    stats = Statistics()
    confusion = np.zeros((6, 6), dtype=np.int64)
    n_paired = 0
    individual_trials = []
    missing_timestamps = 0
    corrected = "UH29_img_Europe"
    groups = defaultdict(dict)
    with zipfile.ZipFile(raw) as archive:
        for name in archive.namelist():
            if "/data used in the article/" in name and name.endswith(".mat"):
                trial, annotator = Path(name).stem.rsplit("_labelled_", 1)
                groups[trial][annotator] = (
                    name,
                    loadmat(io.BytesIO(archive.read(name)), simplify_cells=True)[
                        "ETdata"
                    ],
                )
        assert len(groups) == 34
        fix = next(
            n
            for n in archive.namelist()
            if "/fix_by_Zemblys2018/" in n and n.endswith(".mat")
        )
        original = groups[corrected]["MN"][1]["pos"][:, 5].astype(np.int32)
        fixed_data = loadmat(io.BytesIO(archive.read(fix)), simplify_cells=True)[
            "ETdata"
        ]
        assert np.array_equal(
            fixed_data["pos"][:, :5],
            groups[corrected]["MN"][1]["pos"][:, :5],
            equal_nan=True,
        )
        assert np.count_nonzero(original != fixed_data["pos"][:, 5]) == 75
        groups[corrected]["MN"] = (fix, fixed_data)
    with DatasetWriter(args.out_dir, spec) as writer:
        for trial, copies in sorted(groups.items()):
            assert set(copies) == {"MN", "RA"}
            mn, ra = copies["MN"][1]["pos"], copies["RA"][1]["pos"]
            paired = np.array_equal(mn[:, :5], ra[:, :5], equal_nan=True)
            if paired:
                n_paired += 1
                presentations = [(trial, copies)]
            else:
                individual_trials.append(trial)
                presentations = [
                    (f"{trial}__{a}", {a: value}) for a, value in copies.items()
                ]
            for sid, available in presentations:
                data = next(iter(available.values()))[1]
                pos = data["pos"]
                assert data["sampFreq"] == 500 and pos.shape[1] == 6
                labels = {
                    f"label_{a}": np.full(len(pos), -1, dtype=np.int32)
                    for a in ["MN", "RA"]
                }
                for a, (_, values) in available.items():
                    y = values["pos"][:, 5]
                    assert np.isin(y, list(STATES)).all()
                    labels[f"label_{a}"] = y.astype(np.int32)
                if paired:
                    y, z = labels["label_MN"], labels["label_RA"]
                    consensus = np.where(y == z, y, -1)
                    np.add.at(confusion, (y - 1, z - 1), 1)
                else:
                    # The only available annotation is retained as the reference;
                    # this is not an independent second opinion or an alignment.
                    consensus = labels[f"label_{next(iter(available))}"].copy()
                labels = {"label_consensus": consensus, **labels}
                missing_timestamps += int(np.count_nonzero(~np.isfinite(pos[:, 0])))
                writer.add_series(
                    sid,
                    {c: pos[:, i] for c, i in zip(CHANNELS, [3, 4, 1, 2], strict=True)},
                    time=pos[:, 0],
                    labels=labels,
                    annotators=list(available),
                    meta={
                        "trial_id": trial,
                        "participant_id": trial.split("_", 1)[0],
                        "stimulus": "dots"
                        if "trial" in trial
                        else ("image" if "_img_" in trial else "video"),
                        "source_annotators": list(available),
                        "source_files": [
                            n.split("/annotated_data/", 1)[1]
                            for n, _ in available.values()
                        ],
                        "alignment": "exact_signal_identity"
                        if paired
                        else "separate_native_copy_do_not_treat_as_independent_trial",
                        "corrected_MN": trial == corrected and "MN" in available,
                        "view_distance_m": float(data["viewDist"]),
                        "screen_width_m": float(data["screenDim"][0]),
                        "screen_height_m": float(data["screenDim"][1]),
                        "screen_width_px": int(data["screenRes"][0]),
                        "screen_height_px": int(data["screenRes"][1]),
                    },
                )
                stats.add(sid, labels)
        assert n_paired == 29 and len(stats.rows) == 39
        pq.write_table(
            pa.table(
                {
                    "trial_id": [corrected],
                    "annotator": ["MN"],
                    "label_original": [original.tolist()],
                    "label_corrected": [
                        fixed_data["pos"][:, 5].astype(np.int32).tolist()
                    ],
                }
            ),
            args.out_dir / "correction.parquet",
            compression="zstd",
        )
    observed = float(np.trace(confusion) / confusion.sum())
    expected = float(np.dot(confusion.sum(0), confusion.sum(1)) / confusion.sum() ** 2)
    finish(
        args,
        spec,
        writer,
        stats,
        title="Lund 2013 expert-labelled eye movements, corrected article trials",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="GPL-3.0-only",
        license_url="https://www.gnu.org/licenses/gpl-3.0.html",
        license_evidence=f"{SOURCE}/blob/{REVISION}/README.docx",
        description="Thirty-four distinct eye-movement trials annotated by MN and RA, represented by 39 native series: 29 identical-signal pairs and five trials with two unequal native copies. All four measured gaze/pupil channels and the provider's 2018 label correction are retained.",
        collection="500-Hz SMI Hi-Speed gaze measurements from people viewing images, videos and moving dots. Native gaze x/y in screen pixels and horizontal/vertical pupil diameters (camera pixels) are retained. Screen geometry is in the index.",
        annotation="Source sample codes 1 fixation, 2 saccade, 3 post-saccadic oscillation, 4 smooth pursuit, 5 blink, 6 undefined (any sample fitting none of the other categories). Undefined and blink remain ordinary scored states. Both expert tracks retained. For 29 exactly identical signals, consensus is the common code or -1 on disagreement; for ten individual copies, consensus is explicitly the single available annotation and the unavailable expert is -1. No time shift, truncation, or invented annotator alignment. Zemblys2018 provider correction replaces 75 MN labels in UH29_img_Europe; both complete original/corrected arrays are auxiliary. Agreement is computed only on the 29 exact pairs, after correction.",
        conversion="Canonical article subset only, with explicit provider-recommended correction. The originally uploaded folder contains accidentally uploaded wrong files and is excluded per its readme. One shared row only if all five native time/signal columns match exactly including NaNs; otherwise preserve separate native copies with shared trial_id. Split/train/test grouping and statistical uncertainty must use trial_id (and preferably participant_id), never treat duplicate trial copies as independent recordings. Native float64 values and timestamps retained; missing source timestamps stay NaN, sample rate 500 Hz supplies the sampling clock. No resampling or gaze sanitisation. Demographic fpData, comments, stimuli and algorithm results are excluded.",
        limitations="Five trials differ by 1–3 samples between experts and have no safe source alignment; their sample agreement is undefined. Consensus is derived agreement, not provider adjudication; single-copy references are not two-expert consensus. Missing gaze/pupil/time values and extreme coordinates remain native. Recurrence statistics count stored series and therefore duplicate five trials; the number of independent trials is 34.",
        biases="Small laboratory participant/stimulus sample, limited hardware and only two experts; pursuit and undefined definitions can differ between experts.",
        personal="Pseudonymous participant/trial IDs and gaze/pupil traces retained. Source age/sex/comments and absolute experiment identifiers excluded; do not attempt re-identification.",
        citation="Andersson, Larsson, Holmqvist, Stridh & Nyström (2017). One algorithm to rule them all? Behavior Research Methods 49:616–637. doi:10.3758/s13428-016-0738-9. Acquisition: Larsson, Nyström & Stridh (2013), IEEE TBME 60(9):2484–2493; Larsson et al. (2015), Biomedical Signal Processing and Control 18:145–152.",
        creators=[
            "Richard Andersson",
            "Linnéa Larsson",
            "Kenneth Holmqvist",
            "Martin Stridh",
            "Marcus Nyström",
        ],
        date_published="2024-01-31",
        null_states={c: [5, 6] for c in spec.label_columns},
        info={
            "hf_license": "gpl-3.0",
            "source_revision": REVISION,
            "reference_doi": "https://doi.org/10.3758/s13428-016-0738-9",
            "state_names": {c: STATES for c in spec.label_columns},
            "date_published_scope": "Pinned source repository revision date, not original acquisition date",
            "distinct_trials": 34,
            "exactly_paired_trials": n_paired,
            "unequal_copy_trials": individual_trials,
            "source_timestamp_missing_samples": missing_timestamps,
            "default_label": "label_consensus",
            "agreement": {
                "scope": "29 exact signal pairs after correction; no alignment of unequal copies",
                "paired_samples": int(confusion.sum()),
                "sample_agreement": observed,
                "cohen_kappa": (observed - expected) / (1 - expected),
                "confusion_rows_MN_columns_RA_codes_1_to_6": confusion.tolist(),
            },
            "auxiliary": {
                "correction.parquet": "Complete MN source labels before and after provider Zemblys2018 correction, indexed from zero by list position."
            },
        },
    )


if __name__ == "__main__":
    main()
