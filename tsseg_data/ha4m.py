"""Bounded native HA4M skeleton acquisition and deterministic member digests."""

from __future__ import annotations

import gzip
import hashlib
import io
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

SHARE = "https://cloud.cnr.it/owncloud/index.php/s/j5BZvG1sXPzh6x1"
DAV = "https://cloud.cnr.it/owncloud/public.php/webdav"
RESERVE = 18 * 2**30
INVALID_BODY_ID = 0xFFFFFFFF
FIELDS = [
    "Confidance",
    "X",
    "Y",
    "Z",
    "Qw",
    "Qx",
    "Qy",
    "Qz",
    "X2DColor",
    "Y2DColor",
    "X2DDepth",
    "Y2DDepth",
]
HEADER = "\t".join(["BodyID", "JointID", *FIELDS])
CHANNELS = [f"joint{j:02}_{c.lower()}" for j in range(32) for c in FIELDS]
PATTERN = re.compile(r"Skeletons/(\d+)/FrameID(\d+)_DeviceTimeStamp(\d+)us\.txt")


def download(url, limit):
    """Read one bounded response in memory; never buffer a complete corpus."""
    with urllib.request.urlopen(url, timeout=180) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f"Response exceeds bounded byte limit {limit}: {url}")
    return data


def urls(trial):
    query = urllib.parse.urlencode({"path": f"/{trial}", "files": "Skeletons"})
    return (
        f"{SHARE}/download?{query}",
        f"{SHARE}/download?path=%2F{trial}&files=Labels.txt",
    )


def acquire(root, trial, source_bytes, expected=None):
    """Losslessly gzip the dynamic ZIP envelope, pin its native member content.

    ownCloud generates a ZIP without useful compression. Its envelope can change
    between requests. The SHA256 contract covers sorted native names, lengths and
    bytes with explicit length prefixes, independent of ZIP dates/metadata.
    """
    assert re.fullmatch(r"IDU\d{3}V\d{3}", trial), trial
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    cache = root / f"{trial}.zip.gz"
    labels = root / f"{trial}.Labels.txt"
    zip_url, label_url = urls(trial)
    if not cache.exists():
        if shutil.disk_usage(root).free - source_bytes * 2 < RESERVE:
            raise RuntimeError("Insufficient 18-GiB reserve for trial acquisition")
        raw = download(zip_url, int(source_bytes * 1.3) + 2**20)
        # Validate ZIP structure and canonical content before accepting the cache.
        describe(raw)
        temporary = cache.with_suffix(".gz.part")
        with temporary.open("wb") as stream:
            with gzip.GzipFile(fileobj=stream, filename="", mode="wb", mtime=0) as out:
                out.write(raw)
        temporary.replace(cache)
    else:
        with gzip.open(cache, "rb") as stream:
            raw = stream.read(int(source_bytes * 1.3) + 2**20 + 1)
        if len(raw) > int(source_bytes * 1.3) + 2**20:
            raise RuntimeError("Oversized cached source ZIP")
    if not labels.exists():
        labels.write_bytes(download(label_url, 2**20))
    info = describe(raw)
    info.update(
        {
            "label_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
            "label_bytes": labels.stat().st_size,
            "zip_url": zip_url,
            "label_url": label_url,
            "zip_bytes": len(raw),
            "gzip_cache_bytes": cache.stat().st_size,
        }
    )
    if expected is not None:
        for key in [
            "canonical_sha256",
            "source_bytes",
            "native_frames",
            "label_sha256",
            "label_bytes",
        ]:
            if info[key] != expected[key]:
                raise RuntimeError(f"Pinned native source mismatch for {trial}: {key}")
    return raw, labels.read_bytes(), info


