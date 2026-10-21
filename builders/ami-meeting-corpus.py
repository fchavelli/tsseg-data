"""Build fixed MFCC features and independent manual speaker-activity tracks for AMI."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import scipy

from tsseg_data.ami import (
    AGENTS,
    COEFFS,
    FS,
    HOP,
    RESERVE,
    acquire,
    activity,
    extract,
    segment_source,
)
from tsseg_data.batch import Statistics, finish
from tsseg_data.build import parse_args
from tsseg_data.format import DatasetSpec, DatasetWriter
from tsseg_data.sources import fetch, sha256

ID = "ami-meeting-corpus"
SOURCE = "https://groups.inf.ed.ac.uk/ami/corpus/"
PINS = Path(__file__).parent / "checksums/ami-meeting-corpus.json"
ANNOTATION_SHA = "b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d"
LABELS = [f"label_{agent.lower()}" for agent in AGENTS]
CHANNELS = [f"mfcc_{i:02d}" for i in range(COEFFS)]


def main():
    args = parse_args(
        ID, extra=lambda p: p.add_argument("--pilot", action="store_true")
    )
    raw = args.raw_dir / ID
    raw.mkdir(parents=True, exist_ok=True)
    pins = json.loads((raw / "audio-pins.json" if args.pilot else PINS).read_text())
    if (
        shutil.disk_usage(raw).free
        - pins["audio_bytes"]
        - 22887865
        - 10 * 2**30
        - 64 * 2**20
        < RESERVE
    ):
        raise RuntimeError("Complete cache/output gate breaches18GiB")
    expected_versions = pins.get("extractor_dependencies")
    if expected_versions is not None:
        assert {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        } == expected_versions, "Use the pinned MFCC dependency versions"
    if not args.pilot:
        assert pins["annotation_file"]["sha256"] == ANNOTATION_SHA
    archive = fetch(
        "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip",
        "ami_public_manual_1.6.2.zip",
        ANNOTATION_SHA,
        args.raw_dir,
        ID,
    )
    assert sha256(archive) == ANNOTATION_SHA
    segments, rosters, partitions = segment_source(archive)
    selected = [pin for pin in pins["files"] if "sha256" in pin]
    for pin in selected:
        sid = Path(pin["url"]).name.split(".")[0]
        assert set(rosters[sid]) <= set(AGENTS)
        assert all((sid, agent) in segments for agent in rosters[sid])
        assert all(
            not rows or agent in rosters[sid]
            for (meeting, agent), rows in segments.items()
            if meeting == sid
        )
    if not args.pilot:
        assert len(selected) == 171
    spec = DatasetSpec(
        id=ID,
        task="sd",
        channels=CHANNELS,
        configs={"default": CHANNELS},
        sampling_rate_hz=100,
        time_column=("time_ns", pa.int64()),
        label_columns={t: pa.int8() for t in LABELS},
        meta_columns={
            "session_group": pa.string(),
            "source_audio_samples": pa.int64(),
            "source_audio_channels": pa.int8(),
            "source_audio_sha256": pa.string(),
            "present_agents": pa.list_(pa.string()),
            "source_interval_issues": pa.list_(pa.string()),
            **{
                f"source_{key}": pa.string()
                for key in ["visibility", "seen_type", "k5", "k10"]
            },
        },
    )
    stats = Statistics()
    source_rows = []
    details = []
    positive = {t: 0 for t in LABELS}
    overlap = 0
    with DatasetWriter(args.out_dir, spec) as writer:
        for pin in selected:
            if shutil.disk_usage(raw).free - 2**30 < RESERVE:
                raise RuntimeError("Build reserve plus1GiB write buffer unavailable")
            path = acquire(raw, pin)
            sid = path.name.split(".")[0]
            features, n = extract(path)
            count = len(features)
            assert pin["source_samples"] == n and count == (n + HOP - 1) // HOP
            labels, rows, issues = activity(sid, count, n, segments, rosters[sid])
            source_rows.extend(rows)
            if shutil.disk_usage(raw).free - 2**30 < RESERVE:
                raise RuntimeError("Write reserve plus1GiB buffer unavailable")
            writer.add_series(
                sid,
                {c: features[:, i] for i, c in enumerate(CHANNELS)},
                time=np.arange(count, dtype=np.int64) * 10_000_000,
                labels=labels,
                meta={
                    "session_group": sid[:-1] if sid[-1].isalpha() else sid,
                    "source_audio_samples": n,
                    "source_audio_channels": pin["channels"],
                    "source_audio_sha256": pin["sha256"],
                    "present_agents": sorted(rosters[sid]),
                    "source_interval_issues": issues,
                    **{
                        f"source_{key}": value for key, value in partitions[sid].items()
                    },
                },
            )
            stats.add(sid, labels)
            for track, y in labels.items():
                positive[track] += int(
                    np.count_nonzero((y == 1) & np.r_[True, y[1:] != y[:-1]]) > 1
                )
            shared = int(
                np.count_nonzero(np.sum([y == 1 for y in labels.values()], axis=0) > 1)
            )
            overlap += shared
            details.append(
                {
                    "series_id": sid,
                    "audio_samples": n,
                    "native_audio_channels": pin["channels"],
                    "feature_frames": count,
                    "feature_min": float(features.min()),
                    "feature_max": float(features.max()),
                    "simultaneous_speaker_frames": shared,
                    "interval_issues": issues,
                }
            )
            if shutil.disk_usage(raw).free < RESERVE:
                raise RuntimeError("18GiB reserve breached")
            print(sid, count, issues, flush=True)
    pq.write_table(
        pa.Table.from_pylist(source_rows),
        args.out_dir / "source-segments.parquet",
        compression="zstd",
    )
    if not args.pilot:
        assert len(stats.rows) == 171 and len(source_rows) == 93637
    finish(
        args,
        spec,
        writer,
        stats,
        title="AMI Meeting Corpus: complete mixed-headset MFCC13 and manual speaker-activity reference",
        source=SOURCE,
        sha256=sha256(PINS) if not args.pilot else sha256(raw / "audio-pins.json"),
        license_spdx="CC-BY-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence="https://groups.inf.ed.ac.uk/ami/corpus/license.shtml",
        license_verified_date="2026-10-20",
        description="Deterministic 13-coefficient MFCC features for all 171 provider mixed-headset WAV meetings, with separate manual transcriber activity tracks for up to five local speakers. Preserve speaker overlaps and complete original segment timings. No raw audio, transcript text or videos packaged.",
        collection="The complete primary 171 mixed-headset view of AMI, approximately 100 h of English meetings in multiple rooms. This is the provider mixed-headset view, not all 24 original microphone channels. Native channel counts are retained per meeting; stereo source mixes are explicitly averaged for feature extraction. Source audio is16-kHz signed 16 bit PCM. Audio and manual annotations share the documented synchronized timeline; no fitted offsets or annotation stretching. Five meetings have three local speakers,163 have four and three have five. Five empty D segment-file placeholders correspond to absent roster agents, so D remains entirely unscored in those meetings.",
        annotation="The primary ami_public_manual_1.6.2.zip XML transcriber_start/end intervals are the reference: human transcript segmentation/review, distinct from automatically forced-aligned word/phoneme timestamps. Every original segment ID, channel and decimal timing is retained separately, including51 optional starttime/endtime pairs that are not used for the reference; no word text is packaged. Five independent local speaker tracks A–E encode 1 for a segment active at the exact 10 ms feature center and 0 when no selected transcriber interval is active; this does not independently assert acoustic silence. Structural absent agents are entirely -1. Simultaneous speakers remain simultaneously positive. Source reversed/empty or out-of-duration intervals are retained and flagged, never repaired: their intersecting uncertain timing window is masked -1 for that speaker after valid segments are assigned. No exclusive speaker state, global rater identity or consensus is invented. The local agent A default is a convenience, not a privileged speaker.",
        conversion="SHA-pin every native primary WAV and manual ZIP. WAV decode requires 16 kHz signed 16 bit uncompressed PCM with one or two native channels; no source code execution or model download. Extract in batches of1000 feature frames using bounded audio reads. Center frames at source sample indices0,160,320,... strictly before native EOF (ceil(n/160) frames), with 400-sample 25 ms symmetric Hamming windows at sample offsets-200..199 relative to each nominal anchor and zero padding only beyond native start/end. Convert int16 to float64 by /32768, then take the arithmetic mean of native channels before windowing; no pre-emphasis, mean/variance normalization or learned transform. Compute 512-point real FFT, power=abs(FFT)^2/512, 40 triangular filters equally spaced in2595*log10(1+Hz/700) mel from 0 to 8 kHz with continuous-frequency triangular weights and no area normalization. Natural log with floor 1e-10, DCT-II orthonormal, retain coefficients 0..12 without replacing c0 by an energy feature; cast once to float32. Fixed feature rate 100 Hz; time_ns=center_index*10,000,000. Exact decimal half-open interval mapping uses ceil(time*100), so labels follow frame centers rather than entire windows. Source PCM lengths remain separately available. Long feature series use normal one-hour chunks.",
        limitations="MFCCs are deterministic spectral features and not invertible raw waveform observations or pretrained speaker embeddings. Centered windows include12.5ms context on both sides; source boundary padding affects edge features. A center-sampled label does not assert every sample in the window belongs to that speaker. Manual transcriber timing is coarser than the 10 ms feature grid, and source interval defects remain explicit. Seven source intervals are defective:two reversed and five at TS3007c beyond native PCM EOF2420s (XML meeting duration2430s). Preserve them and mask their intersecting observed windows; never append artificial audio/feature frames. The archive README also reports incomplete or incorrect propagated timing for TS3009c channel3, EN2002a/c and EN2003a; selected transcriber intervals are preserved without assuming a fresh timing validation. Local speaker IDs are meaningful within a meeting; the same local letter need not denote the same person in another meeting. Activity follows released utterance segments rather than sample-accurate voice activity: intervals can contain pauses or non-lexical sounds. Binary recurrence including the no-segment background differs from recurring positive activity; report both. Mixed audio loses individual microphone isolation and contains background/vocalization effects; no voice separation, speaker recognition or diarization model is run.",
        biases="AMI includes scenario design-team role play and natural meetings, mostly non-native English speakers and room/device correlations. Meetings within a scenario day share participants: evaluate with source session or independently documented participant partitions, not random feature windows. Preserve native XML visibility/seen_type/k5/k10 per meeting:98 scenario training,20 development,20 unseen evaluation;33 non-scenario meetings have no XML assignment. The primary datasets page describes distinct scenario-only, full-corpus and full-corpus-ASR variants; XML attributes do not establish a complete person-disjoint split. IB4005 is explicitly excluded from the web full-corpus split for shared speakers. No split is invented for unspecified meetings. Five speaker tracks share a single acoustic scene and are not independent datasets or raters.",
        personal="Voice-derived spectral characteristics can encode speaker properties. Package no waveform, spoken text, names, encoded-gender global participant IDs, absolute dates or private documents. Preserve public meeting IDs and local anonymous agent letters only.",
        citation="Carletta J. (2006). Announcing the AMI Meeting Corpus. The ELRA Newsletter11(1),3–5. AMI Project corpus; primary ami_public_manual_1.6.2.zip posted2017-04-10, whose internal README identifies release1.7 dated2014-06-16. https://groups.inf.ed.ac.uk/ami/corpus/.",
        creators=["AMI Project Consortium", "Jean Carletta"],
        date_published="2017-04-10",
        null_states={t: [0] for t in LABELS},
        info={
            "source_files": pins,
            "state_names": {
                t: {0: "no_annotated_utterance", 1: "annotated_utterance"}
                for t in LABELS
            },
            "annotators": [],
            "tracks": {
                t: {
                    "local_speaker": t[-1].upper(),
                    "semantics": "manual transcriber activity; not independent raters",
                }
                for t in LABELS
            },
            "source_sampling_rate_hz": FS,
            "partition_source": "Manual1.6.2 corpusResources/meetings.xml attributes; native missing values preserved; not a reconstructed full-corpus or ASR split",
            "partition_reference_url": "https://groups.inf.ed.ac.uk/ami/corpus/datasets.shtml",
            "source_roster_counts": {
                str(k): sum(
                    len(rosters[Path(pin["url"]).name.split(".")[0]]) == k
                    for pin in selected
                )
                for k in [3, 4, 5]
            },
            "empty_absent_placeholder_slots": [
                f"{sid}.{agent}"
                for sid in [Path(pin["url"]).name.split(".")[0] for pin in selected]
                for agent in AGENTS
                if (sid, agent) in segments and agent not in rosters[sid]
            ],
            "source_annotation_sha256": ANNOTATION_SHA,
            "source_annotation_url": "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip",
            "extractor_versions": {"numpy": np.__version__, "scipy": scipy.__version__},
            "extractor": "fixed MFCC13 /25ms centered symmetric Hamming /10ms hop /FFT512 /40 continuous mel triangles /ln floor 1e-10 /ortho DCT-II /zero boundary padding /no pre-emphasis",
            "auxiliary": {
                "source-segments.parquet": "Every manual transcriber interval with literal source ID/channel, decimal transcriber and optional starttime/endtime strings, activity mapping and defect status; no transcript words."
            },
            "series_details": details,
            "series_with_positive_recurrence": positive,
            "simultaneous_speaker_frames": overlap,
        },
    )


if __name__ == "__main__":
    main()
