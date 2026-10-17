"""Build TSSB locally; upstream UCR/UEA redistribution rights remain unresolved."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "tssb"
REVISION = "e0c7a1f6cee6874e60cbacd3b8601f2de259606e"
SOURCE = "https://github.com/ermshaua/time-series-segmentation-benchmark"
URL = f"https://codeload.github.com/ermshaua/time-series-segmentation-benchmark/zip/{REVISION}"
SHA256 = "7b3a68700d119bc5bba3dd758c74764a4932d34f176b40636c04aff984b96502"
LICENSE_SCOPE = (
    "BSD-3-Clause is verified for the TSSB repository, not independently for each "
    "underlying UCR/UEA recording. Primary UCR archive and UEA collection pages "
    "checked on 2026-10-18 provide no blanket data licence establishing rights "
    "for these 75 derived series. SOURCE-ONLY: local build only; no redistribution "
    "until per-source rights are resolved. Sources: "
    "https://www.cs.ucr.edu/~eamonn/time_series_data_2018/ and "
    "https://www.timeseriesclassification.com/dataset.php ."
)


def main():
    args = parse_args(ID)
    raw = fetch(URL, "source.zip", SHA256, args.raw_dir, ID)
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=["value"],
        configs={"default": ["value"]},
        label_columns={"label_class": pa.int16()},
        meta_columns={
            "source_dataset": pa.string(),
            "window_size": pa.int32(),
            "label_cut": pa.int16(),
            "source_resample_rate": pa.int32(),
            "source_file": pa.string(),
        },
    )
    stats = Statistics()
    states = set()
    with zipfile.ZipFile(raw) as archive, DatasetWriter(args.out_dir, spec) as writer:
        prefix = archive.namelist()[0] + "tssb/datasets/"
        desc = [
            line.split(",")
            for line in archive.read(prefix + "desc.txt").decode().splitlines()
        ]
        props = {
            r[0]: r[1:]
            for r in (
                line.split(",")
                for line in archive.read(prefix + "properties.txt")
                .decode()
                .splitlines()
            )
        }
        assert len(desc) == len(props) == 75
        for row in desc:
            sid, window, *cp = row
            x = np.loadtxt(archive.open(prefix + sid + ".txt"), dtype=np.float32)
            cps = np.asarray(cp, dtype=np.int64)
            assert np.all((cps > 0) & (cps < len(x))) and np.all(np.diff(cps) > 0)
            normalise, cut, rate, *indices = props[sid]
            cut, rate = int(cut), int(rate)
            assert normalise == "true" and len(indices) == len(cps) + 1
            # Provider utils.generate_time_series_segmentation_dataset splits every
            # class into label_cut+1 parts before selecting indices from properties.
            classes = np.asarray(indices, dtype=np.int16) // (cut + 1)
            y = np.repeat(classes, np.diff(np.r_[0, cps, len(x)])).astype(np.int16)
            assert np.array_equal(np.flatnonzero(y[1:] != y[:-1]) + 1, cps)
            states.update(classes.tolist())
            labels = {"label_class": y}
            writer.add_series(
                sid,
                {"value": x},
                labels=labels,
                meta={
                    "source_dataset": sid,
                    "window_size": int(window),
                    "label_cut": cut,
                    "source_resample_rate": rate,
                    "source_file": f"tssb/datasets/{sid}.txt",
                },
            )
            stats.add(sid, labels)
    finish(
        args,
        spec,
        writer,
        stats,
        title="Time Series Segmentation Benchmark (source-only)",
        source=SOURCE,
        sha256=SHA256,
        license_spdx="BSD-3-Clause",
        license_url=f"{SOURCE}/blob/{REVISION}/LICENSE",
        license_evidence=f"{SOURCE}/blob/{REVISION}/LICENSE",
        description="75 semi-synthetic univariate segmentation series constructed from "
        "UCR/UEA classification datasets. Local source-only conversion; "
        "underlying data redistribution rights remain unresolved.",
        collection="TSSB concatenates classification instances grouped by class, after "
        "per-instance standard-score normalisation and block-mean resampling. "
        "Sources span multiple domains and include non-temporal shape profiles.",
        annotation="CPs are the exact concatenation offsets in desc.txt. State class "
        "IDs reconstruct the grouped classification labels from properties.txt: "
        "selected subsegment index // (label_cut + 1), matching the provider's "
        "generation code. Classes are local to each source dataset. No null "
        "class or absent annotation; all points have construction labels.",
        conversion="Read final source .txt values as float32; no further processing. "
        "Retain provider window size, label_cut and resampling factor. "
        "No physical sampling rate is asserted across unrelated sources.",
        limitations="Artificial concatenation boundaries; only a minority of series "
        "have recurrent classes. Source-domain and original label meanings "
        "are not reconstructed from the numeric grouped class index. " + LICENSE_SCOPE,
        biases="Curated UCR/UEA classification problems; synthetic temporal ordering "
        "does not represent naturally occurring transitions.",
        personal="Some upstream domains include human physiological or motion signals; "
        "no identity attributes are added. Upstream participant consent is not re-audited.",
        citation="Ermshaus, Arik; Schafer, Patrick; Leser, Ulf (2023). ClaSP: "
        "parameter-free time series segmentation. Data Mining and Knowledge "
        "Discovery. https://doi.org/10.1007/s10618-023-00923-x",
        creators=["Ermshaus, Arik", "Schafer, Patrick", "Leser, Ulf"],
        date_published="2021",
        synthetic=True,
        info={
            "reference_doi": "https://doi.org/10.1007/s10618-023-00923-x",
            "source_revision": REVISION,
            "label_origin": "concatenation",
            "license_scope": LICENSE_SCOPE,
            "rehosting_allowed": False,
            "hf_license": "other",
            "license_tier": "C (pending per-source clarification)",
            "state_names": {
                "label_class": {
                    str(s): f"source-local class {s}" for s in sorted(states)
                }
            },
        },
    )


if __name__ == "__main__":
    main()
