"""Build all 14 Barbič sequences locally; annotation redistribution is unresolved."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tsseg_data.batch import Statistics, finish  # noqa: E402
from tsseg_data.build import parse_args  # noqa: E402
from tsseg_data.format import DatasetSpec, DatasetWriter  # noqa: E402
from tsseg_data.sources import fetch  # noqa: E402

ID = "mocap"
SOURCE = "http://graphics.cs.cmu.edu/projects/segmentation/"
SIGNAL_SHA256 = "591da81b05e67e7169aefc5337a61f27efb3b470bed8af4b625886049b74df5a"
LABEL_SHA256 = "5668aec106a9cdba8067f9b98d7e272c803006149f76f2f46a07d77179706ff6"
ALIASES = {"walk": "walking"}
SCOPE = (
    "CMU motion data allow copying/modification/redistribution (FAQ), with no direct "
    "resale even after conversion (home page). The Barbič project page and ground-truth "
    "archive contain no explicit licence for the annotations. SOURCE-ONLY, no "
    "redistribution of this labelled conversion pending author permission. Verified "
    "2026-10-18: http://mocap.cs.cmu.edu/faqs.php and http://mocap.cs.cmu.edu/ ."
)


def parse_labels(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    count = int(lines[0])
    assert len(lines) == 1 + 2 * count
    actions, boundaries = [], []
    for i in range(count):
        number, name = lines[1 + 2 * i].split(maxsplit=1)
        assert int(number) == i + 1
        actions.append(name)
        values = [int(x) for x in lines[2 + 2 * i].split()]
        assert len(values) == (1 if i == count - 1 else 3)
        boundaries.append(values)
    return actions, boundaries


def main():
    args = parse_args(ID)
    signals = fetch(
        SOURCE + "segmentation_amc-data.zip",
        "signals.zip",
        SIGNAL_SHA256,
        args.raw_dir,
        ID,
    )
    labels = fetch(
        SOURCE + "segmentation_ground-truth.zip",
        "labels.zip",
        LABEL_SHA256,
        args.raw_dir,
        ID,
    )
    channels = [f"dof_{i:02d}" for i in range(1, 63)]
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=channels,
        configs={"default": channels},
        sampling_rate_hz=120,
        label_columns={"label_action": pa.int16()},
        meta_columns={
            "subject": pa.string(),
            "trial": pa.string(),
            "source_file": pa.string(),
            "source_label_endpoint": pa.int32(),
        },
    )
    stats = Statistics()
    segment_rows = []
    mismatches = {}
    with zipfile.ZipFile(signals) as signal_zip, zipfile.ZipFile(labels) as label_zip:
        parsed = {
            f"{i:02d}": parse_labels(
                label_zip.read(f"{i:02d}_ground_truth.txt").decode()
            )
            for i in range(1, 15)
        }
        names = sorted(
            {ALIASES.get(a, a) for actions, _ in parsed.values() for a in actions}
        )
        codes = {name: i for i, name in enumerate(names)}
        with DatasetWriter(args.out_dir, spec) as writer:
            for trial, (actions, bounds) in parsed.items():
                member = f"Patient1.Mix {trial}.amc.txt"
                x = np.loadtxt(signal_zip.open(member), dtype=np.float32)
                assert x.shape[1] == 62
                n = len(x)
                cps = np.array([b[1] for b in bounds[:-1]], dtype=np.int64)
                assert np.all((cps > 0) & (cps < n)) and np.all(np.diff(cps) > 0)
                y = np.repeat(
                    [codes[ALIASES.get(a, a)] for a in actions],
                    np.diff(np.r_[0, cps, n]),
                ).astype(np.int16)
                sid = f"86_{trial}"
                if bounds[-1][0] != n:
                    mismatches[sid] = {
                        "source_label_endpoint": bounds[-1][0],
                        "signal_rows": n,
                    }
                writer.add_series(
                    sid,
                    {c: x[:, j] for j, c in enumerate(channels)},
                    labels={"label_action": y},
                    meta={
                        "subject": "86",
                        "trial": trial,
                        "source_file": member,
                        "source_label_endpoint": bounds[-1][0],
                    },
                )
                stats.add(sid, {"label_action": y})
                for i, (action, start, end) in enumerate(
                    zip(actions, np.r_[0, cps], np.r_[cps, n], strict=True)
                ):
                    b = bounds[i] if i < len(actions) - 1 else None
                    segment_rows.append(
                        {
                            "series_id": sid,
                            "segment_idx": i,
                            "start": int(start),
                            "end": int(end),
                            "state": codes[ALIASES.get(action, action)],
                            "source_action": action,
                            "boundary_earliest_source": b[0] if b else None,
                            "boundary_best_source": b[1] if b else None,
                            "boundary_latest_source": b[2] if b else None,
                            "window_order_valid": b[0] <= b[1] <= b[2] if b else None,
                            "overlaps_previous_best": b[0] < bounds[i - 1][1]
                            if b and i
                            else False,
                        }
                    )
    pq.write_table(
        pa.Table.from_pylist(segment_rows),
        args.out_dir / "segments.parquet",
        compression="zstd",
    )
    finish(
        args,
        spec,
        writer,
        stats,
        title="CMU subject 86: 14 Barbič trials (source-only)",
        source=SOURCE,
        sha256=SIGNAL_SHA256,
        license_spdx="LicenseRef-CMU-Motion-Barbic-Labels-Unlicensed",
        license_url=SOURCE,
        license_evidence=SOURCE,
        description="All fourteen 62-DOF motion sequences at 120 Hz with Barbič action "
        "labels and original earliest/best/latest transition estimates. Local source-only build.",
        collection="CMU motion-capture subject 86, fourteen trials used in Graphics Interface "
        "2004. Provider exports one row per frame with 62 joint degrees of freedom; "
        "root includes position and orientation, so not every column is an angle.",
        annotation="Human action descriptions and best boundaries from the Barbič ground "
        "truth archive. walk is explicitly aliased to walking; all other action "
        "strings remain distinct. Exact original strings and all three source "
        "boundary estimates are in segments.parquet. No null class is inferred.",
        conversion="Preserve all 62 source DOFs, float32 cast, no filtering or normalisation. "
        "Use numeric best transition frame as an offset (first point of the next "
        "segment); source does not establish a consistent frame-index convention. "
        "Keep all signal rows and extend/clip only the final action to the actual "
        "signal length; source label endpoints differ by up to eight frames and "
        "are retained in the index. No interior boundary is corrected. Invalid "
        "earliest/best/latest ordering (05 and 06) and broad overlapping window "
        "(04) are preserved and flagged; never silently sorted or clipped.",
        limitations="One subject; subjective approximate boundaries and inconsistent terminal "
        "frame counts. Invalid tolerance windows cannot be used as valid intervals "
        "without a separately documented policy. DOFs use positional names until "
        "the provider amc_to_matrix mapping is independently resolved. " + SCOPE,
        biases="One subject, scripted actions and laboratory capture; action strings have "
        "different granularity, and only walk/walking is normalised.",
        personal="Pseudonymous subject 86 motion; movement patterns may be identifying. "
        "No demographic files or video are included.",
        citation="Barbič, Jernej; Safonova, Alla; Pan, Jia-Yu; Faloutsos, Christos; Hodgins, "
        "Jessica K.; Pollard, Nancy S. (2004). Segmenting Motion Capture Data into "
        "Distinct Behaviors. Graphics Interface, pp. 185–194. " + SOURCE,
        creators=[
            "Barbič, Jernej",
            "Safonova, Alla",
            "Pan, Jia-Yu",
            "Faloutsos, Christos",
            "Hodgins, Jessica K.",
            "Pollard, Nancy S.",
        ],
        date_published="2004",
        info={
            "license_scope": SCOPE,
            "hf_license": "other",
            "rehosting_allowed": False,
            "license_tier": "C (annotations unlicensed)",
            "labels_sha256": LABEL_SHA256,
            "state_names": {"label_action": dict(enumerate(names))},
            "action_aliases": ALIASES,
            "source_endpoint_mismatches": mismatches,
            "auxiliary": {
                "segments.parquet": "Action segments, original action strings, "
                "unmodified source transition triplets and quality flags."
            },
        },
    )


if __name__ == "__main__":
    main()
