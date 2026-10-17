"""Build OPPORTUNITY Activity Recognition (UCI 226, CC BY 4.0, doi:10.24432/C5M027).

4 subjects x 6 runs (5 ADL + 1 drill), 242 body / object / ambient channels at 30 Hz,
7 label tracks with an explicit Null class (kept as a state, listed in null_states).

Run from the repository root (isolated mode, the source is a download)::

    python -I builders/opportunity.py [--raw-dir DIR] [--out build]
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.build import HF_NAMESPACE, finalize, parse_args  # noqa: E402
from tsseg_data.croissant import Activity, DatasetMetadata  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.labels import runs  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "opportunity"
URL = "https://archive.ics.uci.edu/static/public/226/opportunity+activity+recognition.zip"
SHA256 = "3df913b5e5a987d309596350385087737784c9d4b811389536eb3a9bcaf6f1d0"
DOI = "10.24432/C5M027"
P = "OpportunityUCIDataset/dataset/"
FS = 30.0
TRACKS = ["Locomotion", "HL_Activity", "LL_Left_Arm", "LL_Left_Arm_Object",
          "LL_Right_Arm", "LL_Right_Arm_Object", "ML_Both_Arms"]
ABBR = {"Accelerometer": "acc", "InertialMeasurementUnit": "imu",
        "REED SWITCH": "reed", "LOCATION": "loc"}
# Default config: accelerometers of the 5 wired upper-body IMUs (little data loss).
DEFAULT_PREFIX = ("imu_back_acc", "imu_rua_acc", "imu_rla_acc", "imu_lua_acc", "imu_lla_acc")


def slug(desc: str) -> str:
    desc = desc.strip()
    for k, v in ABBR.items():
        if desc.startswith(k):
            desc = v + " " + desc[len(k):]
            break
    # body positions: "RKN^" (upper) and "RKN_" (lower) are two different sensors
    desc = re.sub(r"\^(?=\s|$)", "_up", desc)
    desc = re.sub(r"(?<=[A-Z])_(?=\s|$)", "_lo", desc)
    return re.sub(r"[^a-z0-9]+", "_", desc.lower()).strip("_")


def channel_names(lines: list[str]) -> tuple[list[str], dict, dict, list[dict]]:
    """Channel names, units, source descriptions and the axis fixes applied.

    The source repeats "accX" three times for each of the 12 object sensors
    (e.g. columns 135-137 "Accelerometer CUP accX"), followed by "gyroX", "gyroY".
    The documentation describes these sensors as "3D acceleration and 2D rate of
    turn", so the three repeated columns are the X, Y, Z axes in this order (the
    same order as every other 3D sensor of the file). They are renamed accordingly
    and the fix is recorded.
    """
    descs, units = [], []
    for ln in lines:
        m = re.match(r"Column:\s+(\d+)\s+([^;]+);?(.*)$", ln)
        descs.append((int(m.group(1)), m.group(2).strip()))
        u = re.search(r"unit = (.*)$", m.group(3))
        units.append(u.group(1).strip() if u else "unknown")
    fixes = []
    descs_fixed = list(descs)
    i = 0
    while i < len(descs):
        col, d = descs[i]
        if (d.endswith(" accX") and i + 4 < len(descs)
                and [x[1] for x in descs[i:i + 5]] ==
                [d, d, d, d[:-4] + "gyroX", d[:-4] + "gyroY"]):
            for k, ax in enumerate("XYZ"):
                new = d[:-1] + ax
                descs_fixed[i + k] = (descs[i + k][0], new)
                if k:
                    fixes.append({"source_column": descs[i + k][0], "source_description": d,
                                  "renamed_to": new})
            i += 5
        else:
            i += 1
    names = [slug(d) for _, d in descs_fixed]
    assert len(set(names)) == len(names), "duplicated channel names remain"
    unit_map = dict(zip(names, units))
    source = {n: {"source_column": c, "source_description": d0}
              for n, (c, d0) in zip(names, descs)}
    return names, unit_map, source, fixes


def split_of(run: str) -> str:
    """Opportunity challenge (Chavarriaga et al. 2013): labels of ADL4 and ADL5 of
    subjects 2, 3 and 4 were withheld for testing."""
    subj, sess = run.split("-")
    return "test" if subj in ("S2", "S3", "S4") and sess in ("ADL4", "ADL5") else "train"


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "opportunity.zip", SHA256, args.raw_dir, ID)
    z = zipfile.ZipFile(raw)

    cols = [ln for ln in z.read(P + "column_names.txt").decode("latin-1").splitlines()
            if ln.startswith("Column:")]
    assert len(cols) == 250
    channels, units, source_cols, axis_fixes = channel_names(cols[1:243])
    assert len(axis_fixes) == 24, len(axis_fixes)
    track_cols = [re.match(r"Column:\s+\d+\s+(\S+)", ln).group(1) for ln in cols[243:]]
    assert track_cols == TRACKS, track_cols

    # legend: per track, source code -> name; ids: 0 = Null (source code 0), then
    # the source codes in increasing order -> 1..k
    legend = {t: {} for t in TRACKS}
    for ln in z.read(P + "label_legend.txt").decode("latin-1").splitlines():
        m = re.match(r"\s*(\d+)\s+-\s+(\S+)\s+-\s+(.+?)\s*$", ln)
        if m:
            legend[m.group(2)][int(m.group(1))] = m.group(3)
    code2id = {t: {0: 0, **{c: i + 1 for i, c in enumerate(sorted(legend[t]))}} for t in TRACKS}
    label_cols = {f"label_{t.lower()}": pa.int16() for t in TRACKS}
    state_names = {
        f"label_{t.lower()}": {str(i): ("Null" if c == 0 else legend[t][c])
                               for c, i in code2id[t].items()}
        for t in TRACKS
    }
    state_codes = {f"label_{t.lower()}": {str(i): c for c, i in code2id[t].items()}
                   for t in TRACKS}
    null_states = {c: [0] for c in label_cols}

    default = [c for c in channels if c.startswith(DEFAULT_PREFIX)]
    assert len(default) == 15, default
    spec = DatasetSpec(
        id=ID, task="sd", channels=channels,
        configs={"default": default, "full": channels},
        sampling_rate_hz=FS, channel_type=pa.float32(),
        time_column=("t_ms", pa.int64()), label_columns=label_cols,
        meta_columns={"subject": pa.string(), "session": pa.string(),
                      "run_type": pa.string(), "dt_ms_median": pa.float64(),
                      "dt_ms_max": pa.float64(), "nan_share_full": pa.float64(),
                      "nan_share_default": pa.float64()},
    )
    runs_ = sorted(n[len(P):-4] for n in z.namelist() if n.startswith(P) and n.endswith(".dat"))
    stats = {c: {"segments": [], "null_share": [], "recurrent": [], "seg_per_state": []}
             for c in label_cols}
    lengths = []
    with DatasetWriter(args.out_dir, spec) as w:
        for run in runs_:
            with z.open(P + run + ".dat") as f:
                a = pd.read_csv(f, sep=r"\s+", header=None, dtype=np.float64).to_numpy()
            assert a.shape[1] == 250, a.shape
            t_ms = a[:, 0].astype(np.int64)
            assert np.all(a[:, 0] == t_ms)
            sig = {c: a[:, 1 + j].astype(np.float32) for j, c in enumerate(channels)}
            labs = {}
            for j, t in enumerate(TRACKS):
                src = a[:, 243 + j].astype(np.int64)
                lut = code2id[t]
                unknown = set(np.unique(src).tolist()) - set(lut)
                assert not unknown, (run, t, unknown)
                ids = np.zeros(len(src), dtype=np.int16)
                for c, i in lut.items():
                    ids[src == c] = i
                labs[f"label_{t.lower()}"] = ids
                v, _, _ = runs(ids)
                lab = v[v != 0]
                st = stats[f"label_{t.lower()}"]
                st["segments"].append(len(v))
                st["null_share"].append(float((ids == 0).mean()))
                if len(lab):
                    _, cnt = np.unique(lab, return_counts=True)
                    st["recurrent"].append(float((cnt >= 2).mean()))
                    st["seg_per_state"].append(float(cnt.mean()))
            dt = np.diff(t_ms)
            subj, sess = run.split("-")
            w.add_series(
                run, sig, labels=labs, time=t_ms, split=split_of(run),
                meta={"subject": subj, "session": sess,
                      "run_type": "drill" if sess == "Drill" else "adl",
                      "dt_ms_median": float(np.median(dt)), "dt_ms_max": float(dt.max()),
                      "nan_share_full": float(np.isnan(a[:, 1:243]).mean()),
                      "nan_share_default": float(np.mean([np.isnan(sig[c]).mean()
                                                          for c in default]))},
            )
            lengths.append(len(t_ms))
            print(run, len(t_ms), flush=True)
    summary = w.summary()

    def q(x):
        return f"{np.min(x):.2f} / {np.median(x):.2f} / {np.max(x):.2f}"

    track_rows = ["| Track | States (+ Null) | Null share min / med / max | Segments per run (median) | Recurrent states |",
                  "|---|---|---|---|---|"]
    for c, st in stats.items():
        track_rows.append(
            f"| `{c}` | {len(state_names[c]) - 1} | {q(st['null_share'])} | "
            f"{int(np.median(st['segments']))} | "
            f"{np.mean(st['recurrent']):.0%} (~{np.mean(st['seg_per_state']):.0f} seg./state) |")
    track_table = "\n".join(track_rows)
    lengths = np.array(lengths)
    info = {
        "label_type": "multi_track",
        "domain": "human activity recognition",
        "sampling": "regular, 30 Hz (time stamps in t_ms; small jitter, see index)",
        "time_description": "time since the start of the run, ms (source MILLISEC)",
        "units": units,
        "source_columns": source_cols,
        "axis_fixes": axis_fixes,
        "tracks": [t.lower() for t in TRACKS],
        "annotators": None,
        "default_label": "label_locomotion",
        "null_states": null_states,
        "state_names": state_names,
        "state_source_codes": state_codes,
        "label_descriptions": {c: f"track {t}: state id (names in tsseg.json), 0 = Null"
                               for c, t in zip(label_cols, TRACKS)},
        "label_origin": "human",
        "splits": {"train": "all runs except the test runs",
                   "test": "ADL4 and ADL5 of S2, S3, S4 (Opportunity challenge, "
                           "Chavarriaga et al. 2013)"},
        "agreement": None,
        "source": {"url": URL, "doi": DOI, "sha256": SHA256},
    }
    facts = "\n".join([
        "| | |", "|---|---|",
        "| Task | state detection (and CPD from the label changes) |",
        "| Domain | human activity recognition (sensor-rich kitchen) |",
        f"| Series | {len(lengths)} runs: 4 subjects x (5 ADL + 1 drill) |",
        f"| Length | {lengths.min()} - {lengths.max()} samples ({lengths.min() / FS / 60:.0f} - {lengths.max() / FS / 60:.0f} min) |",
        "| Channels | 242 (7 IMUs, 12 3D accelerometers, 4 localisation tags, 12 object "
        "sensors, 13 reed switches, 8 ambient 3D accelerometers); NaN = packet loss |",
        "| Sampling | 30 Hz |",
        "| Labels | 7 tracks (locomotion, high-level activity, left / right arm actions and "
        "objects, mid-level gestures), each with a Null class |",
        "| Annotators | one annotation per track (no inter-annotator data) |",
        "| License | CC BY 4.0 |",
        f"| Source | [doi:{DOI}](https://doi.org/{DOI}) |",
    ])
    rai = {
        "dataCollection": "Recorded in 2010 in a studio-flat kitchen at ETH Zurich (EU "
        "project OPPORTUNITY): 4 subjects, each performing 5 runs of a loosely scripted "
        "morning routine (ADL) and 1 drill run of 20 repetitions of a fixed sequence, "
        "with body-worn, object and ambient sensors (Roggen et al. 2010).",
        "dataCollectionType": "Wearable and ambient sensor recordings of human subjects "
        "in a laboratory.",
        "dataCollectionTimeframe": "2010",
        "dataPreprocessingProtocol": "Source values are integer-rounded by the providers "
        "(see source column descriptions); cast to float32 without other change. "
        "NaN (packet loss) kept. Labels re-indexed per track (0 = Null).",
        "dataAnnotationProtocol": "Labels annotated offline by the dataset creators, from "
        "video recordings of the sessions, on 7 tracks of different semantics: modes of "
        "locomotion, high-level activities (the ADL script situations), low-level "
        "actions of each arm and the object they handle, mid-level gestures of both "
        "arms (Roggen et al. 2010; Chavarriaga et al. 2013). The Null class means that "
        "none of the classes of the track is being performed.",
        "dataAnnotationPlatform": "Offline video annotation tool of the OPPORTUNITY project "
        "(Calatroni et al. 2011).",
        "dataAnnotationAnalysis": "No inter-annotator agreement available: each track was "
        "annotated once. The source paper notes that start and end times of gestures "
        "are subjectively assessed by the person labelling. Statistics computed by the "
        "builder (Null share, segments, recurrence of states) are in the dataset card.",
        "annotationsPerItem": "One label per sample and per track.",
        "annotatorDemographics": "Not documented (members of the project).",
        "dataLimitations": "Only 4 subjects; wireless sensors suffer packet loss (NaN, "
        "about 4 % of all values); duplicated axis names in the source (fixed, see "
        "axis_fixes); slight time stamp jitter. High-level activities follow the ADL "
        "script, so their order is nearly fixed. Not suited to population-level claims.",
        "dataBiases": "Single kitchen environment, young adult subjects, scripted "
        "routine: over-represents one culture of morning activities.",
        "personalSensitiveInformation": "Motion data of pseudonymous subjects (S1-S4); "
        "no demographic attribute is released with the data.",
        "dataUseCases": "Activity recognition, state detection with a null class, "
        "multi-track (hierarchical) segmentation, CPD from label changes. Validity "
        "established by the Opportunity challenge for locomotion and gestures; the "
        "high-level track is mostly scripted.",
        "dataSocialImpact": "Positive: ambient assisted living research. Risk: activity "
        "monitoring can be used for surveillance; the data itself is low-risk.",
        "hasSyntheticData": False,
        "dataReleaseMaintenancePlan": "Versioned with the tsseg-data repository; rebuilt "
        "from the UCI archive (pinned sha256). Issues: tsseg-data issue tracker.",
    }
    cite = ("@inproceedings{roggen2010opportunity, title={Collecting complex activity "
            "datasets in highly rich networked sensor environments}, author={Roggen, "
            "Daniel and Calatroni, Alberto and Rossi, Mirco and Holleczek, Thomas and "
            "F{\\\"o}rster, Kilian and Tr{\\\"o}ster, Gerhard and Lukowicz, Paul and "
            "Bannach, David and Pirkl, Gerald and Ferscha, Alois and others}, "
            "booktitle={Seventh International Conference on Networked Sensing Systems "
            "(INSS)}, pages={233--240}, year={2010}}\n"
            "@article{chavarriaga2013opportunity, title={The Opportunity challenge: A "
            "benchmark database for on-body sensor-based activity recognition}, "
            "author={Chavarriaga, Ricardo and Sagha, Hesam and Calatroni, Alberto and "
            "Digumarti, Sundara Tejaswi and Tr{\\\"o}ster, Gerhard and Mill{\\'a}n, "
            "Jos{\\'e} del R. and Roggen, Daniel}, journal={Pattern Recognition Letters}, "
            "volume={34}, number={15}, pages={2033--2042}, year={2013}}\n"
            "@misc{opportunity_uci, author={Roggen, Daniel and Calatroni, Alberto and "
            "Nguyen-Dinh, Long-Van and Chavarriaga, Ricardo and Sagha, Hesam}, "
            "title={OPPORTUNITY Activity Recognition}, year={2012}, "
            "howpublished={UCI Machine Learning Repository}, doi={10.24432/C5M027}}")
    meta = DatasetMetadata(
        name=ID,
        description="OPPORTUNITY activity recognition: 4 subjects x (5 ADL runs + 1 drill "
        "run) in a sensor-rich kitchen; 242 body, object and ambient channels at 30 Hz; "
        "7 label tracks (locomotion, high-level activities, low-level arm actions and "
        "objects, mid-level gestures), each with an explicit Null class. Converted to "
        "the tsseg-data format (one Parquet row per run).",
        url=f"https://huggingface.co/datasets/{HF_NAMESPACE}/{ID}",
        license_url="https://spdx.org/licenses/CC-BY-4.0.html",
        license_spdx="CC-BY-4.0",
        cite_as=cite,
        creators=["Roggen, Daniel", "Calatroni, Alberto", "Nguyen-Dinh, Long-Van",
                  "Chavarriaga, Ricardo", "Sagha, Hesam"],
        date_published="2012-08-02",
        version="1.0.0",
        keywords=["human activity recognition", "state detection", "null class",
                  "multi-track labels", "time series segmentation"],
        derived_from=[{"@id": f"https://doi.org/{DOI}",
                       "name": "OPPORTUNITY Activity Recognition (UCI ML Repository)"}],
        activities=[
            Activity("data collection", rai["dataCollection"],
                     agents=["OPPORTUNITY project (ETH Zurich, JKU Linz, Univ. Passau...)"],
                     extra={"rai:dataCollectionTimeframe": "2010"}),
            Activity("data annotation", rai["dataAnnotationProtocol"] + " "
                     + rai["dataAnnotationAnalysis"], agents=["OPPORTUNITY project annotators"]),
            Activity("preprocessing", f"tsseg-data builders/{ID}.py: .dat text -> Parquet, "
                     "values unchanged (float32 cast of integer-rounded source values), "
                     "labels re-indexed per track with 0 = Null, the 24 repeated 'accX' "
                     "object-sensor columns renamed accX/accY/accZ by position, source "
                     f"sha256 {SHA256}.", agents=["tsseg-data"],
                     used=[f"https://doi.org/{DOI}"]),
        ],
        rai=rai,
        field_descriptions={
            **{c: f"Sensor channel '{source_cols[c]['source_description']}' (source "
                  f"column {source_cols[c]['source_column']}), unit {units[c]}; NaN = "
                  "packet loss." for c in channels},
            "t_ms": "Time since the start of the run (ms).",
            "subject": "Subject id (S1-S4).",
            "session": "Run (ADL1-ADL5 or Drill).",
        },
        tsseg={"tracks": info["tracks"], "defaultLabel": "label_locomotion",
               "sourceSha256": SHA256},
    )
    card = {
        "pretty_name": "OPPORTUNITY Activity Recognition",
        "hf_license": "cc-by-4.0",
        "tags": ["time-series", "state-detection", "change-point-detection",
                 "time-series-segmentation", "human-activity-recognition", "null-class",
                 "multi-track", "tsseg"],
        "size_category": "n<1K",
        "annotations_creators": ["expert-generated"],
        "summary": "Body-worn, object and ambient sensor recordings of 4 subjects "
        "performing a morning routine in a kitchen, labelled on 7 tracks of different "
        "granularity, each with a Null class. A reference HAR benchmark whose locomotion "
        "and gesture tracks give recurrent states and a realistic null class for state "
        "detection.",
        "facts": facts,
        "labels": "Seven tracks, `label_<track>`, with ids 0 = Null and 1..k = the source "
        "classes in increasing source code (names and source codes in `tsseg.json`, "
        "`state_names` and `state_source_codes`). Null is an ordinary state, listed in "
        "`null_states`; there is no `-1` in this dataset (every sample is annotated). "
        "Default ground truth: `label_locomotion`. Masking Null is an analysis option, "
        "not the default.\n\n" + track_table,
        "annotation": rai["dataAnnotationProtocol"] + "\n\n" + rai["dataAnnotationAnalysis"]
        + " Label origin: `human`.",
        "conversion": "\n".join([
            f"- Source: UCI archive `opportunity+activity+recognition.zip`, sha256 `{SHA256}`.",
            "- One row per run (no run exceeds 1 h); channel values unchanged (float32), "
            "NaN kept; time stamps from the source MILLISEC column.",
            "- Channel names derived from the source descriptions (`acc_`, `imu_`, `reed_`, "
            "`loc_` prefixes; `^` -> `_up`, `_` -> `_lo` for the two sensors at one body "
            "position). The source repeats `accX` three times for each of the 12 object "
            "sensors; they are renamed `accx`/`accy`/`accz` by position, following the "
            "documentation (3D acceleration + 2D gyroscope per object). All 24 fixes are "
            "listed in `tsseg.json` (`axis_fixes`), with every source column number.",
            "- Splits: `train` / `test` of the Opportunity challenge (test = ADL4, ADL5 of "
            "S2, S3, S4). Many papers use instead S2, S3 ADL4-5 as test and drop S4.",
            f"- Rebuild: `python -I builders/{ID}.py` in tsseg-data.",
        ]),
        "license": "CC BY 4.0 (UCI Machine Learning Repository). Attribution: Roggen et al. "
        "The conversion code is MIT.",
        "citation": "```bibtex\n" + cite + "\n```",
    }
    finalize(args.out_dir, spec, info, meta, card, summary, {
        "default": "15 accelerometer channels of the 5 wired upper-body IMUs (back, "
                   "both upper and lower arms), all label tracks.",
        "full": "all 242 sensor channels, all label tracks.",
    })
    print(f"{ID}: {len(lengths)} runs", {k: v["bytes"] for k, v in summary.items()})


if __name__ == "__main__":
    main()
