"""Independently reconstruct AMI MFCCs, frame clocks and manual activity tracks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import wave
import xml.etree.ElementTree as ET
import zipfile
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from tsseg_data.reader import _to_numpy_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build/ami-meeting-corpus"))
    parser.add_argument("--raw", type=Path, default=Path("raw/ami-meeting-corpus"))
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    info = json.loads((args.build / "tsseg.json").read_text())
    index = {
        r["series_id"]: r
        for r in pq.read_table(args.build / "index.parquet").to_pylist()
    }
    assert len(index) == (4 if args.pilot else 171)
    annotation = args.raw / "ami_public_manual_1.6.2.zip"
    assert (
        hashlib.sha256(annotation.read_bytes()).hexdigest()
        == info["source_annotation_sha256"]
    )
    original = {}
    present = set()
    rosters = {}
    partitions = {}
    with zipfile.ZipFile(annotation) as archive:
        for meeting in ET.fromstring(archive.read("corpusResources/meetings.xml")):
            if meeting.tag == "meeting":
                partitions[meeting.get("observation")] = {
                    key: meeting.get(key)
                    for key in ["visibility", "seen_type", "k5", "k10"]
                }
                rosters[meeting.get("observation")] = {
                    speaker.get("nxt_agent")
                    for speaker in meeting
                    if speaker.tag == "speaker"
                }
        for name in archive.namelist():
            if name.startswith("segments/") and name.endswith(".xml"):
                sid, agent, *_ = Path(name).name.split(".")
                if sid not in index:
                    continue
                present.add((sid, agent))
                for node in ET.fromstring(archive.read(name)):
                    if node.tag == "segment":
                        key = (sid, agent, node.get("{http://nite.sourceforge.net/}id"))
                        assert key not in original
                        original[key] = {
                            "start_text": node.get("transcriber_start"),
                            "end_text": node.get("transcriber_end"),
                            "source_channel": node.get("channel"),
                            "optional_starttime_text": node.get("starttime"),
                            "optional_endtime_text": node.get("endtime"),
                            "source_member": name,
                        }
    rows = pq.read_table(args.build / "source-segments.parquet").to_pylist()
    actual = {(r["series_id"], r["agent"], r["source_id"]): r for r in rows}
    assert len(actual) == len(original) == len(rows)
    if not args.pilot:
        assert len(original) == 93637
        assert sum(r["optional_starttime_text"] is not None for r in rows) == 51
    assert info["source_roster_counts"] == {
        str(size): sum(len(rosters[sid]) == size for sid in index) for size in [3, 4, 5]
    }
    for key, source in original.items():
        for field, value in source.items():
            assert actual[key][field] == value
    # Independent mel construction, analytic Hamming and explicit cosine DCT matrix.
    edges = np.array(
        [
            700 * (10 ** ((2595 * math.log10(1 + 8000 / 700) * i / 41) / 2595) - 1)
            for i in range(42)
        ]
    )
    bank = np.array(
        [
            [
                max(
                    0,
                    min(
                        (frequency - edges[j]) / (edges[j + 1] - edges[j]),
                        (edges[j + 2] - frequency) / (edges[j + 2] - edges[j + 1]),
                    ),
                )
                for j in range(40)
            ]
            for frequency in [i * 16000 / 512 for i in range(257)]
        ]
    )
    window = 0.54 - 0.46 * np.cos(2 * np.pi * np.arange(400) / 399)
    cosine = np.array(
        [
            [
                math.cos(math.pi * k * (2 * j + 1) / 80)
                * (math.sqrt(1 / 40) if k == 0 else math.sqrt(2 / 40))
                for k in range(13)
            ]
            for j in range(40)
        ]
    )
    pins = {
        Path(p["url"]).name.split(".")[0]: p
        for p in info["source_files"]["files"]
        if "sha256" in p
    }
    label_cache = {}
    verified_sources = set()
    chunks = {}
    max_error = 0.0
    total = 0
    for file in info["configs"]["default"]["files"]:
        for batch in pq.ParquetFile(args.build / file).iter_batches(batch_size=1):
            for row in _to_numpy_rows(pa.Table.from_batches([batch])):
                sid = row["series_id"]
                meta = index[sid]
                pin = pins[sid]
                source_path = args.raw / Path(pin["url"]).name
                if sid not in verified_sources:
                    assert meta["present_agents"] == sorted(rosters[sid])
                    for key, value in partitions[sid].items():
                        assert meta[f"source_{key}"] == value
                    assert source_path.stat().st_size == pin["bytes"]
                    h = hashlib.sha256()
                    with source_path.open("rb") as stream:
                        while data := stream.read(1024 * 1024):
                            h.update(data)
                    assert h.hexdigest() == pin["sha256"] == meta["source_audio_sha256"]
                    verified_sources.add(sid)
                    nframes = (meta["source_audio_samples"] + 159) // 160
                    times = np.arange(nframes, dtype=np.int64) * 10000000
                    expected_labels = {}
                    expected_issues = []
                    for agent in "ABCDE":
                        keys = [key for key in original if key[:2] == (sid, agent)]
                        y = (
                            np.zeros(nframes, dtype=np.int8)
                            if agent in rosters[sid]
                            else np.full(nframes, -1, dtype=np.int8)
                        )
                        assert (sid, agent) in present or agent not in rosters[sid]
                        assert not keys or agent in rosters[sid]
                        masks = []
                        for key in keys:
                            r = actual[key]
                            a = Decimal(r["start_text"])
                            b = Decimal(r["end_text"])
                            duration = Decimal(meta["source_audio_samples"]) / 16000
                            if b <= a or a < 0 or b > duration:
                                assert (
                                    r["status"]
                                    == (
                                        "reversed_or_empty_source_interval"
                                        if b <= a
                                        else "outside_native_audio_duration"
                                    )
                                    and r["start_feature"] is None
                                    and r["end_feature_exclusive"] is None
                                )
                                expected_issues.append(key[2])
                                low = max(Decimal(0), min(a, b))
                                high = min(duration, max(a, b))
                                masks.append((low, high))
                            else:
                                assert r["status"] == "valid"
                                first = int(
                                    np.searchsorted(
                                        times,
                                        int(
                                            (a * 10**9).to_integral_value(
                                                rounding=ROUND_CEILING
                                            )
                                        ),
                                        side="left",
                                    )
                                )
                                last = int(
                                    np.searchsorted(
                                        times,
                                        int(
                                            (b * 10**9).to_integral_value(
                                                rounding=ROUND_CEILING
                                            )
                                        ),
                                        side="left",
                                    )
                                )
                                assert (
                                    r["start_feature"],
                                    r["end_feature_exclusive"],
                                ) == (first, last)
                                y[first:last] = 1
                        for low, high in masks:
                            if high > low:
                                first = np.searchsorted(
                                    times,
                                    int(
                                        (low * 10**9).to_integral_value(
                                            rounding=ROUND_CEILING
                                        )
                                    ),
                                )
                                last = np.searchsorted(
                                    times,
                                    int(
                                        (high * 10**9).to_integral_value(
                                            rounding=ROUND_CEILING
                                        )
                                    ),
                                )
                                y[first:last] = -1
                        expected_labels[f"label_{agent.lower()}"] = y
                    assert sorted(meta["source_interval_issues"]) == sorted(
                        expected_issues
                    )
                    label_cache[sid] = expected_labels
                start = row["chunk_start"]
                end = start + row["length"]
                assert row["time_ns"].tolist() == [
                    i * 10000000 for i in range(start, end)
                ]
                for label, values in label_cache[sid].items():
                    assert np.array_equal(row[label], values[start:end])
                actual_features = np.column_stack([row[c] for c in info["channels"]])
                assert np.isfinite(actual_features).all()
                with wave.open(str(source_path), "rb") as audio:
                    n = audio.getnframes()
                    assert (
                        n == meta["source_audio_samples"]
                        and audio.getframerate() == 16000
                        and audio.getsampwidth() == 2
                        and audio.getnchannels() == pin["channels"]
                        and audio.getnchannels() == meta["source_audio_channels"]
                        and audio.getnchannels() in {1, 2}
                    )
                    for first in range(start, end, 777):
                        last = min(first + 777, end)
                        positions = np.arange(first, last, dtype=np.int64)[
                            :, None
                        ] * 160 + np.arange(-200, 200)
                        valid = (positions >= 0) & (positions < n)
                        a = max(0, int(positions.min()))
                        b = min(n, int(positions.max()) + 1)
                        audio.setpos(a)
                        samples = (
                            np.frombuffer(audio.readframes(b - a), dtype="<i2").astype(
                                np.float64
                            )
                            / 32768
                        )
                        channels = audio.getnchannels()
                        samples = (
                            np.add.reduce(samples.reshape(-1, channels), axis=1)
                            / channels
                        )
                        frames = np.zeros(positions.shape, dtype=np.float64)
                        frames[valid] = samples[(positions - a)[valid]]
                        power = (
                            np.square(
                                np.abs(np.fft.rfft(frames * window, n=512, axis=1))
                            )
                            / 512
                        )
                        logs = np.log(
                            np.maximum(
                                np.einsum("ij,jk->ik", power, bank, optimize=False),
                                1e-10,
                            )
                        )
                        expected = np.einsum(
                            "ij,jk->ik", logs, cosine, optimize=False
                        ).astype(np.float32)
                        error = float(
                            np.max(
                                np.abs(
                                    actual_features[first - start : last - start]
                                    - expected
                                )
                            )
                        )
                        max_error = max(max_error, error)
                        assert error <= 3e-5, (sid, first, error)
                chunks[sid] = chunks.get(sid, 0) + row["length"]
                total += row["length"]
    assert set(chunks) == set(index) == verified_sources
    assert all(chunks[sid] == index[sid]["length"] for sid in index)
    print(
        f"Verified{len(index)}/{len(index)} meetings, {total} MFCC13 frames; independent numpyFFT/analytic-window/mel/cosine-DCT maximum absolute error{max_error:.9g} (bound3e-5), exact every speaker label/time/source segment, native PCM lengths and SHA; no mismatches."
    )


if __name__ == "__main__":
    main()
