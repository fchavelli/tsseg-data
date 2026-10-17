"""Build mozilla-perf-cpd-annotations (Besbes et al., Zenodo 10.5281/zenodo.20382322).

174 Firefox performance series (Perfherder), change points annotated independently
by 4 to 7 of 11 Mozilla performance engineers. Pure CPD, several annotators.

Run from the repository root (isolated mode, the source is a download)::

    python -I builders/mozilla-perf-cpd-annotations.py [--raw-dir DIR] [--out build]
"""

from __future__ import annotations

import csv
import io
import json
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
from tsseg_data.labels import f1_cps, pairwise, tcpd_f1  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "mozilla-perf-cpd-annotations"
URL = "https://zenodo.org/api/records/20382322/files/dataset.zip/content"
SHA256 = "715ef0f3c08b9e3d582dbe570dbe832d4f4a1772ef033079f07a58cdfc82a746"
MD5_ZENODO = "7b228bbf49422aefa4bffae3548a1c5e"
DOI = "10.5281/zenodo.20382322"
ROOT = "190382791/"
DEFAULT_TYPES = ["mean", "mean_variance"]  # the authors exclude "variance"
MARGIN = 5
META = {
    "application": pa.string(),
    "repository": pa.string(),
    "framework": pa.int32(),
    "suite": pa.string(),
    "test": pa.string(),
    "platform": pa.string(),
    "measurement_unit": pa.string(),
    "lower_is_better": pa.bool_(),
    "tags": pa.string(),
    "first_timestamp": pa.timestamp("ms"),
    "last_timestamp": pa.timestamp("ms"),
}


