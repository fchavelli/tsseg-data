"""Shared steps of every builder: arguments, tsseg.json, card, checksums."""

from __future__ import annotations

import argparse
import json
import string
from pathlib import Path

from .croissant import DatasetMetadata, write_croissant
from .format import (
    CHUNK_SECONDS,
    FORMAT_VERSION,
    HIGH_FREQ_HZ,
    MISSING_LABEL,
    TARGET_FILE_BYTES,
    DatasetSpec,
    human_bytes,
)
from .sources import sha256

__all__ = ["REPO", "REPO_URL", "HF_NAMESPACE", "parse_args", "write_json", "finalize"]

REPO = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/fchavelli/tsseg-data"  # planned, not created yet
HF_NAMESPACE = "fchavelli"  # planned Hugging Face account, one repo per dataset


def parse_args(dataset_id: str, argv=None, extra=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=f"Build {dataset_id} in the tsseg-data format.")
    if extra is not None:
        extra(p)
    p.add_argument("--raw-dir", type=Path, default=REPO / "raw",
                   help="cache of source files, <raw-dir>/<id>/ (default: ./raw)")
    p.add_argument("--out", type=Path, default=REPO / "build",
                   help="output root; the dataset goes to <out>/<id>/ (default: ./build)")
    a = p.parse_args(argv)
    a.out_dir = a.out / dataset_id
    return a


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _hf_yaml(info: dict, card: dict) -> str:
    lines = ["---"]
    lines.append(f"license: {card['hf_license']}")
    if card.get("license_name"):
        lines.append(f"license_name: {card['license_name']}")
        lines.append(f"license_link: {card['license_link']}")
    lines.append(f"pretty_name: \"{card['pretty_name']}\"")
    lines.append("task_categories:")
    lines += [f"  - {t}" for t in card.get("task_categories", ["other"])]
    lines.append("tags:")
    lines += [f"  - {t}" for t in card["tags"]]
    lines.append(f"size_categories:\n  - {card['size_category']}")
    if card.get("annotations_creators"):
        lines.append("annotations_creators:")
        lines += [f"  - {t}" for t in card["annotations_creators"]]
    lines.append("source_datasets:\n  - original")
    lines.append("configs:")
    for i, cfg in enumerate(info["configs"]):
        lines.append(f"  - config_name: {cfg}")
        lines.append("    data_files:")
        lines.append("      - split: train")
        lines.append(f"        path: data/{cfg}/*.parquet")
        if i == 0:
            lines.append("    default: true")
    lines.append("  - config_name: index")
    lines.append("    data_files:")
    lines.append("      - split: train")
    lines.append("        path: index.parquet")
    lines.append("---")
    return "\n".join(lines)


def _configs_table(info: dict) -> str:
    rows = ["| Config | Channels | Rate | Size | Files | Content |",
            "|---|---|---|---|---|---|"]
    for name, c in info["configs"].items():
        rate = f"{c['sampling_rate_hz']:g} Hz" if c.get("sampling_rate_hz") else "irregular"
        rows.append(f"| `{name}`{' (default)' if name == info['default_config'] else ''} "
                    f"| {len(c['channels'])} | {rate} | {human_bytes(c['bytes'])} "
                    f"| {len(c['files'])} | {c['description']} |")
    return "\n".join(rows)


def _structure(info: dict, spec: DatasetSpec) -> str:
    out = [
        "One Parquet row per series (or per one-hour chunk of a long series), in "
        f"part files of about {TARGET_FILE_BYTES // 2**20} MiB under `data/<config>/`.",
        "",
        "| Column | Type | Content |",
        "|---|---|---|",
        "| `series_id` | string | series identifier |",
        "| `chunk_idx`, `chunk_start`, `length` | int | chunk number, offset (samples), "
        "number of samples in the row |",
    ]
    if spec.time_column:
        out.append(f"| `{spec.time_column[0]}` | list<{spec.time_column[1]}> | "
                   f"{info.get('time_description', 'time stamps')} |")
    out.append(f"| one column per channel | list<{spec.channel_type}> | signal values "
               "(names and units in `tsseg.json`) |")
    for c in spec.label_columns:
        out.append(f"| `{c}` | list<{spec.label_columns[c]}> | "
                   f"{info['label_descriptions'].get(c, 'dense labels')} |")
    if spec.cp_annotators:
        out.append("| `cps_<annotator>` | list<int32> | change points of one annotator "
                   "(null = series not annotated by them, empty = no change) |")
        out.append("| `cp_types_<annotator>` | list<string> | type of each change point |")
    out += [
        "",
        "`index.parquet` has one row per series: `series_id`, `length`, `n_channels`, "
        "`n_chunks`, `split`, `label_columns`, `annotators`, the number of label "
        "changes per label column (`n_changes_*`) or of change points per annotator "
        "(`n_cps_*`), the part files of each config (`files_*`) and series metadata."
        + (" Configs have different sampling rates: `length` and `n_chunks` are those "
           "of the default config, `length_<config>` and `n_chunks_<config>` those of "
           "each config; lengths, chunks and labels of a config are at its own rate "
           "(see the Configs table)." if spec.multi_rate else ""),
        "",
        "Conventions:",
        f"- `{MISSING_LABEL}` marks only the absence of ground truth (not scored, outside "
        "the protocol). Null / other / transition classes are ordinary states, listed "
        "in `tsseg.json` under `null_states`.",
        "- Change points are 0-based indices of the first point of the new segment, "
        "without 0 and n.",
        f"- Series longer than {CHUNK_SECONDS // 3600} h sampled at {HIGH_FREQ_HZ:g} Hz "
        f"or more are split into chunks of {CHUNK_SECONDS} s; concatenate them by "
        "`(series_id, chunk_idx)` (`tsseg_data.reader.load_series` does it).",
    ]
    if info.get("tracks"):
        out.append("- Label tracks (different semantics, same time span): "
                   + ", ".join(f"`label_{t}`" for t in info["tracks"]) + ".")
    if info.get("annotators"):
        out.append("- Annotators (same semantics, different people): "
                   + ", ".join(f"`{a}`" for a in info["annotators"])
                   + (f"; default ground truth `{info['default_label']}`."
                      if info.get("default_label") else "."))
    return "\n".join(out)


