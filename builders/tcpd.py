"""Build available measured TCPD series; keep external inputs and experts explicit."""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import ChangePointStatistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "tcpd"
SOURCE = "https://github.com/alan-turing-institute/TCPD"
REVISION = "e8f19a3635e3b7f1a8aff59ce7f4d9bea17525c0"
URL = f"https://codeload.github.com/alan-turing-institute/TCPD/zip/{REVISION}"
SHA256 = "056787f65d2a2e838d82e278d439887bd2fc093cb4209120ff0e28fa38fc2941"


def options(parser):
    parser.add_argument(
        "--extra-json-dir",
        type=Path,
        help="locally obtained missing TCPD JSONs; native MD5 must match pinned primary checksums.json",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless all 37 measured series are available",
    )


def main() -> None:
    args = parse_args(ID, extra=options)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    with zipfile.ZipFile(raw) as archive:
        root = archive.namelist()[0]
        annotations = json.loads(archive.read(root + "annotations.json"))
        checksums = json.loads(archive.read(root + "checksums.json"))
        assert checksums["kind"] == "md5"
        real = sorted(s for s in annotations if not s.startswith("quality_control_"))
        assert len(real) == 37
        inputs, provenance, pending = {}, [], []
        for sid in real:
            name = root + f"datasets/{sid}/{sid}.json"
            if name in archive.namelist():
                content = archive.read(name)
                origin = f"datasets/{sid}/{sid}.json"
            elif (
                args.extra_json_dir is not None
                and (args.extra_json_dir / f"{sid}.json").is_file()
            ):
                content = (args.extra_json_dir / f"{sid}.json").read_bytes()
                origin = "local external JSON verified against primary TCPD MD5"
            else:
                content = None
                origin = "not bundled; external collector reconstruction pending"
                pending.append(sid)
            readme_name = f"datasets/{sid}/README.md"
            readme = archive.read(root + readme_name)
            urls = sorted(set(re.findall(r"https?://[^\s)\]>`]+", readme.decode())))
            provenance.append(
                {
                    "series_id": sid,
                    "included": content is not None,
                    "input_origin": origin,
                    "primary_readme_url": f"{SOURCE}/blob/{REVISION}/{readme_name}",
                    "readme_sha256": hashlib.sha256(readme).hexdigest(),
                    "source_urls_from_readme": urls,
                    "native_json_md5": None
                    if content is None
                    else hashlib.md5(content).hexdigest(),
                    "native_json_sha256": None
                    if content is None
                    else hashlib.sha256(content).hexdigest(),
                    "rights_status": "Per-source terms differ; no blanket MIT data licence; conservative source-only pending upstream review",
                }
            )
            if content is None:
                continue
            accepted = checksums["checksums"][f"{sid}.json"]
            if isinstance(accepted, str):
                accepted = [accepted]
            assert hashlib.md5(content).hexdigest() in accepted, (
                f"Native TCPD checksum mismatch: {sid}"
            )
            inputs[sid] = json.loads(content)
    if args.require_complete and pending:
        raise RuntimeError(f"Missing native measured series: {', '.join(pending)}")
    assert len(inputs) >= 27
    experts = sorted({a for sid in real for a in annotations[sid]}, key=int)
    channels = [f"value_{i}" for i in range(max(d["n_dim"] for d in inputs.values()))]
    spec = DatasetSpec(
        id=ID,
        task="cpd",
        channels=channels,
        configs={"default": channels},
        channel_type=pa.float64(),
        time_column=("source_index", pa.int32()),
        cp_annotators=experts,
        meta_columns={
            "source_name": pa.string(),
            "native_n_channels": pa.int32(),
            "native_channel_names": pa.list_(pa.string()),
            "native_channel_types": pa.list_(pa.string()),
        },
    )
    stats = ChangePointStatistics()
    times, agreements, annotation_rows = [], [], []
    for sid in real:
        for expert, points in annotations[sid].items():
            annotation_rows.append(
                {
                    "series_id": sid,
                    "source_annotator_id": expert,
                    "signal_included": sid in inputs,
                    "native_zero_based_cps": points,
                }
            )
    with DatasetWriter(args.out_dir, spec) as writer:
        for sid, data in sorted(inputs.items()):
            n, ndim = data["n_obs"], data["n_dim"]
            assert data["name"] == sid and len(data["series"]) == ndim
            assert data["time"]["index"] == list(range(n))
            signal = {c: np.full(n, np.nan, dtype=np.float64) for c in channels}
            for i, values in enumerate(data["series"]):
                assert values["type"] in ["int", "float"]
                array = np.asarray(values["raw"], dtype=np.float64)
                assert len(array) == n
                signal[channels[i]] = array
            raw_points = {a: None for a in experts}
            cps = {a: None for a in experts}
            for expert, values in annotations[sid].items():
                points = np.asarray(values, dtype=np.int32)
                assert np.all((points > 0) & (points < n)) and np.all(
                    np.diff(points) > 0
                )
                raw_points[expert] = points
                cps[expert] = (points, ["unspecified"] * len(points))
            for first, second in itertools.combinations(annotations[sid], 2):
                a, b = set(annotations[sid][first]), set(annotations[sid][second])
                agreements.append(
                    {
                        "series_id": sid,
                        "annotator_a": first,
                        "annotator_b": second,
                        "intersection": len(a & b),
                        "union": len(a | b),
                        "exact_jaccard": len(a & b) / len(a | b) if a | b else 1.0,
                    }
                )
            times.append(
                {
                    "series_id": sid,
                    "native_time_json": json.dumps(data["time"], ensure_ascii=False),
                }
            )
            writer.add_series(
                sid,
                signal,
                time=np.asarray(data["time"]["index"], dtype=np.int32),
                cps=cps,
                annotators=list(annotations[sid]),
                meta={
                    "source_name": data["longname"],
                    "native_n_channels": ndim,
                    "native_channel_names": [v["label"] for v in data["series"]],
                    "native_channel_types": [v["type"] for v in data["series"]],
                },
            )
            stats.add(sid, n, raw_points)
        for filename, rows in [
            ("source_provenance.parquet", provenance),
            ("native_times.parquet", times),
            ("source_annotations.parquet", annotation_rows),
            ("expert_agreement.parquet", agreements),
        ]:
            pq.write_table(
                pa.Table.from_pylist(rows), args.out_dir / filename, compression="zstd"
            )
    finish(
        args,
        spec,
        writer,
        stats,
        title="Turing Change Point Dataset: available measured series, source-only",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="LicenseRef-TCPD-Mixed-Upstream",
        license_url=f"{SOURCE}/tree/{REVISION}/datasets",
        license_evidence=f"{SOURCE}/blob/{REVISION}/README.md",
        description=f"Measured TCPD series with all native expert boundary lists, excluding all five fully synthetic quality-control series. This build includes {len(inputs)} of 37 measured series; {len(pending)} external native JSON inputs remain pending. Individual data licences differ; no blanket MIT data redistribution permission is asserted.",
        collection="TCPD curates short measured series from diverse economic, industrial, environmental, medical and movement sources. Native JSONs are retained numerically, including multivariate run_log; optional external JSONs are accepted only when their bytes match the pinned primary TCPD checksums. No remote provider collector is executed.",
        annotation="Primary TCPD README explicitly specifies zero-based CP indices and source annotator IDs. Every original expert list is preserved separately: [] means an expert marked no CP, null means that expert did not annotate the series. No union, average boundary, consensus, semantic state or recurrence is fabricated. Five fully synthetic quality_control inputs and their annotations are excluded. All 37 measured-series expert annotations remain auxiliary even when a signal is pending. Exact pairwise CP-set Jaccard is reported on included signals, with two empty sets assigned 1; this strict statistic uses no tolerance and is not semantic-state agreement.",
        conversion="Source archive SHA256 and every included native JSON's published MD5 checked, with independent SHA256 recorded per JSON. One series per native dataset; float64 native channel values preserved. Two native nonfinite values in uk_coal_employ are retained, distinct from dimension padding. Generic ordered value_i columns map reversibly to native channel names/types in the index. Absent dimensions are padded NaN and must be selected using native_n_channels, not treated as observations. Native source index retained as time column; complete original calendar/numeric time structures preserved losslessly in native_times.parquet. No resampling, scaling, whitening, generated signals or univariate flattening. External JSON option changes the explicit included/pending inventory; --require-complete fails on any missing measured series.",
        limitations="Default only includes 27 bundled measured JSONs, not the entire original 42-series benchmark. Ten measured signals require external reconstruction: apple, bee_waggle_6, bitcoin, iceland_tourism, measles, occupancy, ratner_stock, robocalls, scanline_126007, scanline_42049. Original collectors depend on mutable Yahoo APIs or archived upstream pages and are not executed. Licensed local JSONs can be supplied with --extra-json-dir, retaining primary checksum checks; completeness is explicit. Source licences and time units differ per series, and upstream rights require individual review before any redistribution. No shared physical sampling rate exists. Source selection and preprocessing precede this conversion.",
        biases="Curated short heterogeneous series and subjective expert boundaries; not representative of all segmentation tasks. Exact Jaccard heavily penalises near-miss boundaries, so report established multi-expert CP metrics separately.",
        personal="Some source series include human run-log or medical/ecological measurements and coarse native calendar times; source expert numeric IDs retained. No identities are inferred; review individual provenance before sensitive applications. Native source time data may reveal routine timing.",
        citation="Van den Burg, G. J. J. & Williams, C. K. I. (2020). An Evaluation of Change Point Detection Algorithms. arXiv:2003.06222. Turing Change Point Dataset. doi:10.5281/zenodo.3713242. Individual upstream attribution URLs are preserved in source_provenance.parquet.",
        creators=["Gertjan J. J. van den Burg", "Christopher K. I. Williams"],
        date_published="2025-07-25",
        info={
            "hf_license": "other",
            "license_scope": "Code repository MIT; individual data licences vary. The primary README explicitly distinguishes them. Upstream redistribution rights are not collectively established; tier C/source-only, no rehosting. See docs/licenses/tcpd.md and source_provenance.parquet.",
            "rehosting_allowed": False,
            "source_revision": REVISION,
            "date_published_scope": "Pinned source repository revision date",
            "reference_doi": "https://doi.org/10.5281/zenodo.3713242",
            "included_measured_series": len(inputs),
            "pending_measured_series": pending,
            "excluded_synthetic_series": [f"quality_control_{i}" for i in range(1, 6)],
            "default_annotator": None,
            "agreement": {
                "method": "Mean pairwise exact boundary-set Jaccard; two empty sets agree fully; no positional tolerance",
                "pairs": len(agreements),
                "mean_exact_jaccard": float(
                    np.mean([r["exact_jaccard"] for r in agreements])
                ),
            },
            "auxiliary": {
                "source_provenance.parquet": "Per-series input availability, native MD5/SHA256, primary README URL/SHA and source attribution URLs, including pending signals.",
                "native_times.parquet": "Complete native heterogeneous time objects as lossless JSON, with calendar/numeric values and provider format.",
                "source_annotations.parquet": "Every expert boundary list for the 37 measured series, including signals pending local reconstruction; no synthetic data.",
                "expert_agreement.parquet": "Per included series/expert pair strict boundary intersection, union and exact Jaccard; empty-set convention explicit.",
            },
        },
    )


if __name__ == "__main__":
    main()
