"""Croissant metadata (core 1.0 + Responsible AI) generated from a built dataset.

The record sets and fields are derived from the Parquet schemas actually written,
so the metadata cannot drift from the files. Builders supply the descriptive part
(``DatasetMetadata``): citation, license, provenance, RAI texts, annotation
documentation.

NeurIPS Evaluations & Datasets track (2026) requires, per dataset, the Croissant
core fields and the minimal RAI fields listed in ``REQUIRED_RAI``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .sources import sha256

__all__ = [
    "CONTEXT",
    "CONFORMS_TO",
    "REQUIRED_RAI",
    "RECOMMENDED_RAI",
    "DatasetMetadata",
    "Activity",
    "build_croissant",
    "write_croissant",
]

CONFORMS_TO = [
    "http://mlcommons.org/croissant/1.0",
    "http://mlcommons.org/croissant/RAI/1.0",
]

CONTEXT = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "prov": "http://www.w3.org/ns/prov#",
    "tsseg": "https://github.com/fchavelli/tsseg-data/ns#",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "equivalentProperty": "cr:equivalentProperty",
    "dct": "http://purl.org/dc/terms/",
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileProperty": "cr:fileProperty",
    "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "samplingRate": "cr:samplingRate",
    "sc": "https://schema.org/",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}

# Minimal RAI set of the NeurIPS 2026 E&D hosting guidelines.
REQUIRED_RAI = [
    "rai:dataLimitations",
    "rai:dataBiases",
    "rai:personalSensitiveInformation",
    "rai:dataUseCases",
    "rai:dataSocialImpact",
    "rai:hasSyntheticData",
    "prov:wasDerivedFrom",
    "prov:wasGeneratedBy",
]
# Filled for every dataset of the collection (annotation documentation, upkeep).
RECOMMENDED_RAI = [
    "rai:dataCollection",
    "rai:dataCollectionType",
    "rai:dataCollectionTimeframe",
    "rai:dataPreprocessingProtocol",
    "rai:dataAnnotationProtocol",
    "rai:dataAnnotationPlatform",
    "rai:dataAnnotationAnalysis",
    "rai:annotationsPerItem",
    "rai:annotatorDemographics",
    "rai:dataReleaseMaintenancePlan",
]

PARQUET = "application/x-parquet"


@dataclass
class Activity:
    """One ``prov:Activity`` of ``prov:wasGeneratedBy``.

    ``kind`` is one of ``data collection``, ``data annotation``, ``preprocessing``.
    """

    kind: str
    description: str
    agents: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_jsonld(self, i: int) -> dict:
        d = {
            "@type": "prov:Activity",
            "@id": f"activity/{i}-{self.kind.replace(' ', '-')}",
            "name": self.kind,
            "description": self.description,
        }
        if self.agents:
            d["prov:wasAssociatedWith"] = [
                {"@type": "prov:Agent", "name": a} for a in self.agents
            ]
        if self.used:
            d["prov:used"] = [{"@id": u} for u in self.used]
        d.update(self.extra)
        return d


@dataclass
class DatasetMetadata:
    """Descriptive metadata a builder supplies for its dataset."""

    name: str
    description: str
    url: str
    license_url: str
    license_spdx: str
    cite_as: str
    creators: list[str]
    date_published: str
    version: str
    keywords: list[str]
    derived_from: list[dict]  # [{"@id": uri, "name": ...}]; primary source with DOI first
    activities: list[Activity]
    rai: dict  # keys without the "rai:" prefix
    field_descriptions: dict[str, str] = field(default_factory=dict)
    record_set_descriptions: dict[str, str] = field(default_factory=dict)
    auxiliary: dict[str, str] = field(default_factory=dict)  # file -> description
    tsseg: dict = field(default_factory=dict)
    publisher: str | None = None
    same_as: list[str] = field(default_factory=list)


def _datatype(t: pa.DataType) -> tuple[str, bool]:
    repeated = False
    if pa.types.is_list(t) or pa.types.is_large_list(t):
        t, repeated = t.value_type, True
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "sc:Text", repeated
    if pa.types.is_boolean(t):
        return "sc:Boolean", repeated
    if pa.types.is_integer(t):
        return "sc:Integer", repeated
    if pa.types.is_floating(t):
        return "sc:Float", repeated
    if pa.types.is_timestamp(t) or pa.types.is_date(t):
        return "sc:DateTime", repeated
    raise TypeError(f"no Croissant type for {t}")


def _fields(rs: str, src: dict, schema: pa.Schema, desc: dict[str, str]) -> list[dict]:
    out = []
    for f in schema:
        dt, repeated = _datatype(f.type)
        d = {
            "@type": "cr:Field",
            "@id": f"{rs}/{f.name}",
            "name": f.name,
            "description": desc.get(f.name) or _default_description(f.name),
            "dataType": dt,
            "source": {**src, "extract": {"column": f.name}},
        }
        if repeated:
            d["repeated"] = True
        out.append(d)
    return out


def _default_description(col: str) -> str:
    fixed = {
        "series_id": "Series identifier (stable across configs and versions).",
        "chunk_idx": "Chunk number within the series (0 for unchunked series).",
        "chunk_start": "Offset of the chunk in the series, in samples.",
        "length": "Number of samples in this row (chunk length).",
        "n_channels": "Number of channels of the series (full config).",
        "n_chunks": "Number of rows (chunks) the series is split into.",
        "split": "Source-defined split, if any (null otherwise).",
        "label_columns": "Dense label columns available for the series.",
        "annotators": "Annotators who labelled the series.",
    }
    if col in fixed:
        return fixed[col]
    if col.startswith("label_"):
        return (f"Dense labels '{col[6:]}' (one integer per sample); -1 = no ground "
                "truth. State names in tsseg.json.")
    if col.startswith("n_changes_"):
        return f"Number of label changes of label_{col[10:]} over the whole series."
    if col.startswith("n_cps_"):
        return f"Number of change points of annotator {col[6:]} (null = not annotated)."
    if col.startswith("cps_"):
        return (f"Change points of annotator {col[4:]}: 0-based index of the first "
                "point of the new segment (null = not annotated, empty = no change).")
    if col.startswith("cp_types_"):
        return f"Type of each change point of annotator {col[9:]}."
    if col.startswith("files_"):
        return f"Part files of config '{col[6:]}' holding the series."
    return col


def build_croissant(root: Path, meta: DatasetMetadata, configs: list[str]) -> dict:
    """Croissant JSON-LD for the dataset built in ``root``."""
    root = Path(root)
    distribution = [
        {
            "@type": "cr:FileObject",
            "@id": "index.parquet",
            "name": "index.parquet",
            "description": "One row per series: length, channels, chunks, split, "
            "label columns, annotators, per-label change counts, part files.",
            "contentUrl": "index.parquet",
            "encodingFormat": PARQUET,
            "sha256": sha256(root / "index.parquet"),
        }
    ]
    record_sets = [
        {
            "@type": "cr:RecordSet",
            "@id": "index",
            "name": "index",
            "description": "One record per series.",
            "key": {"@id": "index/series_id"},
            "field": _fields("index", {"fileObject": {"@id": "index.parquet"}},
                             pq.read_schema(root / "index.parquet"),
                             meta.field_descriptions),
        }
    ]
    for cfg in configs:
        fs = f"data-{cfg}"
        distribution.append(
            {
                "@type": "cr:FileSet",
                "@id": fs,
                "name": fs,
                "description": f"Parquet part files of config '{cfg}' "
                "(one row per series or per one-hour chunk).",
                "encodingFormat": PARQUET,
                "includes": f"data/{cfg}/*.parquet",
            }
        )
        schema = pq.read_schema(next(iter(sorted((root / "data" / cfg).glob("*.parquet")))))
        record_sets.append(
            {
                "@type": "cr:RecordSet",
                "@id": cfg,
                "name": cfg,
                "description": meta.record_set_descriptions.get(
                    cfg, f"Config '{cfg}': one record per series (or chunk)."),
                "key": [{"@id": f"{cfg}/series_id"}, {"@id": f"{cfg}/chunk_idx"}],
                "field": _fields(cfg, {"fileSet": {"@id": fs}}, schema,
                                 meta.field_descriptions),
            }
        )
    for fname, desc in meta.auxiliary.items():
        rs = Path(fname).stem
        distribution.append(
            {
                "@type": "cr:FileObject",
                "@id": fname,
                "name": fname,
                "description": desc,
                "contentUrl": fname,
                "encodingFormat": PARQUET,
                "sha256": sha256(root / fname),
            }
        )
        record_sets.append(
            {
                "@type": "cr:RecordSet",
                "@id": rs,
                "name": rs,
                "description": desc,
                "field": _fields(rs, {"fileObject": {"@id": fname}},
                                 pq.read_schema(root / fname), meta.field_descriptions),
            }
        )

    doc = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "conformsTo": CONFORMS_TO,
        "name": meta.name,
        "description": meta.description,
        "url": meta.url,
        "license": meta.license_url,
        "citeAs": meta.cite_as,
        "creator": [{"@type": "sc:Person", "name": c} for c in meta.creators],
        "datePublished": meta.date_published,
        "version": meta.version,
        "keywords": meta.keywords,
        "isLiveDataset": False,
        "distribution": distribution,
        "recordSet": record_sets,
    }
    if meta.publisher:
        doc["publisher"] = {"@type": "sc:Organization", "name": meta.publisher}
    if meta.same_as:
        doc["sameAs"] = meta.same_as
    for k, v in meta.rai.items():
        doc[f"rai:{k}"] = v
    doc["prov:wasDerivedFrom"] = meta.derived_from
    doc["prov:wasGeneratedBy"] = [a.to_jsonld(i) for i, a in enumerate(meta.activities)]
    for k, v in meta.tsseg.items():
        doc[f"tsseg:{k}"] = v
    return doc


def write_croissant(root: Path, meta: DatasetMetadata, configs: list[str]) -> Path:
    doc = build_croissant(root, meta, configs)
    missing = [k for k in REQUIRED_RAI if doc.get(k) in (None, "", [])]
    if missing:
        raise ValueError(f"missing required RAI fields: {missing}")
    p = Path(root) / "croissant.json"
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return p
