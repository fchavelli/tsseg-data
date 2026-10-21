"""Bounded AMI audio acquisition, fixed MFCCs and manual segment activity tracks."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
import wave
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from pathlib import Path

import numpy as np
from scipy.fft import dct, rfft

from .sources import sha256

RESERVE = 18 * 2**30
FS = 16000
HOP = 160
WINDOW = 400
NFFT = 512
MELS = 40
COEFFS = 13
AGENTS = list("ABCDE")


def acquire(root, pin, allow_new=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    name = Path(pin["url"]).name
    path = root / name
    if path.exists():
        assert path.stat().st_size == pin["bytes"]
        digest = sha256(path)
    else:
        if shutil.disk_usage(root).free - pin["bytes"] - 64 * 2**20 < RESERVE:
            raise RuntimeError("Audio transfer breaches18GiB reserve")
        partial = path.with_suffix(path.suffix + ".part")
        checkpoint = partial.with_suffix(partial.suffix + ".http.json")
        identity = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        if partial.exists() and identity is None:
            # Historical partials have no HTTP identity; restart only this WAV.
            partial.write_bytes(b"")
        total = partial.stat().st_size if partial.exists() else 0
        assert 0 <= total <= pin["bytes"]
        while total < pin["bytes"]:
            last = min(total + 32 * 2**20, pin["bytes"]) - 1
            length = last - total + 1
            if shutil.disk_usage(root).free - length - 64 * 2**20 < RESERVE:
                raise RuntimeError("Range transfer breaches18GiB reserve")
            for attempt in range(5):
                command = [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "180",
                    "--range",
                    f"{total}-{last}",
                    "--max-filesize",
                    str(length),
                    "-D",
                    "/dev/stderr",
                ]
                if identity:
                    command += ["-H", f"If-Range: {identity['etag']}"]
                result = subprocess.run(command + [pin["url"]], capture_output=True)
                if result.returncode:
                    print(
                        f"Retry {name} offset={total} attempt={attempt + 1} curl={result.returncode}",
                        flush=True,
                    )
                    if attempt == 4:
                        raise RuntimeError(result.stderr.decode(errors="replace"))
                    time.sleep(min(2**attempt, 8))
                    continue
                headers = result.stderr
                assert len(headers) < 65536
                statuses = re.findall(rb"^HTTP/\S+ (\d+)", headers, re.M)
                ranges = re.findall(
                    rb"^Content-Range: bytes (\d+)-(\d+)/(\d+)", headers, re.M | re.I
                )
                assert statuses[-1] == b"206", (name, statuses)
                assert tuple(map(int, ranges[-1])) == (total, last, pin["bytes"])
                assert len(result.stdout) == length
                etags = re.findall(rb"^ETag: ([^\r\n]+)", headers, re.M | re.I)
                assert etags, (name, "Primary range has no ETag")
                current = {
                    "etag": etags[-1].decode("ascii"),
                    "bytes": pin["bytes"],
                    "url": pin["url"],
                }
                if identity:
                    assert identity == current, (name, "Source changed during transfer")
                else:
                    identity = current
                    identity_temp = checkpoint.with_suffix(".json.part")
                    identity_temp.write_text(json.dumps(identity) + "\n")
                    identity_temp.replace(checkpoint)
                with partial.open("ab") as output:
                    for offset in range(0, length, 2**20):
                        block = result.stdout[offset : offset + 2**20]
                        if (
                            shutil.disk_usage(root).free - len(block) - 64 * 2**20
                            < RESERVE
                        ):
                            raise RuntimeError("18GiB reserve violation")
                        output.write(block)
                total += length
                break
        assert partial.stat().st_size == pin["bytes"]
        digest = sha256(partial)
        if identity:
            pin["http_etag"] = identity["etag"]
        if "sha256" in pin:
            assert digest == pin["sha256"]
        elif not allow_new:
            raise RuntimeError("Missing SHA pin")
        partial.rename(path)
    if "sha256" in pin:
        assert digest == pin["sha256"]
    elif not allow_new:
        raise RuntimeError("Missing SHA pin")
    pin["sha256"] = digest
    layout = riff_layout(path)
    if "riff_layout" in pin:
        assert layout == pin["riff_layout"]
    with wave.open(str(path), "rb") as source:
        for key, value in {
            "source_samples": source.getnframes(),
            "sample_rate_hz": source.getframerate(),
            "channels": source.getnchannels(),
            "sample_width_bytes": source.getsampwidth(),
        }.items():
            if key in pin:
                assert pin[key] == value, (path.name, key)
    return path


def filters():
    hz = np.arange(NFFT // 2 + 1) * FS / NFFT
    edges = 700 * (
        10 ** (np.linspace(0, 2595 * math.log10(1 + FS / 2 / 700), MELS + 2) / 2595) - 1
    )
    bank = np.maximum(
        0,
        np.minimum(
            (hz[:, None] - edges[:-2]) / (edges[1:-1] - edges[:-2]),
            (edges[2:] - hz[:, None]) / (edges[2:] - edges[1:-1]),
        ),
    )
    return bank


def extract(path):
    """Centered25ms windows/10ms hops, symmetric Hamming, fixed MFCC13."""
    bank = filters()
    window = np.hamming(WINDOW)
    with wave.open(str(path), "rb") as audio:
        assert (
            audio.getframerate() == FS
            and audio.getnchannels() in {1, 2}
            and audio.getsampwidth() == 2
            and audio.getcomptype() == "NONE"
        )
        n = audio.getnframes()
        count = (n + HOP - 1) // HOP
        result = np.empty((count, COEFFS), np.float32)
        # Exactly10s worth of feature centers per batch. Left/right padding is zero.
        for start in range(0, count, 1000):
            end = min(start + 1000, count)
            first = start * HOP - WINDOW // 2
            last = (end - 1) * HOP + WINDOW // 2
            a = max(0, first)
            b = min(n, last)
            audio.setpos(a)
            pcm = (
                np.frombuffer(audio.readframes(b - a), dtype="<i2").astype(np.float64)
                / 32768
            )
            # Native stereo mixes are reduced explicitly, before windowing/FFT.
            pcm = pcm.reshape(-1, audio.getnchannels()).mean(axis=1)
            samples = np.pad(pcm, (a - first, last - b))
            frames = np.lib.stride_tricks.sliding_window_view(samples, WINDOW)[::HOP]
            assert len(frames) == end - start
            power = np.abs(rfft(frames * window, n=NFFT, axis=1)) ** 2 / NFFT
            logs = np.log(
                np.maximum(np.einsum("ij,jk->ik", power, bank, optimize=False), 1e-10)
            )
            result[start:end] = dct(logs, type=2, norm="ortho", axis=1)[
                :, :COEFFS
            ].astype(np.float32)
    return result, n


def segment_source(archive_path):
    """Read released manual transcriber interval times; never execute source code."""
    segments = {}
    rosters = {}
    partitions = {}
    with zipfile.ZipFile(archive_path) as archive:
        root = ET.fromstring(archive.read("corpusResources/meetings.xml"))
        for meeting in root:
            if meeting.tag == "meeting":
                partitions[meeting.get("observation")] = {
                    key: meeting.get(key)
                    for key in ["visibility", "seen_type", "k5", "k10"]
                }
                rosters[meeting.get("observation")] = [
                    s.get("nxt_agent") for s in meeting if s.tag == "speaker"
                ]
        for name in archive.namelist():
            if not name.startswith("segments/") or not name.endswith(".xml"):
                continue
            sid, agent, *_ = Path(name).name.split(".")
            data = archive.read(name)
            assert len(data) < 2**20
            values = []
            for node in ET.fromstring(data):
                if node.tag == "segment":
                    values.append(
                        {
                            "series_id": sid,
                            "agent": agent,
                            "source_id": node.get("{http://nite.sourceforge.net/}id"),
                            "start_text": node.get("transcriber_start"),
                            "end_text": node.get("transcriber_end"),
                            "source_channel": node.get("channel"),
                            "optional_starttime_text": node.get("starttime"),
                            "optional_endtime_text": node.get("endtime"),
                            "source_member": name,
                        }
                    )
            segments[(sid, agent)] = values
    return segments, rosters, partitions


def activity(sid, nframes, audio_samples, segments, roster):
    labels = {}
    rows = []
    issues = []
    for agent in AGENTS:
        key = (sid, agent)
        y = np.full(nframes, -1, dtype=np.int8)
        if agent not in roster:
            assert not segments.get(key, []), (
                sid,
                agent,
                "annotated agent absent from roster",
            )
            labels[f"label_{agent.lower()}"] = y
            continue
        assert key in segments, (sid, agent, "missing expected speaker segments")
        y[:] = 0
        bad = []
        for original in segments[key]:
            row = dict(original)
            a = Decimal(row["start_text"])
            b = Decimal(row["end_text"])
            row["status"] = "valid"
            row["start_feature"] = None
            row["end_feature_exclusive"] = None
            if b <= a:
                row["status"] = "reversed_or_empty_source_interval"
                bad.append((min(a, b), max(a, b)))
                issues.append(row["source_id"])
            elif a < 0 or b > Decimal(audio_samples) / FS:
                row["status"] = "outside_native_audio_duration"
                bad.append((max(Decimal(0), a), min(Decimal(audio_samples) / FS, b)))
                issues.append(row["source_id"])
            else:
                first = int((a * 100).to_integral_value(rounding="ROUND_CEILING"))
                last = int((b * 100).to_integral_value(rounding="ROUND_CEILING"))
                y[first:last] = 1
                row["start_feature"] = first
                row["end_feature_exclusive"] = last
            rows.append(row)
        for a, b in bad:
            a = max(Decimal(0), a)
            b = min(Decimal(audio_samples) / FS, b)
            if b <= a:
                continue
            first = max(0, int((a * 100).to_integral_value(rounding="ROUND_CEILING")))
            last = min(
                nframes, int((b * 100).to_integral_value(rounding="ROUND_CEILING"))
            )
            y[first:last] = -1
        labels[f"label_{agent.lower()}"] = y
    return labels, rows, issues


def riff_layout(path):
    """Audit all RIFF chunk headers without reading non-audio metadata payloads."""
    import struct

    path = Path(path)
    size = path.stat().st_size
    chunks = []
    data_blocks = []
    with path.open("rb") as stream:
        header = stream.read(12)
        assert header[:4] == b"RIFF" and header[8:] == b"WAVE"
        declared = struct.unpack_from("<I", header, 4)[0] + 8
        position = 12
        while position + 8 <= size:
            stream.seek(position)
            tag, length = struct.unpack("<4sI", stream.read(8))
            assert position + 8 + length <= size, (path.name, tag, length, size)
            chunks.append(tag.decode("ascii", errors="backslashreplace"))
            if tag == b"data":
                data_blocks.append({"offset": position + 8, "bytes": length})
            position += 8 + length + (length % 2)
    assert len(data_blocks) == 1, (path.name, "multiple/absent PCM blocks")
    with wave.open(str(path), "rb") as source:
        assert (
            data_blocks[0]["bytes"]
            == source.getnframes() * source.getnchannels() * source.getsampwidth()
        )
    return {
        "chunk_tags": chunks,
        "declared_riff_bytes": declared,
        "pcm_data_bytes": data_blocks[0]["bytes"],
        "bytes_after_pcm": size - data_blocks[0]["offset"] - data_blocks[0]["bytes"],
    }
