"""Build Dreem Open Dataset - Healthy (DOD-H), Guillot et al. 2020.

Sources
- Signals: Zenodo doi:10.5281/zenodo.15900394 (MIT), ``dodh.zip`` (21.9 GB). Only the
  selected nights are fetched, by HTTP Range requests on the zip (CRC32-checked), or
  read from the raw cache (sha256-checked).
- Hypnograms of the 5 scorers (30-s epochs): GitHub
  Dreem-Organization/dreem-learning-evaluation (MIT) at a pinned commit.

Alignment (fix of the pilot): the h5 signals are cut to lights off / lights on. The
cut table of dreem-learning-evaluation (README / evaluation.py) is keyed by the h5
attribute ``record_id``, not by the file name; the window kept by the reference
evaluation is ``[max(first epoch scored by all scorers, lights_off[record_id]),
min(last epoch scored by all scorers + 1, lights_on[record_id]))``. The builder
applies this rule and checks that it gives exactly the length of the h5 signals.

Run from the repository root (isolated mode, the sources are downloads)::

    python -I builders/dreem-dod-h.py [--raw-dir DIR] [--out build] [--all-records]

Without ``--all-records``, signals are built for the 3 nights of the pilot (the
labels-only table always covers the 25 nights).

Configs (decided 2026-10-18): ``default`` = C3-M2, F3-F4, EOG1, EMG resampled to
100 Hz (the usual sleep staging rate, as Sleep-EDFx): ``scipy.signal.resample_poly(x,
2, 5)`` on the whole night in float64 (polyphase FIR anti-aliasing low-pass, Kaiser
window, cut-off at the new Nyquist frequency 50 Hz), then cast to float32; a 30-s
epoch is exactly 3 000 samples. ``full`` = the 16 channels at the native 250 Hz,
values unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import h5py  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import scipy  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from tsseg_data.build import HF_NAMESPACE, finalize, parse_args  # noqa: E402
from tsseg_data.croissant import Activity, DatasetMetadata  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.labels import (  # noqa: E402
    adjusted_rand_index,
    change_points,
    cohen_kappa,
    f1_cps,
    pairwise,
    runs,
)
from tsseg_data.sources import (  # noqa: E402
    RemoteZip,
    fetch,
    file_crc32,
    remote_extract,
    sha256,
)

ID = "dreem-dod-h"
DOI = "10.5281/zenodo.15900394"
ZIP_URL = "https://zenodo.org/api/records/15900394/files/dodh.zip/content"
ZIP_SIZE = 21872016217
ZIP_MD5 = "92043c07d397d6f84aed9bd18645ab4c"
GH_REPO = "https://github.com/Dreem-Organization/dreem-learning-evaluation"
GH_RAW = (
    "https://raw.githubusercontent.com/Dreem-Organization/dreem-learning-evaluation"
)
GH_COMMIT = "1e4c142d84634b60898845243b01b81d7eb4acec"
CHECKSUMS = json.loads((Path(__file__).parent / "checksums" / f"{ID}.json").read_text())
RECORDS = CHECKSUMS["records"]  # the 25 nights (file names = scorer file names)
PILOT_RECORDS = [
    "3e842aa8-bcd9-521e-93a2-72124233fe2c",
    "b5d5785d-87ee-5078-b9b9-aac6abd4d8de",
    "769df255-2284-50b3-8917-2155c759fbbd",
]
# CRC32 of the zip members of the pilot nights (zip central directory).
MEMBER_CRC32 = {
    "3e842aa8-bcd9-521e-93a2-72124233fe2c": 550098687,
    "b5d5785d-87ee-5078-b9b9-aac6abd4d8de": 976930194,
    "769df255-2284-50b3-8917-2155c759fbbd": 1871423930,
}
# dreem-learning-evaluation@1e4c142, README.md "dodh" settings: keyed by h5 record_id.
LIGHTS_OFF = {
    "63b799f6-8a4f-4224-8797-ea971f78fb53": 60,
    "de3af7b1-ab6f-43fd-96f0-6fc64e8d2ed4": 60,
}
LIGHTS_ON = {"a14f8058-f636-4be7-a67a-8f7f91a419e7": 620}
SCORERS = [f"s{i}" for i in range(1, 6)]
STAGES = {0: "Wake", 1: "N1", 2: "N2", 3: "N3", 4: "REM"}
EPOCH_S = 30
FS = 250
SPE = FS * EPOCH_S
DEFAULT_CHANNELS = ["C3_M2", "F3_F4", "EOG1", "EMG"]
DEFAULT_FS = 100  # default config: resampled 250 -> 100 Hz
UP, DOWN = 2, 5  # DEFAULT_FS / FS
DEFAULT_SPE = DEFAULT_FS * EPOCH_S
RESAMPLING = (
    f"scipy.signal.resample_poly(x, {UP}, {DOWN}) (scipy {scipy.__version__}) "
    "on the whole night in float64: polyphase FIR anti-aliasing low-pass "
    "(Kaiser window, beta 5, cut-off at the new Nyquist frequency 50 Hz), "
    "then cast to float32"
)
assert FS * UP == DEFAULT_FS * DOWN


def soft_agreement(h, others):
    pc = np.zeros((6, len(h)))
    for o in others:
        pc[np.asarray(o) + 1, np.arange(len(h))] += 1
    pc = pc / pc.max(0)
    return pc[np.asarray(h) + 1, np.arange(len(h))].mean()


def consensus(hyps: dict[str, np.ndarray]) -> tuple[np.ndarray, list[str]]:
    """Port of dreem-learning-evaluation ``build_consensus_hypnogram``: majority
    vote, ties broken by the scorer with the best soft agreement with the others."""
    names = list(hyps)
    ranked = sorted(
        names,
        key=lambda s: -soft_agreement(hyps[s], [hyps[o] for o in names if o != s]),
    )
    arr = np.array([hyps[s] for s in ranked]) + 1
    n = arr.shape[1]
    pc = np.zeros((6, n))
    for h in arr:
        pc[h, np.arange(n)] += 1
    cons = np.argmax(pc, 0)
    ties = (pc == pc[cons, np.arange(n)]).sum(0) > 1
    cons[ties] = arr[0][ties]
    return cons - 1, ranked


def scorer_window(
    hyps: dict[str, np.ndarray], record_id: str | None
) -> tuple[int, int]:
    """Epoch window of the reference evaluation (see module docstring)."""
    first = max(int(np.flatnonzero(h >= 0)[0]) for h in hyps.values())
    last = len(next(iter(hyps.values()))) - max(
        int(np.flatnonzero(h[::-1] >= 0)[0]) for h in hyps.values()
    )
    if record_id is not None:
        first = max(first, LIGHTS_OFF.get(record_id, 0))
        last = min(last, LIGHTS_ON.get(record_id, last))
    return first, last


def load_scorers(raw_dir: Path) -> dict[str, dict[str, np.ndarray]]:
    hyps = {}
    for rec in RECORDS:
        hyps[rec] = {}
        for i, s in enumerate(SCORERS, 1):
            key = f"scorer_{i}/{rec}.json"
            p = fetch(
                f"{GH_RAW}/{GH_COMMIT}/scorers/dodh/{key}",
                key,
                CHECKSUMS["scorers_sha256"][key],
                raw_dir / ID,
                "scorers",
            )
            h = np.asarray(json.loads(p.read_text()), dtype=np.int64)
            assert set(np.unique(h).tolist()) <= {-1, *STAGES}, (rec, s)
            hyps[rec][s] = h
        assert len({len(v) for v in hyps[rec].values()}) == 1, rec
    return hyps


def get_h5(raw_dir: Path, rec: str, rz_cache: list) -> Path:
    p = raw_dir / ID / f"{rec}.h5"
    if p.exists():
        if rec in CHECKSUMS["h5_sha256"]:
            if sha256(p) != CHECKSUMS["h5_sha256"][rec]:
                raise RuntimeError(f"sha256 mismatch for {p}")
        elif file_crc32(p) != MEMBER_CRC32.get(rec, -1):
            raise RuntimeError(f"no pinned digest matches {p}")
        return p
    if not rz_cache:
        rz_cache.append(RemoteZip(ZIP_URL, ZIP_SIZE))
    remote_extract(rz_cache[0], f"dodh/{rec}.h5", p)  # CRC32 checked
    if rec not in CHECKSUMS["h5_sha256"] or sha256(p) != CHECKSUMS["h5_sha256"][rec]:
        raise RuntimeError(f"missing or mismatched pinned H5 SHA256: {rec}")
    return p


def main() -> None:
    args = parse_args(
        ID,
        extra=lambda p: p.add_argument(
            "--all-records",
            action="store_true",
            help="build the signals of the 25 nights (downloads ~20 GB more)",
        ),
    )
    records_sig = RECORDS if args.all_records else PILOT_RECORDS
    hyps = load_scorers(args.raw_dir)

    rz: list = []
    nights, channels, units, ch_meta = {}, None, {}, {}
    for rec in records_sig:
        h5p = get_h5(args.raw_dir, rec, rz)
        with h5py.File(h5p, "r") as f:
            desc = json.loads(f.attrs["description"])
            cols = [d["path"].split("/")[-1] for d in desc]
            for d, c in zip(desc, cols, strict=True):
                assert d["fs"] == FS
                units[c] = d["unit"]
                ch_meta[c] = {
                    "name": d["name"],
                    "domain": d["domain"],
                    "source_path": d["source_path"],
                }
            record_id = f.attrs["record_id"].decode()
            nights[rec] = {
                "h5": h5p,
                "record_id": record_id,
                "start_time": float(f.attrs["start_time"]),
                "n_epochs_h5": len(f["hypnogram"]),
                "n_samples": len(f[desc[0]["path"]]),
            }
        channels = channels or cols
        assert cols == channels, rec
    if channels is None:
        raise RuntimeError("no night with signals")

    # ---- labels of the 25 nights: window, consensus, agreement
    windows, cons_all, ranking, epochs = {}, {}, {}, []
    for rec in RECORDS:
        rid = nights[rec]["record_id"] if rec in nights else None
        a, b = scorer_window(hyps[rec], rid)
        windows[rec] = (a, b)
        cons = np.full(len(hyps[rec]["s1"]), -1, dtype=np.int64)
        c, ranked = consensus({s: h[a:b] for s, h in hyps[rec].items()})
        cons[a:b] = c
        cons_all[rec], ranking[rec] = cons, ranked
        df = pd.DataFrame(
            {"series_id": rec, "epoch": np.arange(len(cons), dtype=np.int32)}
        )
        for s in SCORERS:
            df[f"label_{s}"] = hyps[rec][s].astype(np.int8)
        df["label_consensus"] = cons.astype(np.int8)
        df["in_window"] = (df.epoch >= a) & (df.epoch < b)
        df["lights_cut_known"] = rid is not None
        df["has_signals"] = rec in nights
        epochs.append(df)
    epochs = pd.concat(epochs, ignore_index=True)

    kappas, aris, f1s, k_vs_cons = [], [], [], {s: [] for s in SCORERS}
    for rec in RECORDS:
        a, b = windows[rec]
        hw = {s: hyps[rec][s][a:b] for s in SCORERS}
        kappas += pairwise(hw, cohen_kappa)
        aris += pairwise(hw, adjusted_rand_index)
        f1s += pairwise(
            {s: change_points(h) for s, h in hw.items()}, lambda x, y: f1_cps(x, y, 1)
        )
        for s in SCORERS:
            others, _ = consensus({o: hw[o] for o in SCORERS if o != s})
            k_vs_cons[s].append(cohen_kappa(hw[s], others))
    agreement = {
        "unit": "30-s epochs inside the evaluation window, 25 nights",
        "pairwise_cohen_kappa_mean": round(float(np.nanmean(kappas)), 3),
        "pairwise_ari_mean": round(float(np.nanmean(aris)), 3),
        "pairwise_transition_f1_margin_1_epoch_mean": round(float(np.mean(f1s)), 3),
        "kappa_vs_consensus_of_others": {
            s: round(float(np.nanmean(v)), 3) for s, v in k_vs_cons.items()
        },
    }

    # ---- signals
    label_cols = {f"label_{s}": pa.int8() for s in SCORERS}
    label_cols["label_consensus"] = pa.int8()
    label_cols["label_h5"] = pa.int8()
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=channels,
        configs={"default": DEFAULT_CHANNELS, "full": channels},
        sampling_rate_hz=FS,
        config_rates={"default": DEFAULT_FS},
        channel_type=pa.float32(),
        label_columns=label_cols,
        meta_columns={
            "record_id": pa.string(),
            "start_time_unix": pa.float64(),
            "window_first_epoch": pa.int32(),
            "window_end_epoch": pa.int32(),
            "n_epochs_scored": pa.int32(),
            "h5_hypnogram_agreement": pa.float64(),
        },
    )
    per_night = {}
    with DatasetWriter(args.out_dir, spec) as w:
        for rec in sorted(nights):
            nt = nights[rec]
            a, b = windows[rec]
            if b - a != nt["n_epochs_h5"] or nt["n_samples"] != nt["n_epochs_h5"] * SPE:
                raise RuntimeError(
                    f"{rec}: window {a}:{b} does not match the h5 "
                    f"({nt['n_epochs_h5']} epochs, {nt['n_samples']} samples)"
                )
            with h5py.File(nt["h5"], "r") as f:
                desc = json.loads(f.attrs["description"])
                sig = {
                    c: f[d["path"]][...].astype(np.float32)
                    for c, d in zip(channels, desc, strict=True)
                }
                hyp_h5 = f["hypnogram"][...].astype(np.int64)
            ep = {f"label_{s}": hyps[rec][s][a:b] for s in SCORERS}
            ep["label_consensus"] = cons_all[rec][a:b]
            ep["label_h5"] = hyp_h5
            assert all(set(np.unique(v)) <= {-1, *STAGES} for v in ep.values()), rec
            labs = {c: np.repeat(v, SPE) for c, v in ep.items()}
            low = {
                c: resample_poly(sig[c].astype(np.float64), UP, DOWN).astype(np.float32)
                for c in DEFAULT_CHANNELS
            }
            assert all(len(v) == (b - a) * DEFAULT_SPE for v in low.values()), rec
            agree_h5 = float((hyp_h5 == cons_all[rec][a:b]).mean())
            w.add_series(
                rec,
                sig,
                labels=labs,
                annotators=SCORERS,
                resampled={
                    "default": {
                        "signals": low,
                        "labels": {c: np.repeat(v, DEFAULT_SPE) for c, v in ep.items()},
                    }
                },
                meta={
                    "record_id": nt["record_id"],
                    "start_time_unix": nt["start_time"],
                    "window_first_epoch": a,
                    "window_end_epoch": b,
                    "n_epochs_scored": len(hyps[rec]["s1"]),
                    "h5_hypnogram_agreement": agree_h5,
                },
            )
            v, _, _ = runs(cons_all[rec][a:b])
            per_night[rec] = {
                "hours": (b - a) * EPOCH_S / 3600,
                "segments": len(v),
                "unscored_share": float((labs["label_consensus"] < 0).mean()),
                "h5_agreement": agree_h5,
                "samples_full": nt["n_samples"],
                "samples_default": (b - a) * DEFAULT_SPE,
                "record_id": nt["record_id"],
                "window_first_epoch": a,
                "window_end_epoch": b,
                "tracks": {
                    c: {
                        "segments": len(runs(y)[0]),
                        "missing_share": float((y < 0).mean()),
                        "recurrent": bool(
                            np.any(
                                np.unique(
                                    runs(y)[0][runs(y)[0] != -1], return_counts=True
                                )[1]
                                > 1
                            )
                        ),
                    }
                    for c, y in ep.items()
                },
            }
            print(rec, per_night[rec], flush=True)
            del sig, labs, low
    summary = w.summary()
    epochs.to_parquet(args.out_dir / "epochs.parquet", index=False, compression="zstd")

    win_epochs = epochs[epochs.in_window]
    seg_counts = [
        len(runs(cons_all[r][windows[r][0] : windows[r][1]])[0]) for r in RECORDS
    ]
    native_lengths = [r["samples_full"] for r in per_night.values()]
    measured = {
        "n_series": len(per_night),
        "samples": sum(native_lengths),
        "samples_default": sum(r["samples_default"] for r in per_night.values()),
        "length_min": min(native_lengths),
        "length_median": float(np.median(native_lengths)),
        "length_max": max(native_lengths),
        "sample_counts_basis": "full config at native 250 Hz; default counts also supplied",
        "tracks": {
            c: {
                "segments": sum(r["tracks"][c]["segments"] for r in per_night.values()),
                "series_with_recurrence": sum(
                    r["tracks"][c]["recurrent"] for r in per_night.values()
                ),
                "missing_share": sum(
                    r["tracks"][c]["missing_share"] * r["samples_full"]
                    for r in per_night.values()
                )
                / sum(native_lengths),
            }
            for c in label_cols
        },
    }
    info = {
        "label_type": "multi_annotator",
        "domain": "sleep (polysomnography)",
        "sampling": "regular; default config 100 Hz (resampled), full config 250 Hz "
        "(native); labels on 30-s epochs repeated per sample",
        "resampling": {"default": RESAMPLING},
        "units": units,
        "channel_info": ch_meta,
        "tracks": None,
        "annotators": SCORERS,
        "consensus_label": "label_consensus",
        "default_label": "label_consensus",
        "other_labels": {
            "label_h5": "hypnogram shipped in the source h5 file (provider "
            "version; differs from the recomputed consensus on a few % of "
            "epochs)"
        },
        "null_states": {},
        "state_names": {c: {str(k): v for k, v in STAGES.items()} for c in label_cols},
        "label_descriptions": {
            **{
                f"label_{s}": f"sleep stage scored by scorer {s[1]} (30-s epoch repeated "
                "per sample); -1 = epoch not scored"
                for s in SCORERS
            },
            "label_consensus": "consensus stage (majority; ties -> best-ranked scorer)",
            "label_h5": "hypnogram of the source h5 file",
        },
        "epoch_seconds": EPOCH_S,
        "label_origin": "human",
        "splits": None,
        "records_with_signals": sorted(nights),
        "all_records": RECORDS,
        "lights_cut_rule": "window = [max(first epoch scored by all, lights_off[record_id]),"
        " min(last epoch scored by all + 1, lights_on[record_id]))",
        "lights_off_by_record_id": LIGHTS_OFF,
        "lights_on_by_record_id": LIGHTS_ON,
        "scorer_ranking_per_record": ranking,
        "agreement": agreement,
        "series_statistics": per_night,
        "statistics": measured,
        "license_verification": {
            "date": "2026-10-18",
            "license": "MIT",
            "url": f"https://zenodo.org/records/{DOI.split('.')[-1]}",
            "depositor": "Valentin Thorey, paper co-author (ORCID 0000-0002-8327-815X)",
            "provider_confirmation": "https://github.com/Dreem-Organization/dreem-learning-open#download-of-dod-o-and-dod-h",
        },
        "source": {
            "signals_doi": DOI,
            "zip_url": ZIP_URL,
            "zip_md5": ZIP_MD5,
            "scorers_repo": f"{GH_REPO}/tree/{GH_COMMIT}",
            "h5_sha256": {r: CHECKSUMS["h5_sha256"].get(r) for r in nights},
        },
    }
    hrs = [v["hours"] for v in per_night.values()]
    facts = "\n".join(
        [
            "| | |",
            "|---|---|",
            "| Task | state detection (sleep stages); CPD from stage transitions |",
            "| Domain | sleep medicine, overnight polysomnography |",
            f"| Series | {len(nights)} nights with signals in this build (of 25; "
            "`--all-records` builds all); `epochs.parquet` has the labels of the 25 |",
            f"| Length | {min(hrs):.1f} - {max(hrs):.1f} h: "
            f"{min(hrs) * 3600 * DEFAULT_FS:.2e} - {max(hrs) * 3600 * DEFAULT_FS:.2e} "
            f"samples at 100 Hz (`default`), {min(hrs) * 3600 * FS:.2e} - "
            f"{max(hrs) * 3600 * FS:.2e} at 250 Hz (`full`), stored in 1-h chunks |",
            "| Channels | 16: 12 EEG derivations, 2 EOG, EMG, ECG (mV) |",
            "| Labels | 5 stages (Wake, N1, N2, N3, REM), 30-s epochs, 5 scorers + consensus |",
            f"| Segments per night | {min(seg_counts)} - {max(seg_counts)} (consensus) |",
            f"| Consensus recurrence | {measured['tracks']['label_consensus']['series_with_recurrence']}/{len(nights)} built nights |",
            f"| Not scored in window | {float((win_epochs.label_consensus < 0).mean()):.2%} of epochs |",
            f"| Agreement | pairwise Cohen kappa {agreement['pairwise_cohen_kappa_mean']}, "
            f"ARI {agreement['pairwise_ari_mean']}, transition F1 (+-1 epoch) "
            f"{agreement['pairwise_transition_f1_margin_1_epoch_mean']} |",
            "| License | MIT |",
            f"| Source | [doi:{DOI}](https://doi.org/{DOI}), [{GH_REPO.split('/')[-1]}]({GH_REPO}) |",
        ]
    )
    rai = {
        "dataCollection": "One overnight clinical polysomnography (PSG) per subject, 25 "
        "healthy adult volunteers at IRBA's Fatigue and Vigilance Unit, Bretigny-sur-Orge, "
        "France, using a Siesta PSG system (Compumedics), as described in Guillot et al. "
        "(2020), section II-A1. The primary provider repository links this Zenodo release.",
        "dataCollectionType": "Clinical physiological recordings of human subjects.",
        "dataCollectionTimeframe": "Recording dates are in the source (start_time); "
        "released 2020, Zenodo version 2025-07.",
        "dataPreprocessingProtocol": "Signals as released in the h5 files (already "
        "filtered and resampled to 250 Hz by the providers, float32), cut by the "
        "providers to lights off / on; kept unchanged in the full config. Default "
        "config: 4 channels (C3-M2, F3-F4, EOG1, EMG) resampled to 100 Hz with "
        + RESAMPLING
        + "; a 30-s epoch is exactly 3 000 samples. Labels aligned to the "
        "signals with the record_id-keyed cut table of dreem-learning-evaluation.",
        "dataAnnotationProtocol": "Each night scored independently by 5 sleep experts "
        "following the AASM rules, in 30-s epochs, into Wake, N1, N2, N3, REM (-1 = not "
        "scored). Consensus as in Guillot et al. (2020): majority vote, ties broken by "
        "the scorer who agrees best with the others on that night.",
        "dataAnnotationPlatform": "Not documented in the release (clinical scoring "
        "software of each scorer).",
        "dataAnnotationAnalysis": f"Agreement computed by the builder on the 25 nights "
        f"(epochs inside the evaluation window): mean pairwise Cohen kappa "
        f"{agreement['pairwise_cohen_kappa_mean']}, mean pairwise ARI "
        f"{agreement['pairwise_ari_mean']}, mean pairwise F1 of stage transitions "
        f"(+-1 epoch) {agreement['pairwise_transition_f1_margin_1_epoch_mean']}; kappa "
        "of each scorer against the consensus of the other four: "
        + ", ".join(
            f"{k} {v}" for k, v in agreement["kappa_vs_consensus_of_others"].items()
        )
        + ".",
        "annotationsPerItem": "5 expert labels per 30-s epoch, plus the consensus.",
        "annotatorDemographics": "Five registered polysomnography technologists from three "
        "sleep centres, each with more than five years of clinical/scoring experience, "
        "using AASM v2.5 (Guillot et al. 2020 section II-A1). Individual identities not released.",
        "dataLimitations": "25 subjects only, healthy adults: not representative of "
        "patients (see DOD-O). Labels are piecewise constant on 30-s epochs, so change "
        "points are only defined to the epoch. Very long series (~7 M samples per "
        "channel). Not for clinical use or diagnosis.",
        "dataBiases": "Healthy, relatively young cohort from a single site; scorer "
        "disagreement concentrates on N1 and transitions.",
        "personalSensitiveInformation": "Health data: physiological signals (EEG, ECG...) "
        "of pseudonymous subjects. The recording start time is kept as in the source. "
        "No demographic attribute is included in this conversion.",
        "dataUseCases": "Sleep staging, state detection on long multichannel series, "
        "studies of inter-annotator variability. Validity of the consensus as reference "
        "established by Guillot et al. (2020) for automated sleep staging evaluation.",
        "dataSocialImpact": "Positive: open, multi-scored reference for sleep staging. "
        "Risks: health data; models evaluated on healthy subjects may not transfer to "
        "patients. The source is pseudonymised and released under MIT by its providers.",
        "hasSyntheticData": False,
        "dataReleaseMaintenancePlan": "Versioned with the tsseg-data repository; rebuilt "
        "from the pinned Zenodo record and GitHub commit. Issues: tsseg-data issue "
        "tracker.",
    }
    cite = (
        "@article{guillot2020dreem, title={Dreem Open Datasets: Multi-Scored Sleep "
        "Datasets to Compare Human and Automated Sleep Staging}, author={Guillot, "
        "Antoine and Sauvet, Fabien and During, Emmanuel H. and Thorey, Valentin}, "
        "journal={IEEE Transactions on Neural Systems and Rehabilitation Engineering}, "
        "volume={28}, number={9}, pages={1955--1965}, year={2020}, "
        "doi={10.1109/TNSRE.2020.3011181}}"
    )
    meta = DatasetMetadata(
        name=ID,
        description="Dreem Open Dataset - Healthy (DOD-H): overnight polysomnography of 25 "
        "healthy adults (12 EEG derivations, 2 EOG, EMG, ECG at 250 Hz), each night "
        "scored in 30-s epochs by 5 independent sleep experts (AASM), with the consensus "
        "of Guillot et al. (2020). Converted to the tsseg-data format (one Parquet row "
        "per one-hour chunk, labels repeated per sample): default config = 4 channels "
        "resampled to 100 Hz, full config = the 16 channels at 250 Hz; per-epoch labels "
        "of all 25 nights in epochs.parquet.",
        url=f"https://huggingface.co/datasets/{HF_NAMESPACE}/{ID}",
        license_url="https://spdx.org/licenses/MIT.html",
        license_spdx="MIT",
        cite_as=cite,
        creators=[
            "Guillot, Antoine",
            "Sauvet, Fabien",
            "During, Emmanuel H.",
            "Thorey, Valentin",
        ],
        date_published="2025-07-15",
        version="1.0.0",
        keywords=[
            "sleep staging",
            "polysomnography",
            "EEG",
            "multi-annotator",
            "state detection",
            "time series segmentation",
        ],
        derived_from=[
            {"@id": f"https://doi.org/{DOI}", "name": "Dreem Open Datasets (Zenodo)"},
            {
                "@id": f"{GH_REPO}/tree/{GH_COMMIT}",
                "name": "dreem-learning-evaluation (scorer hypnograms)",
            },
            {
                "@id": "https://doi.org/10.1109/TNSRE.2020.3011181",
                "name": "Guillot et al. 2020 (paper)",
            },
        ],
        activities=[
            Activity(
                "data collection",
                rai["dataCollection"],
                agents=["Dreem", "Guillot et al. 2020"],
            ),
            Activity(
                "data annotation",
                rai["dataAnnotationProtocol"] + " " + rai["dataAnnotationAnalysis"],
                agents=["5 sleep experts"],
            ),
            Activity(
                "preprocessing",
                f"tsseg-data builders/{ID}.py: h5 -> Parquet; "
                "full config: 16 channels at 250 Hz, float32 values unchanged; "
                "default config: 4 channels resampled 250 -> 100 Hz with "
                + RESAMPLING
                + "; one-hour chunks, scorer hypnograms "
                "aligned with the record_id-keyed lights-off/on table of "
                "dreem-learning-evaluation and repeated per sample, consensus "
                "recomputed (port of build_consensus_hypnogram).",
                agents=["tsseg-data"],
                used=[f"https://doi.org/{DOI}", f"{GH_REPO}/tree/{GH_COMMIT}"],
            ),
        ],
        rai=rai,
        field_descriptions={
            **{
                c: f"{ch_meta[c]['domain']} {ch_meta[c]['name']} at 250 Hz ({units[c]})."
                for c in channels
            },
            **{
                f"default/{c}": f"{ch_meta[c]['domain']} {ch_meta[c]['name']} resampled "
                f"to 100 Hz ({units[c]})."
                for c in DEFAULT_CHANNELS
            },
            **{c: d for c, d in info["label_descriptions"].items()},
            "epoch": "Epoch number (30 s) from the start of the scorer hypnogram.",
            "in_window": "Epoch inside the evaluation window (scored by all scorers, "
            "between lights off and on when known).",
            "lights_cut_known": "The night's record_id is known, so its lights cut is "
            "applied (only for nights with signals in this build).",
            "has_signals": "The signals of the night are in this build.",
        },
        auxiliary={
            "epochs.parquet": "Per-epoch labels of the 25 nights (5 scorers and "
            "consensus), with the evaluation window."
        },
        tsseg={
            "annotators": SCORERS,
            "defaultLabel": "label_consensus",
            "epochSeconds": EPOCH_S,
            "agreement": agreement,
            "zipMd5": ZIP_MD5,
            "scorersCommit": GH_COMMIT,
            "licenseVerification": info["license_verification"],
            "sourceH5Sha256": info["source"]["h5_sha256"],
        },
    )
    card = {
        "pretty_name": "Dreem Open Dataset - Healthy (DOD-H)",
        "hf_license": "mit",
        "tags": [
            "time-series",
            "state-detection",
            "change-point-detection",
            "time-series-segmentation",
            "sleep-staging",
            "eeg",
            "polysomnography",
            "multi-annotator",
            "tsseg",
        ],
        "size_category": "n<1K",
        "annotations_creators": ["expert-generated"],
        "summary": "Overnight polysomnography of 25 healthy adults, each night scored by 5 "
        "independent sleep experts. Long multichannel series (5-8 h at 100 Hz in the "
        "default config, 250 Hz in the full one) with "
        "recurrent states (sleep cycles) and a measured inter-annotator variability: a "
        "demanding state detection benchmark.",
        "facts": facts,
        "labels": "Sleep stages 0 = Wake, 1 = N1, 2 = N2, 3 = N3, 4 = REM; -1 = epoch "
        "not scored (absence of ground truth). Columns: `label_s1` ... `label_s5` (one "
        "per scorer), `label_consensus` (default ground truth) and `label_h5` (the "
        "hypnogram shipped in the h5 file, kept for reference). No null state. Labels "
        "are defined per 30-s epoch (3 000 samples at 100 Hz in `default`, 7 500 at "
        "250 Hz in `full`) and repeated per sample.",
        "annotation": rai["dataAnnotationProtocol"]
        + "\n\n"
        + rai["dataAnnotationAnalysis"]
        + " Label origin: `human`.",
        "conversion": "\n".join(
            [
                f"- Signals: members `dodh/<record>.h5` of `dodh.zip` ([doi:{DOI}]"
                f"(https://doi.org/{DOI}), md5 `{ZIP_MD5}`), fetched by HTTP Range and "
                "checked by CRC32, or read from a cache checked by sha256 "
                f"(`builders/checksums/{ID}.json`).",
                f"- Hypnograms: `scorers/dodh/scorer_<k>/<record>.json` of "
                f"[dreem-learning-evaluation@{GH_COMMIT[:7]}]({GH_REPO}/tree/{GH_COMMIT}), "
                "sha256-pinned.",
                "- Alignment: the h5 signals start at lights off and stop at lights on. The "
                "cut table of the reference evaluation is keyed by the h5 attribute "
                "`record_id` (not by the file name); the window "
                "`[max(first epoch scored by all, lights_off), min(last epoch scored by all "
                "+ 1, lights_on))` reproduces the h5 length exactly for every built night "
                "(checked; the build fails otherwise). In `epochs.parquet`, the lights cut "
                "is applied only to nights whose h5 was read (`lights_cut_known`).",
                "- `full`: values unchanged (float32, 250 Hz); 1-h chunks of 900 000 "
                "samples.",
                "- `default`: C3-M2, F3-F4, EOG1, EMG resampled to 100 Hz (the usual sleep "
                "staging rate, as Sleep-EDFx) with " + RESAMPLING + "; 1-h chunks of "
                "360 000 samples, labels repeated over 3 000 samples per epoch.",
                f"- Rebuild: `python -I builders/{ID}.py [--all-records]` in tsseg-data.",
            ]
        ),
        "license": "MIT (Zenodo record and dreem-learning-evaluation repository). "
        "Verified 2026-10-18 at https://zenodo.org/records/15900394, deposited by "
        "paper co-author Valentin Thorey and linked by the primary Dreem-Organization "
        "repository. Attribution: Guillot et al. (2020). The conversion code is MIT.",
        "citation": "```bibtex\n" + cite + "\n```",
    }
    finalize(
        args.out_dir,
        spec,
        info,
        meta,
        card,
        summary,
        {
            "default": "4 channels (C3-M2 and F3-F4 EEG, EOG, EMG) resampled to 100 Hz, "
            "all labels.",
            "full": "all 16 channels at 250 Hz, all labels.",
        },
    )
    print(
        f"{ID}: {len(nights)} nights",
        {k: v["bytes"] for k, v in summary.items()},
        agreement,
    )


if __name__ == "__main__":
    main()