def finalize(
    root: Path,
    spec: DatasetSpec,
    info: dict,
    meta: DatasetMetadata,
    card: dict,
    summary: dict,
    config_descriptions: dict[str, str],
) -> None:
    """Write tsseg.json, croissant.json, README.md and SHA256SUMS in ``root``."""
    root = Path(root)
    info = {
        "id": spec.id,
        "format_version": FORMAT_VERSION,
        "task": spec.task,
        # rate of the default config; each config has its own below
        "sampling_rate_hz": spec.rate(next(iter(spec.configs))),
        "native_sampling_rate_hz": spec.sampling_rate_hz,
        "default_config": next(iter(spec.configs)),
        "configs": {
            cfg: {"channels": chans, "sampling_rate_hz": spec.rate(cfg),
                  "description": config_descriptions[cfg],
                  "files": summary[cfg]["files"], "bytes": summary[cfg]["bytes"]}
            for cfg, chans in spec.configs.items()
        },
        "channels": spec.channels,
        "time_column": spec.time_column[0] if spec.time_column else None,
        "label_columns": list(spec.label_columns),
        "cp_annotators": list(spec.cp_annotators),
        "missing_label": MISSING_LABEL,
        "chunking": {"chunk_seconds": CHUNK_SECONDS, "min_sampling_rate_hz": HIGH_FREQ_HZ},
        **info,
    }
    write_json(root / "tsseg.json", info)
    meta.tsseg = {
        "formatVersion": FORMAT_VERSION,
        "task": spec.task,
        "defaultConfig": info["default_config"],
        "labelOrigin": info.get("label_origin"),
        "missingLabel": MISSING_LABEL,
        "nullStates": info.get("null_states", {}),
        "loaderMetadata": "tsseg.json",
        "configSamplingRateHz": ({cfg: spec.rate(cfg) for cfg in spec.configs}
                                 if spec.sampling_rate_hz else None),
        **meta.tsseg,
    }
    meta.record_set_descriptions = {
        **{cfg: f"Config '{cfg}': {config_descriptions[cfg]} One record per series "
           "(or one-hour chunk)." for cfg in spec.configs},
        **meta.record_set_descriptions,
    }
    write_croissant(root, meta, list(spec.configs))

    tmpl = string.Template((REPO / "cards" / "dataset_card.md.tmpl").read_text())
    readme = tmpl.substitute(
        yaml_header=_hf_yaml(info, card),
        pretty_name=card["pretty_name"],
        dataset_id=spec.id,
        summary=card["summary"],
        facts=card["facts"],
        configs=_configs_table(info),
        structure=_structure(info, spec),
        labels=card["labels"],
        annotation=card["annotation"],
        conversion=card["conversion"],
        limitations=meta.rai["dataLimitations"],
        biases=meta.rai["dataBiases"],
        personal=meta.rai["personalSensitiveInformation"],
        use_cases=meta.rai["dataUseCases"],
        social_impact=meta.rai["dataSocialImpact"],
        synthetic="Yes." if meta.rai["hasSyntheticData"] else "No: all signals are measured.",
        license=card["license"],
        citation=card["citation"],
        maintenance=meta.rai.get("dataReleaseMaintenancePlan", ""),
        repo_url=REPO_URL,
    )
    (root / "README.md").write_text(readme)

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (root / "SHA256SUMS").write_text(
        "".join(f"{sha256(p)}  {p.relative_to(root).as_posix()}\n" for p in files)
    )