def members(raw):
    """Read native members with ZIP CRC validation, rejecting unexpected paths."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        assert 0 < len(names) <= 30000 and len(set(names)) == len(names)
        assert sum(x.file_size for x in archive.infolist()) <= 128 * 2**20
        assert all(x.file_size <= 65536 for x in archive.infolist())
        for name in sorted(names):
            match = PATTERN.fullmatch(name)
            assert match, name
            yield name, match, archive.read(name)


def describe(raw):
    digest = hashlib.sha256()
    size, count, cameras = 0, 0, set()
    for name, match, data in members(raw):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(data)
        size += len(data)
        count += 1
        cameras.add(match[1])
    assert count and len(cameras) == 1
    return {
        "canonical_sha256": digest.hexdigest(),
        "source_bytes": size,
        "native_frames": count,
        "camera": next(iter(cameras)),
    }


def decode(raw, label_bytes):
    """Keep the union of source frame IDs, with NaNs for missing skeletons."""
    records, unassigned = [], []
    for name, match, data in members(raw):
        assert data.splitlines()[0].decode() == HEADER, name
        values = np.loadtxt(io.BytesIO(data), skiprows=1, dtype=np.float64)
        assert values.ndim == 2 and values.shape[1] == 14
        assert len(values) % 32 == 0 and np.isfinite(values).all(), name
        valid = []
        for block_index, block in enumerate(values.reshape(-1, 32, 14)):
            assert np.array_equal(block[:, 1], np.arange(32)), name
            ids = np.unique(block[:, 0])
            assert len(ids) == 1 and ids[0] == int(ids[0]), name
            body = int(ids[0])
            assert 0 <= body <= INVALID_BODY_ID
            observations = block[:, 2:].astype(np.float32).reshape(-1)
            if body == INVALID_BODY_ID:
                # SDK explicitly marks this ID invalid, yet the exporter retains
                # nonzero estimates. Preserve every value as unassigned data.
                unassigned.append(
                    {
                        "frame_id": int(match[2]),
                        "source_block_index": block_index,
                        "source_body_id": body,
                        "reason": "invalid_sdk_body_id",
                        "values": observations,
                    }
                )
            else:
                valid.append((body, observations, block_index))
        if len(valid) > 1:
            # A frame label cannot identify which of several valid bodies is the
            # annotated participant. Retain every block; leave main pose unknown.
            for body, observations, block_index in valid:
                unassigned.append(
                    {
                        "frame_id": int(match[2]),
                        "source_block_index": block_index,
                        "source_body_id": body,
                        "reason": "multiple_valid_body_ids",
                        "values": observations,
                    }
                )
        body, observations = (
            valid[0][:2]
            if len(valid) == 1
            else (-1, np.full(384, np.nan, dtype=np.float32))
        )
        records.append((int(match[2]), int(match[3]), body, observations))
    labels = np.loadtxt(io.BytesIO(label_bytes), dtype=np.int32)
    assert labels.ndim == 2 and labels.shape[1] == 3
    assert np.all(labels[:, 0] >= 0) and len(set(labels[:, 0])) == len(labels)
    assert np.isin(labels[:, 1], np.arange(13)).all()
    assert np.isin(labels[:, 2], [0, 1, 2]).all()
    frame_ids = [r[0] for r in records]
    assert len(frame_ids) == len(set(frame_ids))
    n = max(max(frame_ids), int(labels[:, 0].max())) + 1
    assert 0 < n <= 100000, "Unexpected frame range"
    x = np.full((n, len(CHANNELS)), np.nan, dtype=np.float32)
    timestamps = np.full(n, -1, dtype=np.int64)
    body_ids = np.full(n, -1, dtype=np.int64)
    action = np.full(n, -1, dtype=np.int8)
    repetition = np.full(n, -1, dtype=np.int8)
    for frame, timestamp, body, row in records:
        x[frame] = row
        timestamps[frame] = timestamp
        body_ids[frame] = body
    action[labels[:, 0]] = labels[:, 1]
    repetition[labels[:, 0]] = labels[:, 2]
    return x, timestamps, body_ids, action, repetition, unassigned


def qualify_label_associations(root, pins):
    """Pin later primary-author GT as evidence for two original CSV associations.

    Evidence files are NOT rehosted: the feature repository has no licence grant.
    Published values come only from the original CC-BY CSVs. The complete action
    vector, not merely its length, must equal the author's later trial-level GT.
    """
    root = Path(root)
    corrections = {}
    for trial, annotation_trial in [
        ("IDU039V001", "IDU039V002"),
        ("IDU039V002", "IDU039V001"),
    ]:
        name = f"features-{trial}.txt"
        url = (
            "https://cloud.cnr.it/owncloud/index.php/s/ZBrMapYdFkL6xy2/download?"
            + urllib.parse.urlencode({"path": "/groundTruth", "files": f"{trial}.txt"})
        )
        path = root / name
        if not path.exists():
            path.write_bytes(download(url, 2**20))
        evidence = path.read_bytes()
        assigned_labels = (root / f"{annotation_trial}.Labels.txt").read_bytes()
        values = np.loadtxt(io.BytesIO(assigned_labels), dtype=np.int64)
        author = np.loadtxt(io.BytesIO(evidence), dtype=np.int64)
        assert np.array_equal(values[:, 1], author), trial
        raw, _, _ = acquire(root, trial, pins[trial]["source_bytes"], pins[trial])
        x, timestamps, bodies, action, repetition, unassigned = decode(
            raw, assigned_labels
        )
        pins[trial].update(
            {
                "frames": len(x),
                "missing_skeletons": int((bodies == -1).sum()),
                "missing_labels": int((action == -1).sum()),
                "source_label_trial": annotation_trial,
            }
        )
        corrections[trial] = {
            "source_label_trial": annotation_trial,
            "author_ground_truth": {
                "filename": name,
                "url": url,
                "sha256": hashlib.sha256(evidence).hexdigest(),
                "bytes": len(evidence),
                "action_rows": len(author),
                "evidence_only": True,
                "rights": "No explicit licence found in author feature repository; do not rehost evidence file.",
            },
            "evidence_repository": "https://github.com/ispstiima/HA4Mfeatures",
            "comparison": "Every original CC-BY action value matches later primary-author GT under this association; no signal-content or length optimization.",
        }
    return corrections
