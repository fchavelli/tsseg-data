"""Shared reporting for source builders: measured statistics and provenance."""

from __future__ import annotations

import numpy as np

from .build import HF_NAMESPACE, finalize
from .croissant import Activity, DatasetMetadata
from .labels import runs


class Statistics:
    """Count recurrence within each series, excluding missing ground truth."""

    def __init__(self):
        self.rows = []

    def add(self, series_id, labels):
        row = {"series_id": series_id, "length": len(next(iter(labels.values())))}
        for track, y in labels.items():
            values, _, lengths = runs(y)
            known = values[values != -1]
            _, counts = np.unique(known, return_counts=True)
            row[track] = {
                "segments": len(values),
                "labelled_segments": len(known),
                "states": len(counts),
                "recurrent": bool(np.any(counts > 1)),
                "recurrent_states": int(np.count_nonzero(counts > 1)),
                "missing_samples": int(np.count_nonzero(y == -1)),
                "min_segment_length": int(lengths.min()),
            }
        self.rows.append(row)

    def summary(self):
        lengths = [r["length"] for r in self.rows]
        result = {
            "n_series": len(lengths),
            "samples": sum(lengths),
            "length_min": min(lengths),
            "length_median": float(np.median(lengths)),
            "length_max": max(lengths),
            "tracks": {},
        }
        for track in self.rows[0].keys() - {"series_id", "length"}:
            values = [r[track] for r in self.rows]
            result["tracks"][track] = {
                "segments": sum(v["segments"] for v in values),
                "series_with_recurrence": sum(v["recurrent"] for v in values),
                "missing_share": sum(v["missing_samples"] for v in values)
                / sum(lengths),
                "min_segment_length": min(v["min_segment_length"] for v in values),
            }
        return result


def finish(
    args,
    spec,
    writer,
    stats,
    *,
    title,
    source,
    sha256,
    license_spdx,
    license_url,
    license_evidence,
    description,
    collection,
    annotation,
    conversion,
    limitations,
    biases,
    personal,
    citation,
    creators,
    date_published,
    info=None,
    null_states=None,
    synthetic=False,
):
    """Write card and Croissant from explicit source facts and measured counts."""
    measured = stats.summary()
    labels = list(spec.label_columns)
    null_states = null_states or {}
    evidence = {"date": "2026-10-18", "url": license_evidence, "license": license_spdx}
    if info and info.get("license_scope"):
        evidence["scope"] = info["license_scope"]
        evidence["rehosting_allowed"] = info.get("rehosting_allowed", False)
    info = {
        "label_type": "states",
        "default_label": labels[0],
        "label_origin": "human",
        "label_descriptions": {c: c for c in labels},
        "null_states": null_states,
        "agreement": None,
        "source": {"url": source, "sha256": sha256},
        "license_verification": evidence,
        "statistics": measured,
        "series_statistics": stats.rows,
        **(info or {}),
    }
    rai = {
        "dataCollection": collection,
        "dataAnnotationProtocol": annotation,
        "dataAnnotationAnalysis": "Measured segment counts, missing share and state recurrence "
        "are reported per track and series. No independent annotator tracks are available; "
        "inter-annotator agreement cannot be computed.",
        "dataPreprocessingProtocol": conversion,
        "dataLimitations": limitations,
        "dataBiases": biases,
        "personalSensitiveInformation": personal,
        "dataUseCases": "Change point detection and state detection; recurrence counts "
        "are reported separately for each label track.",
        "dataSocialImpact": "Research use; evaluate generalisation before operational use.",
        "hasSyntheticData": synthetic,
        "dataReleaseMaintenancePlan": "Versioned source builder in tsseg-data; no publication yet.",
    }
    meta = DatasetMetadata(
        name=spec.id,
        description=description,
        url=f"https://huggingface.co/datasets/{HF_NAMESPACE}/{spec.id}",
        license_url=license_url,
        license_spdx=license_spdx,
        cite_as=citation,
        creators=creators,
        date_published=date_published,
        version="1.0.0",
        keywords=[
            "time series segmentation",
            "change point detection",
            "state detection",
        ],
        derived_from=[{"@id": source, "name": title}]
        + (
            [{"@id": info["reference_doi"], "name": "Source publication"}]
            if info.get("reference_doi")
            else []
        ),
        activities=[
            Activity("data collection", collection, agents=creators),
            Activity("data annotation", annotation, agents=creators),
            Activity("preprocessing", conversion, agents=["tsseg-data"], used=[source]),
        ],
        rai=rai,
        auxiliary=info.get("auxiliary", {}),
        tsseg={"licenseVerification": evidence, "sourceSha256": sha256},
    )
    facts = [
        "| Property | Value |",
        "|---|---|",
        f"| Series | {measured['n_series']} |",
        f"| Samples | {measured['samples']} |",
        f"| Length min / median / max | {measured['length_min']} / "
        f"{measured['length_median']:g} / {measured['length_max']} |",
        f"| Channels | {len(spec.channels)} |",
        f"| Sampling | {spec.sampling_rate_hz or 'not specified'} Hz |",
    ]
    track_table = [
        "| Track | Segments | Series with recurrent states | Unlabelled share |",
        "|---|---|---|---|",
    ]
    for track, v in measured["tracks"].items():
        track_table.append(
            f"| {track} | {v['segments']} | "
            f"{v['series_with_recurrence']}/{measured['n_series']} | "
            f"{v['missing_share']:.3%} |"
        )
    license_text = (
        f"{license_spdx}. Verified at the primary source on 2026-10-18: "
        f"[{license_evidence}]({license_evidence}). Conversion code: MIT."
    )
    if info.get("license_scope"):
        license_text += " " + info["license_scope"]
    card = {
        "pretty_name": title,
        "hf_license": info.get("hf_license", license_spdx.lower()),
        "tags": ["time-series", "state-detection", "change-point-detection", "tsseg"],
        "size_category": "n<1K",
        "annotations_creators": ["expert-generated"],
        "summary": description,
        "facts": "\n".join(facts),
        "labels": annotation
        + "\n\n"
        + "\n".join(track_table)
        + "\n\nMissing ground truth uses -1. Null/transition classes stay ordinary "
        "states unless the source explicitly excludes them. Recurrence counts "
        "a state appearing in two or more separated segments within one series; "
        "missing labels are excluded. Per-series statistics are in tsseg.json.",
        "annotation": annotation + " No independent annotator tracks are available; "
        "inter-annotator agreement cannot be computed.",
        "conversion": conversion + f"\n\nSource SHA256: `{sha256}`. "
        f"Rebuild: `python -I builders/{spec.id}.py`.",
        "license": license_text,
        "citation": citation,
    }
    finalize(
        args.out_dir,
        spec,
        info,
        meta,
        card,
        writer.summary(),
        {c: "Source sensor channels and all label tracks." for c in spec.configs},
    )
    print(measured, flush=True)
