"""Preserve native neuroblastoma profiles and weak breakpoint-region constraints."""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import rdata  # noqa: E402

from tsseg_data.batch import ChangePointStatistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "neuroblastoma-cnv"
SOURCE = "https://cran.r-project.org/package=neuroblastoma"
URL = "https://cran.r-project.org/src/contrib/Archive/neuroblastoma/neuroblastoma_2023.9.3.tar.gz"
CURRENT_URL = "https://cran.r-project.org/src/contrib/neuroblastoma_2023.9.3.tar.gz"
SHA256 = "3076d317455067bf55d6475119472ec4116461890624777bb1fc90d5b3f6c2a2"


def main() -> None:
    args = parse_args(ID)
    # Version-pinned current CRAN URL; the identical package moves to Archive
    # when a new release appears. Both paths remain protected by the same SHA.
    try:
        raw = fetch(
            CURRENT_URL, "neuroblastoma_2023.9.3.tar.gz", SHA256, args.raw_dir, ID
        )
    except OSError:
        raw = fetch(URL, "neuroblastoma_2023.9.3.tar.gz", SHA256, args.raw_dir, ID)
    with tarfile.open(raw) as archive:
        # Parse R serialization as data; do not run R or any downloaded code.
        data = rdata.read_rda(
            archive.extractfile("neuroblastoma/data/neuroblastoma.RData")
        )["neuroblastoma"]
    profiles, regions = data["profiles"], data["annotations"]
    assert list(profiles) == ["profile.id", "chromosome", "position", "logratio"]
    assert list(regions) == ["profile.id", "chromosome", "min", "max", "annotation"]
    assert not profiles.isna().any().any()
    assert not regions.isna().any().any()
    assert set(regions.annotation) == {"normal", "breakpoint"}
    assert (regions["min"] < regions["max"]).all()
    for frame in (profiles, regions):
        frame["series_id"] = [
            f"profile-{p}_chr-{c}"
            for p, c in zip(frame["profile.id"], frame.chromosome, strict=True)
        ]
    regions = regions.rename(
        columns={"profile.id": "profile_id", "min": "min_bp", "max": "max_bp"}
    )
    for column in ("profile_id", "chromosome", "annotation"):
        regions[column] = regions[column].astype(str)
    regions["source_row"] = np.arange(1, len(regions) + 1, dtype=np.int32)
    regions["min_changes"] = (regions.annotation == "breakpoint").astype(np.int32)
    # Null upper bound = no upper bound, rather than an invented exact count.
    regions["max_changes"] = [0 if x == "normal" else None for x in regions.annotation]
    counts = regions.series_id.value_counts()
    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=["logratio"],
        configs={"default": ["logratio"]},
        channel_type=pa.float64(),
        time_column=("position_bp", pa.int32()),
        meta_columns={
            "profile_id": pa.string(),
            "chromosome": pa.string(),
            "n_annotation_regions": pa.int32(),
        },
    )
    stats = ChangePointStatistics()
    with DatasetWriter(args.out_dir, spec) as writer:
        for (profile, chromosome), frame in profiles.groupby(
            ["profile.id", "chromosome"], observed=True, sort=True
        ):
            sid = frame.series_id.iloc[0]
            positions = frame.position.to_numpy(dtype=np.int32)
            assert np.all(np.diff(positions.astype(np.int64)) > 0), sid
            values = frame.logratio.to_numpy(dtype=np.float64)
            assert np.isfinite(values).all(), sid
            writer.add_series(
                sid,
                {"logratio": values},
                time=positions,
                meta={
                    "profile_id": str(profile),
                    "chromosome": str(chromosome),
                    "n_annotation_regions": int(counts.get(sid, 0)),
                },
            )
            stats.add(sid, len(frame), {})
        assert set(regions.series_id) <= {r["series_id"] for r in stats.rows}
        table = pa.Table.from_pandas(regions, preserve_index=False)
        # Explicit nullable integer avoids float/NaN ambiguity for open bounds.
        table = table.set_column(
            table.schema.get_field_index("max_changes"),
            "max_changes",
            pa.array(regions.max_changes, type=pa.int32(), from_pandas=True),
        )
        pq.write_table(table, args.out_dir / "regions.parquet", compression="zstd")
    finish(
        args,
        spec,
        writer,
        stats,
        title="Neuroblastoma copy number profiles with weak breakpoint regions",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="GPL-3.0-only",
        license_url="https://www.gnu.org/licenses/gpl-3.0.html",
        license_evidence=SOURCE,
        description="Native normalized aCGH logratio profiles by patient profile and chromosome, with expert region constraints. This is weakly supervised CPD, not exact-boundary ground truth.",
        collection="Tumours from patients at Institut Curie assayed using array comparative genomic hybridization. Probe coordinates and normalized logratios come directly from CRAN neuroblastoma 2023.9.3.",
        annotation="The package defines normal regions as zero breakpoints and breakpoint regions as at least one breakpoint. All source rows, genomic bounds and both constraint types are retained in regions.parquet. No midpoint, exact CP list, dense state label or consensus is inferred. Unannotated positions have no ground truth; normal is a scored zero-change constraint, not a missing or null state. Endpoint inclusion is not specified by the package manual; native bounds remain unchanged. Region-aware evaluation is required, and ordinary point-distance CP metrics cannot be applied directly.",
        conversion="One series per (profile.id, chromosome), including chromosomes without regions. Native within-group probe order, integer base-pair coordinates and float64 normalized logratios retained without resampling, smoothing or interpolation. Source region order and one-based source_row preserved. min_changes=0/max_changes=0 for normal; min_changes=1/max_changes=null (unbounded) for breakpoint. No exact CP columns exist. RData decoded using rdata 1.0.0 without executing R code.",
        limitations="Region constraints are sparse and do not locate exact changes or give semantic copy-number states. State recurrence and exact segment counts are undefined. Not an independent full-genome annotation. Clinical diagnostic validity is not established.",
        biases="Institut Curie tumour cohort and selected chromosomes; assay, cohort and expert-selection effects may limit generalisation.",
        personal="Human tumour genomic measurements with source pseudonymous profile IDs. No names or demographic records are included. Genomic data are sensitive; do not attempt re-identification or clinical use.",
        citation="Hocking et al. (2013). Learning smoothing models of copy number profiles using breakpoint annotations. BMC Bioinformatics 14:164. doi:10.1186/1471-2105-14-164. CRAN neuroblastoma 2023.9.3, Toby Dylan Hocking.",
        creators=[
            "Toby Dylan Hocking",
            "Gudrun Schleiermacher",
            "Isabelle Janoueix-Lerosey",
        ],
        date_published="2023-09-04",
        info={
            "hf_license": "gpl-3.0",
            "label_type": "cpd_region_constraints",
            "reference_doi": "https://doi.org/10.1186/1471-2105-14-164",
            "use_cases": "Region-aware weakly supervised change point detection only; exact CP metrics require a separate justified evaluation protocol.",
            "annotation_regions": {
                "total": len(regions),
                "by_type": {
                    str(k): int(v) for k, v in regions.annotation.value_counts().items()
                },
                "annotated_series": int(regions.series_id.nunique()),
                "profiles": int(profiles["profile.id"].nunique()),
                "endpoint_convention": "unspecified by provider; native bounds retained",
            },
            "auxiliary": {
                "regions.parquet": "All source weak genomic regions, unchanged bounds, source row and zero/at-least-one CP constraints; not exact CP positions."
            },
        },
    )


if __name__ == "__main__":
    main()
