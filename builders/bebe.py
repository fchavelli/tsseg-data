"""Preserve the seven licensed animal datasets in BEBE's formatted v3 release."""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import yaml  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args, write_json  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch, sha256  # noqa: E402

ID = "bebe"
SOURCE = "https://zenodo.org/records/10982620"
PIN_FILE = Path(__file__).parent / "checksums" / "bebe.json"
RESERVE = 18 * 2**30
META_BUFFER = 64 * 2**20
COHORTS = [
    "desantis_rattlesnakes",
    "baglione_crows",
    "friedlaender_whales",
    "pagano_bears",
    "maekawa_gulls",
    "ladds_seals",
    "vehkaoja_dogs",
]
CHANNELS = ["AccX", "AccY", "AccZ", "Depth", "Speed", "Wetdry"] + [
    f"{sensor}{axis}_{location}"
    for sensor in ["Acc", "Gyr"]
    for location in ["Back", "Neck"]
    for axis in "XYZ"
]
# Bounded, in-memory CSV-prefix pilots, before full download: Parquet/CSV bytes.
PILOT_RATIOS = dict(
    zip(
        COHORTS,
        [
            3868 / 75126,
            533225 / 4252791,
            295131 / 3275180,
            397551 / 15157932,
            433028 / 5174335,
            263479 / 3910139,
            553718 / 5870081,
        ],
        strict=True,
    )
)
PROVIDER_PROCESSING = {
    "desantis_rattlesnakes": "Released 1-Hz preprocessed X/Ydyn/Z; dynamic_acc_only flag in provider notebook; clips split at individual/time gaps.",
    "baglione_crows": "Released 50-Hz acceleration; provider interpolates NaNs and divides three axes by per-clip mean vector norm; interval labels rasterized by provider.",
    "friedlaender_whales": "Released 5-Hz Aw acceleration, depth and speedJJ from provider MAT files; NaNs interpolated, interval labels rasterized, tail cropped after last annotation by provider. Preserve all remaining released rows.",
    "pagano_bears": "Released 16-Hz Int_aX/Int_aY/Int_aZ plus interpolated Wetdry; provider uses corrected annotation clocks and merges rare/mixed behaviors into unknown. Duration-summary gap infilling in notebook does not modify released CSV labels.",
    "maekawa_gulls": "Released 25-Hz acceleration; provider normalizes by per-clip mean vector norm and flips Y/Z for individuals 8/9/10/11; source clips split at time gaps.",
    "ladds_seals": "Released 25-Hz XYZ and depth with provider interpolation of NaNs; provider groups original behaviors, including Other mapped to unknown. No additional gravity subtraction performed here.",
    "vehkaoja_dogs": "Released 100-Hz back/neck accelerometer and gyroscope axes with provider behavior taxonomy and clip partition. Shares source animals/recordings with dog-behaviour-vehkaoja; never independent evaluation datasets.",
}


def make_spec():
    return DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=None,
        time_column=("time_ns", pa.int64()),
        label_columns={"label_behavior": pa.int16()},
        meta_columns={
            "cohort": pa.string(),
            "individual_id": pa.string(),
            "source_individual_id": pa.int32(),
            "source_clip_id": pa.string(),
            "source_fold": pa.int8(),
            "source_sampling_rate_hz": pa.float64(),
            "time_step_ns": pa.int64(),
            "native_channels": pa.list_(pa.string()),
            "source_member": pa.string(),
            "source_archive": pa.string(),
            "overlap_group": pa.string(),
            "source_label_to_global_json": pa.string(),
        },
    )


def project(root, remaining, ratios, raw_remaining=0):
    """Include remaining source, output with 25% margin, and metadata buffer."""
    needed = (
        raw_remaining
        + META_BUFFER
        + sum(
            size * max(PILOT_RATIOS[cohort], ratios.get(cohort, 0)) * 1.25
            for cohort, size in remaining.items()
        )
    )
    free = shutil.disk_usage(root).free
    result = {
        "free_bytes": free,
        "projected_remaining_bytes": needed,
        "projected_peak_free_bytes": free - needed,
    }
    if free - needed < RESERVE:
        raise RuntimeError(
            f"Projected peak free {(free - needed) / 2**30:.3f} GiB below 18 GiB reserve"
        )
    return result