def main() -> None:
    args = parse_args(ID)
    raw = fetch(URL, "dataset.zip", SHA256, args.raw_dir, ID)
    outer = zipfile.ZipFile(raw)
    inner = zipfile.ZipFile(io.BytesIO(outer.read(ROOT + "timeseries.zip")))
    attrs = json.loads(outer.read(ROOT + "timeseries_attributes_polished.json"))
    ann_rows = list(csv.DictReader(io.StringIO(
        outer.read(ROOT + "annotations_anonymized.csv").decode())))
    task_rows = list(csv.DictReader(io.StringIO(
        outer.read(ROOT + "tasks_anonymized.csv").decode())))

    def ann_id(user: str) -> str:
        return f"u{int(user):02d}"

    annotators = sorted({ann_id(r["UserID"]) for r in task_rows})
    # (series, annotator) -> list of (cp, type); "no_cp" rows -> empty list
    cps: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for r in task_rows:
        cps[(r["DatasetName"], ann_id(r["UserID"]))] = []
    for r in ann_rows:
        key = (r["DatasetName"], ann_id(r["UserID"]))
        assert key in cps, key
        if r["AnnotationIndex"] != "no_cp":
            cps[key].append((int(r["AnnotationIndex"]), r["AnnotationType"]))

    series = {}
    for info in inner.infolist():
        if not (info.filename.startswith("timeseries/") and info.filename.endswith(".json")):
            continue
        d = json.loads(inner.read(info))
        assert d["n_dim"] == 1 and len(d["series"]) == 1
        values = np.asarray(d["series"][0]["raw"], dtype=np.float64)
        ts = pd.to_datetime(d["time"]["raw"], format=d["time"]["format"]).to_numpy(
            "datetime64[ms]")
        assert list(d["time"]["index"]) == list(range(len(values))) and d["n_obs"] == len(values)
        series[d["name"]] = (values, ts)

    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=["value"],
        configs={"default": ["value"]},
        sampling_rate_hz=None,
        channel_type=pa.float64(),
        time_column=("timestamp", pa.timestamp("ms")),
        cp_annotators=annotators,
        meta_columns=META,
    )
    dropped = []
    agree_rows = []
    with DatasetWriter(args.out_dir, spec) as w:
        for sid in sorted(series, key=int):
            values, ts = series[sid]
            n = len(values)
            a = attrs.get(sid, {})
            per = {}
            for ann in annotators:
                if (sid, ann) not in cps:
                    continue
                pts = sorted(set(cps[(sid, ann)]))
                keep = [(c, t) for c, t in pts if 0 < c < n]
                dropped += [(sid, ann, c) for c, t in pts if not 0 < c < n]
                assert len({c for c, _ in keep}) == len(keep), (sid, ann, "two types at one CP")
                per[ann] = (np.array([c for c, _ in keep], dtype=np.int32),
                            [t for _, t in keep])
            w.add_series(
                sid,
                {"value": values},
                time=ts,
                cps=per,
                annotators=sorted(per),
                meta={
                    **{k: a.get(k) for k in META if k in a},
                    "first_timestamp": ts[0],
                    "last_timestamp": ts[-1],
                },
            )
            sets = {k: v[0][np.isin(v[1], DEFAULT_TYPES)] for k, v in per.items()}
            agree_rows.append({
                "pairwise_f1": float(np.mean(pairwise(sets, lambda x, y: f1_cps(x, y, MARGIN)))),
                "one_vs_rest_tcpd_f1": float(np.mean([
                    tcpd_f1([sets[o] for o in sets if o != k], sets[k], MARGIN) for k in sets])),
                "n_annotators": len(sets),
            })
    summary = w.summary()
    assert not dropped, dropped[:5]

    tasks = pd.DataFrame({
        "series_id": [r["DatasetName"] for r in task_rows],
        "annotator": [ann_id(r["UserID"]) for r in task_rows],
        "task_id": [int(r["TaskID"]) for r in task_rows],
        "difficulty": [float(r["Difficulty"]) if r["Difficulty"] else np.nan for r in task_rows],
        "time_spent_ms": [float(r["TimeSpent"]) if r["TimeSpent"] else np.nan for r in task_rows],
    }).sort_values(["series_id", "annotator"])
    tasks.to_parquet(args.out_dir / "tasks.parquet", index=False, compression="zstd")

    # ---- statistics and agreement
    ag = pd.DataFrame(agree_rows)
    lengths = np.array([len(v[0]) for v in series.values()])
    types = pd.Series([t for v in cps.values() for _, t in v]).value_counts().to_dict()
    n_cps_default = [len(v) for k, v in cps.items()]
    agreement = {
        "margin_points": MARGIN,
        "change_types": DEFAULT_TYPES,
        "pairwise_f1_mean": round(float(ag.pairwise_f1.mean()), 3),
        "one_vs_rest_tcpd_f1_mean": round(float(ag.one_vs_rest_tcpd_f1.mean()), 3),
        "paper_reported_f1": 0.76,
    }
    info = {
        "label_type": "cps",
        "domain": "software performance",
        "sampling": "irregular: one measurement per build / push; treated as a sequence",
        "time_description": "push / build time (UTC, naive)",
        "units": {"value": "per series, see index column measurement_unit (mostly ms)"},
        "annotators": annotators,
        "tracks": None,
        "default_label": None,
        "default_change_types": DEFAULT_TYPES,
        "change_types": sorted(types),
        "cp_convention": "0-based index of the annotated point (TCPD annotation tool), "
        "kept as is; the TCPD F1 of the paper (0.76) is reproduced with it",
        "null_states": {},
        "state_names": {},
        "label_descriptions": {},
        "label_origin": "human",
        "splits": None,
        "agreement": agreement,
        "source": {"url": URL, "doi": DOI, "sha256": SHA256, "md5_zenodo": MD5_ZENODO},
    }

    n_ser = len(series)
    facts = "\n".join([
        "| | |", "|---|---|",
        "| Task | change point detection (pure CPD, several annotators) |",
        "| Domain | software performance (Firefox CI, Perfherder) |",
        f"| Series | {n_ser} univariate |",
        f"| Length | {lengths.min()} - {lengths.max()} points (median {int(np.median(lengths))}) |",
        "| Sampling | irregular, one point per build; `timestamp` column |",
        f"| Annotators | {len(annotators)} engineers, 4-7 per series |",
        f"| Change points | {sum(types.values())} annotations ({', '.join(f'{k} {v}' for k, v in types.items())}) |",
        f"| Agreement | pairwise F1@{MARGIN} {agreement['pairwise_f1_mean']}, one-vs-rest TCPD F1 {agreement['one_vs_rest_tcpd_f1_mean']} |",
        "| License | CC BY 4.0 |",
        f"| Source | [doi:{DOI}](https://doi.org/{DOI}) |",
    ])
    rai = {
        "dataCollection": "Perfherder measurements of Firefox performance tests from May "
        "2023 to May 2024, selected by the authors from the Mozilla performance time "
        "series dataset (doi:10.5281/zenodo.15465568).",
        "dataCollectionType": "Software telemetry from continuous integration (automated "
        "performance tests), no human subjects.",
        "dataCollectionTimeframe": "2023-05 to 2024-05",
        "dataPreprocessingProtocol": "Source JSON (TCPD format) converted to Parquet without "
        "changing any value; annotations regrouped per (series, annotator).",
        "dataAnnotationProtocol": "Each series was annotated independently by several Mozilla "
        "performance engineers in a TCPD-style web tool (van den Burg & Williams 2020): "
        "click the points where the behaviour changes, type each change (mean, variance, "
        "mean_variance) or state that there is no change (no_cp). The authors exclude "
        "variance-only changes from their evaluation because of low agreement.",
        "dataAnnotationPlatform": "TCPD-style annotation web tool.",
        "dataAnnotationAnalysis": f"Agreement computed by the builder on the default change "
        f"types ({', '.join(DEFAULT_TYPES)}), margin {MARGIN} points: mean pairwise F1 "
        "(index 0 added to both sets, TCPD convention) "
        f"{agreement['pairwise_f1_mean']}, mean one-vs-rest TCPD F1 "
        f"{agreement['one_vs_rest_tcpd_f1_mean']} (paper: 0.76). All annotations are kept, "
        "with their type; no consensus is defined by the source.",
        "annotationsPerItem": "4 to 7 annotators per series (median 6).",
        "annotatorDemographics": f"{len(annotators)} Mozilla performance engineers "
        "(pseudonymous ids u04-u16); no other information released.",
        "dataLimitations": "Irregular sampling (one point per build), treated as a sequence; "
        "series pre-selected around performance alerts; variance-type annotations have "
        "low agreement. Not suited to forecasting or to assessing CPD methods on "
        "physical signals.",
        "dataBiases": "Selection bias: series were chosen from tests that raised alerts. "
        "Annotators are Mozilla staff who may know the alert history (label bias).",
        "personalSensitiveInformation": "None: software measurements; annotator ids are "
        "pseudonymised by the source.",
        "dataUseCases": "Benchmarking CPD methods against several human annotations "
        "(TCPD-style F1 / covering). Validity established by the source paper for "
        "offline CPD evaluation; not established for online alerting.",
        "dataSocialImpact": "Low. May help maintain software performance; no "
        "foreseeable misuse.",
        "hasSyntheticData": False,
        "dataReleaseMaintenancePlan": "Versioned with the tsseg-data repository; rebuilt "
        "from the pinned Zenodo record. Issues: tsseg-data issue tracker.",
    }
    meta = DatasetMetadata(
        name=ID,
        description="174 Mozilla Firefox performance time series (Perfherder, 2023-2024) "
        "with change points annotated independently by 4 to 7 of 11 Mozilla performance "
        "engineers and typed as mean / variance / mean_variance shifts. Converted to the "
        "tsseg-data format (one Parquet row per series, change points per annotator).",
        url=f"https://huggingface.co/datasets/{HF_NAMESPACE}/{ID}",
        license_url="https://spdx.org/licenses/CC-BY-4.0.html",
        license_spdx="CC-BY-4.0",
        cite_as="@misc{besbes2026mozillacpd_data, author={Besbes, Mohamed Bilel and Costa, "
        "Diego Elias}, title={Exploring Statistical Change Point Detection Techniques for "
        "Performance Anomaly Detection at Mozilla (dataset)}, year={2026}, "
        "publisher={Zenodo}, doi={10.5281/zenodo.20382322}}",
        creators=["Besbes, Mohamed Bilel", "Costa, Diego Elias"],
        date_published="2026-05-25",
        version="1.0.0",
        keywords=["change point detection", "software performance", "multi-annotator",
                  "time series segmentation"],
        derived_from=[{"@id": f"https://doi.org/{DOI}",
                       "name": "Mozilla performance CPD annotations (Zenodo)"}],
        activities=[
            Activity("data collection", rai["dataCollection"],
                     agents=["Mozilla Perfherder"], used=["https://doi.org/10.5281/zenodo.15465568"],
                     extra={"rai:dataCollectionTimeframe": rai["dataCollectionTimeframe"]}),
            Activity("data annotation", rai["dataAnnotationProtocol"] + " " +
                     rai["dataAnnotationAnalysis"],
                     agents=["11 Mozilla performance engineers", "TCPD-style annotation tool"]),
            Activity("preprocessing", f"tsseg-data builders/{ID}.py: JSON -> Parquet "
                     "(values and change point indices unchanged), annotations regrouped "
                     "per annotator, task table kept. Source sha256 " + SHA256 + ".",
                     agents=["tsseg-data"], used=[f"https://doi.org/{DOI}"]),
        ],
        rai=rai,
        field_descriptions={
            "value": "Performance measurement (unit: index column measurement_unit).",
            "timestamp": "Push / build time of each measurement.",
            "difficulty": "Difficulty rated by the annotator.",
            "time_spent_ms": "Time spent on the annotation task (ms).",
        },
        auxiliary={"tasks.parquet": "One row per (series, annotator) annotation task: "
                   "difficulty, time spent."},
        tsseg={"annotators": annotators, "defaultChangeTypes": DEFAULT_TYPES,
               "sourceSha256": SHA256, "agreement": agreement},
    )
    card = {
        "pretty_name": "Mozilla performance change point annotations",
        "hf_license": "cc-by-4.0",
        "tags": ["time-series", "change-point-detection", "time-series-segmentation",
                 "multi-annotator", "software-performance", "tsseg"],
        "size_category": "n<1K",
        "annotations_creators": ["expert-generated"],
        "summary": "174 performance time series of Firefox (Perfherder, May 2023 - May "
        "2024) in which 4 to 7 Mozilla performance engineers independently marked the "
        "change points and typed them (mean, variance, mean and variance). A recent, "
        "real-world CPD benchmark with several human annotations per series, in the "
        "style of TCPD.",
        "facts": facts,
        "labels": "Change points only (no dense states). Each annotator column "
        "`cps_<annotator>` lists the annotated points and `cp_types_<annotator>` their "
        f"types. Default evaluation keeps types {DEFAULT_TYPES} (the authors drop "
        "`variance`, whose agreement is low): an annotator who marked only variance "
        "changes then has no change point, which differs from an annotator who did not "
        "see the series (null). There is no consensus; evaluate against all annotators "
        "(TCPD F1 / covering).",
        "annotation": rai["dataAnnotationProtocol"] + "\n\n" + rai["dataAnnotationAnalysis"]
        + " Label origin: `human`. The per-task difficulty and time spent are in "
        "`tasks.parquet`.",
        "conversion": "\n".join([
            f"- Source: `dataset.zip` of [doi:{DOI}](https://doi.org/{DOI}), sha256 `{SHA256}`.",
            "- Values, time stamps and change point indices are unchanged; one row per "
            "series, ordered by numeric series id.",
            "- No annotation falls at index 0 or beyond the series end (checked).",
            f"- Rebuild: `python -I builders/{ID}.py` in tsseg-data.",
        ]),
        "license": "CC BY 4.0 (source: Zenodo record). Attribution: Besbes, Costa et al. "
        "The conversion code is MIT.",
        "citation": "```bibtex\n" + meta.cite_as + "\n```\n\nPaper: Besbes et al., "
        "arXiv:2606.18377 (author list to verify before publication).",
    }
    finalize(args.out_dir, spec, info, meta, card, summary,
             {"default": "the univariate series with time stamps and all annotations."})
    print(f"{ID}: {n_ser} series, {summary['default']['bytes']} bytes, agreement {agreement}")


if __name__ == "__main__":
    main()