def describe_rates(root):
    card = root / "README.md"
    text = (
        card.read_text()
        .replace(
            "| Sampling | irregular or unspecified |",
            "| Sampling | Regular per source cohort: 1 / 5 / 16 / 25 / 50 / 100 Hz; exact time_ns |",
        )
        .replace("| irregular |", "| regular per cohort (see index) |")
    )
    text = text.replace(
        "| Channels | 18 |",
        "| Channels | 3–12 released channels per cohort; 18-column union, structural absence is NaN |",
    )
    text = text.replace(
        "One Parquet row per series (or per one-hour chunk of a long series), in part files of about 256 MiB under `data/<config>/`.",
        "One Parquet row per complete released source clip, in shared part files of about 256 MiB under `data/default/`. Mixed cohort rates are recorded per series; clips are not divided by the global-rate chunking rule.",
    ).replace(
        "- Series longer than 1 h sampled at 10 Hz or more are split into chunks of 3600 s; concatenate them by `(series_id, chunk_idx)` (`tsseg_data.reader.load_series` does it).",
        "- Complete source clips are retained as rows, including long bear clips; exact per-series `time_ns` and `source_sampling_rate_hz` define their timing.",
    )
    info = json.loads((root / "tsseg.json").read_text())
    rows = [
        "## Cohort statistics",
        "",
        "| Cohort | Clips | Animals | Channels | Hz | Recurrent clips | Unscored |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    source_metadata = json.loads((root / "source_metadata.json").read_text())
    for cohort in COHORTS:
        c = info["cohort_statistics"][cohort]
        track = c["tracks"]["label_behavior"]
        channels = len(source_metadata[cohort]["clip_column_names"]) - 2
        rows.append(
            f"| {cohort} | {c['n_series']} | {c['individuals']} | {channels} | {c['sampling_rate_hz']} | {track['series_with_recurrence']} | {track['missing_share']:.3%} |"
        )
    text = text.replace("## Configs", "\n".join(rows) + "\n\n## Configs")
    card.write_text(text)
    sums = root / "SHA256SUMS"
    sums.write_text(
        "\n".join(
            f"{sha256(card) if name == 'README.md' else digest}  {name}"
            for digest, name in (
                line.split("  ", 1) for line in sums.read_text().splitlines()
            )
        )
        + "\n"
    )


def main():
    args = parse_args(ID)
    raw = args.raw_dir / ID
    raw.mkdir(parents=True, exist_ok=True)
    pins = json.loads(PIN_FILE.read_text())
    assert set(pins) == {f"formatted_{c}.zip" for c in COHORTS}
    # CSV upper bounds from the primary ZIP directories, obtained before download.
    remaining = dict(
        zip(
            COHORTS,
            [
                14098688,
                1133696356,
                585213017,
                9704362986,
                969171958,
                190147405,
                3783540520,
            ],
            strict=True,
        )
    )
    raw_remaining = sum(
        p["bytes"] for name, p in pins.items() if not (raw / name).exists()
    )
    projections = [project(raw, remaining, {}, raw_remaining)]
    archives = {}
    for cohort in COHORTS:
        name = f"formatted_{cohort}.zip"
        pin = pins[name]
        missing = not (raw / name).exists()
        path = fetch(pin["url"], name, pin["sha256"], args.raw_dir, ID)
        assert path.stat().st_size == pin["bytes"]
        archives[cohort] = path
        if missing:
            raw_remaining -= pin["bytes"]
        project(raw, remaining, {}, raw_remaining)
    spec, stats = make_spec(), Statistics()
    source_metadata, states, ratios = {}, {}, {}
    cohort_stats, label_mapping = {}, {}
    with DatasetWriter(args.out_dir, spec) as writer:
        licenses = args.out_dir / "source_licenses"
        licenses.mkdir(exist_ok=True)
        for cohort, path in archives.items():
            cohort_statistics = Statistics()
            with zipfile.ZipFile(path) as archive:
                prefix = f"formatted_{cohort}/"
                metadata = yaml.safe_load(
                    archive.read(prefix + "dataset_metadata.yaml")
                )
                assert metadata["label_names"][0] == "unknown"
                cols = metadata["clip_column_names"]
                native_channels = [
                    c for c in cols if c not in ["individual_id", "label"]
                ]
                assert set(native_channels) <= set(CHANNELS)
                csvs = {
                    prefix + "clip_data/" + clip + ".csv"
                    for clip in metadata["clip_ids"]
                }
                actual = {
                    n
                    for n in archive.namelist()
                    if n.startswith(prefix + "clip_data/")
                    and n.endswith(".csv")
                    and "/." not in n
                }
                assert (
                    actual == csvs
                    and sum(archive.getinfo(n).file_size for n in csvs)
                    == remaining[cohort]
                )
                fs = metadata["sr"]
                assert fs in [1, 5, 16, 25, 50, 100] and 10**9 % fs == 0
                step = 10**9 // fs
                local_map = {0: -1}
                for local, name in enumerate(metadata["label_names"][1:], 1):
                    global_code = len(states)
                    states[global_code] = f"{cohort}:{name}"
                    local_map[local] = global_code
                label_mapping[cohort] = local_map
                source_metadata[cohort] = metadata
                for name in archive.namelist():
                    if (
                        name.startswith(prefix)
                        and "/" not in name[len(prefix) :]
                        and Path(name).name
                        in [
                            "license_bebe.txt",
                            "license_raw.txt",
                            "license_seals.txt",
                            "readme.txt",
                        ]
                    ):
                        (licenses / (cohort + "_" + Path(name).name)).write_bytes(
                            archive.read(name)
                        )
                processed_csv, written_bytes = 0, 0
                for clip in metadata["clip_ids"]:
                    member = prefix + "clip_data/" + clip + ".csv"
                    project(args.out_dir, remaining, ratios)
                    with archive.open(member) as source:
                        frame = pd.read_csv(
                            source, header=None, names=cols, dtype=np.float64
                        )
                    assert frame.shape[1] == len(cols) and len(frame) > 0
                    individual = metadata["clip_id_to_individual_id"][clip]
                    assert np.all(frame["individual_id"].to_numpy() == individual)
                    source_labels = frame["label"].to_numpy()
                    assert (
                        np.isfinite(source_labels).all()
                        and np.equal(source_labels, np.floor(source_labels)).all()
                    )
                    assert set(np.unique(source_labels)) <= set(local_map)
                    lookup = np.array(
                        [local_map[i] for i in range(len(local_map))], dtype=np.int16
                    )
                    labels = lookup[source_labels.astype(np.int64)]
                    folds = [
                        int(f)
                        for f, clips in metadata["clip_ids_per_fold"].items()
                        if clip in clips
                    ]
                    assert (
                        len(folds) == 1
                        and individual in metadata["individuals_per_fold"][folds[0]]
                    )
                    n, sid = len(frame), f"{cohort}__{clip}"
                    signals = {
                        c: frame[c].to_numpy(dtype=np.float32)
                        if c in native_channels
                        else np.full(n, np.nan, dtype=np.float32)
                        for c in CHANNELS
                    }
                    before = sum(
                        (args.out_dir / f).stat().st_size
                        for f in writer.parts["default"].files
                    )
                    writer.add_series(
                        sid,
                        signals,
                        labels={"label_behavior": labels},
                        time=np.arange(n, dtype=np.int64) * step,
                        split=f"fold_{folds[0]}",
                        meta={
                            "cohort": cohort,
                            "individual_id": f"{cohort}:{individual}",
                            "source_individual_id": individual,
                            "source_clip_id": clip,
                            "source_fold": folds[0],
                            "source_sampling_rate_hz": float(fs),
                            "time_step_ns": step,
                            "native_channels": native_channels,
                            "source_member": member,
                            "source_archive": path.name,
                            "overlap_group": "dog-behaviour-vehkaoja"
                            if cohort == "vehkaoja_dogs"
                            else None,
                            "source_label_to_global_json": json.dumps(local_map),
                        },
                    )
                    # Flush each clip to measure compression; parts remain dataset-level shards.
                    writer.parts["default"].flush()
                    after = sum(
                        (args.out_dir / f).stat().st_size
                        for f in writer.parts["default"].files
                    )
                    written_bytes += after - before
                    processed_csv += archive.getinfo(member).file_size
                    remaining[cohort] -= archive.getinfo(member).file_size
                    ratios[cohort] = written_bytes / processed_csv
                    stats.add(sid, {"label_behavior": labels})
                    cohort_statistics.add(sid, {"label_behavior": labels})
                    projection = project(args.out_dir, remaining, ratios)
                cohort_stats[cohort] = cohort_statistics.summary()
                cohort_stats[cohort]["individuals"] = len(metadata["individual_ids"])
                cohort_stats[cohort]["sampling_rate_hz"] = fs
                projections.append({"cohort": cohort, **projection})
                print(
                    f"{cohort}: {cohort_stats[cohort]}; projected peak free {projection['projected_peak_free_bytes'] / 2**30:.2f} GiB",
                    flush=True,
                )
    assert (
        len(stats.rows) == 369
        and sum(c["individuals"] for c in cohort_stats.values()) == 105
    )
    write_json(args.out_dir / "source_metadata.json", source_metadata)
    finish(
        args,
        spec,
        writer,
        stats,
        title="BEBE: seven licensed animal datasets (formatted-release subset)",
        source=SOURCE,
        sha256=sha256(PIN_FILE),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence=SOURCE,
        license_verified_date="2026-10-19",
        description="All 369 released clips from 105 individuals in seven licensed animal datasets of BEBE v3: rattlesnakes, crows, whales, polar bears, gulls, seals and dogs. This explicitly scoped formatted-release subset excludes the noncommercial HAR/HAPT duplicate and rights-unclear turtles. It is not the complete nine-dataset BEBE collection or a reconstruction of original unprocessed signals. Retain every released formatted sensor column and label without additional signal processing. Dogs overlap dog-behaviour-vehkaoja and must not be treated as independent evaluation data.",
        collection="BEBE combines animal-borne sensor datasets acquired by different laboratories, species, environments and annotation protocols. Source formatted release provides 3–12 channels per cohort at 1–100 Hz, clip boundaries, animal IDs and five animal-grouped cross-validation folds. Source preprocessing is cohort-specific, documented in provider_processing and source_metadata.json. Keep repeated clips from the same animal together and preserve provided folds.",
        annotation="Human behavioral annotations already rasterized and taxonomically grouped by the provider. Local label 0 is unknown, explicitly excluded by BEBE's primary evaluation code; map it to unscored -1, without infilling. It includes both missing observations and original rare/mixed behaviors collapsed to unknown by the provider, not an ordinary shared null behavior. Each scored class is namespaced by cohort and mapped to a globally unique reversible code; source_label_to_global_json and original label_names retain the literal mapping. No consensus or independent annotation tracks are invented. Recurrence is measured per released clip excluding -1, with per-cohort and per-series statistics. Missing gaps can separate repeated observations without proving an intervening behavioral change.",
        conversion="Verify the seven complete formatted ZIP archives against pinned SHA256 and official Zenodo MD5/size; stream one CSV member directly from ZIP, checking its CRC at EOF. Never extract a duplicate CSV corpus. CSVs have no header; use provider metadata column order. Preserve all numeric signal values with one float32 cast, all rows, clip IDs and source folds. One default config stores the union of 18 sensor names, with structural absence filled NaN and native_channels listed per series; the union does not imply 18 sensors on any animal. Exact relative nanoseconds use the released per-cohort rate. Global rate is null because rates differ; clips remain whole under the mixed-rate format, grouped in shared Parquet shards. No new resampling, filtering, normalization, interpolation, annotation reconstruction or synthetic joining. Preserve source licences and original dataset metadata as auxiliary provenance files.",
        limitations="Formatted-release track only: the authors already normalized, interpolated, rotated, cropped, split and/or grouped labels in cohort-specific ways; original raw signal and taxonomy fidelity cannot be claimed. Crows/gulls are normalized by clip mean vector norm; gull Y/Z axes flipped for selected animals; whales use released Aw/depth/speed and cropped tails; rattlesnakes use preprocessed X/Ydyn/Z. Provider units are not harmonized across cohorts. Unknown includes provider-excluded behaviors; masks reflect BEBE evaluation scope, not purely annotation availability. HAR and turtles are excluded for rights reasons, so full benchmark totals do not apply. Dogs share source recordings with dog-behaviour-vehkaoja; deduplicate across datasets. No new annotation agreement can be measured.",
        biases="Small, unequal animal cohorts with different species, sensor placement, captivity/wild conditions, observer coverage and taxonomy. Long unannotated recordings dominate some cohorts. Avoid pooling behavior classes across species or animal leakage across folds; do not treat protocol gaps or provider preprocessing artifacts as ecological ground truth.",
        personal="Pseudonymous animal IDs retained; excluded human HAR dataset is not exported. No personal identity, absolute calendar timestamp, GPS location or demographic fields are exported.",
        citation="Hoffman et al. (2024). A benchmark for computational analysis of animal behavior, using animal-borne tags. Movement Ecology 12, 78. doi:10.1186/s40462-024-00511-8. BEBE v3 dataset: doi:10.5281/zenodo.10982620. Cite each original animal dataset as described in its retained metadata/licence and the BEBE paper.",
        creators=["Benjamin Hoffman", "Matthew Cusimano", "BEBE dataset contributors"],
        date_published="2024-04-10",
        info={
            "state_names": {"label_behavior": states},
            "source_files": pins,
            "cohort_statistics": cohort_stats,
            "provider_processing": PROVIDER_PROCESSING,
            "source_label_mappings": label_mapping,
            "included_cohorts": COHORTS,
            "excluded_cohorts": {
                "HAR": "Original noncommercial terms; HAPT duplicate",
                "jeantet_turtles": "No clear original redistribution grant",
            },
            "overlap_groups": {"vehkaoja_dogs": ["dog-behaviour-vehkaoja"]},
            "license_scope": "Only seven audited formatted animal archives: explicit per-archive CC BY 4.0 grants; polar-bear raw source is USGS public domain. Original CC BY grants also verified for crows, whales, seals, dogs, gulls and rattlesnakes. HAR noncommercial and turtles citation-only sources excluded; deposit-level licence is not used to override original restrictions. Retained source_licenses contains exact primary notices.",
            "rehosting_allowed": True,
            "reference_doi": "https://doi.org/10.1186/s40462-024-00511-8",
            "source_preprocessing_notebooks": "https://github.com/earthspecies/BEBE-datasets",
            "source_evaluation": "https://github.com/earthspecies/BEBE/blob/main/BEBE/evaluation/evaluation.py",
            "time_description": "Exact relative time_ns at source_sampling_rate_hz per cohort; not original device timestamps.",
            "storage_sizing": {
                "reserve_bytes": RESERVE,
                "projection_margin": 0.25,
                "metadata_buffer_bytes": META_BUFFER,
                "pilot_parquet_to_csv_ratios": PILOT_RATIOS,
                "rolling_projections": projections,
            },
        },
    )
    describe_rates(args.out_dir)


if __name__ == "__main__":
    main()
