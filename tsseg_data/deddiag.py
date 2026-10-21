"""Read the primary DEDDIAG sparse measurements without database execution."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

RESERVE = 18 * 2**30
SECOND = 10**9


def storage_gate(root, pins):
    """Reserve the complete measured output, remaining source and bounded scratch."""
    root = Path(root)
    gate = pins["storage_gate"]
    remaining = sum(
        max(
            0,
            pin["size"]
            - (
                (root / pin["name"]).stat().st_size
                if (root / pin["name"]).exists()
                else (
                    (root / (pin["name"] + ".part")).stat().st_size
                    if (root / (pin["name"] + ".part")).exists()
                    else 0
                )
            ),
        )
        for pin in pins["files"]
    )
    free = shutil.disk_usage(root).free
    required = remaining + gate["output_with_margin_bytes"] + gate["scratch_bytes"]
    if free - required < RESERVE:
        raise RuntimeError(
            f"Full corpus gate fails: free={free}, required={required}, "
            f"reserve={RESERVE}"
        )
    return {
        "free_bytes": free,
        "remaining_source_bytes": remaining,
        "output_and_scratch_bytes": required - remaining,
        "projected_free_bytes": free - required,
        "reserve_bytes": RESERVE,
    }


def metadata(audit):
    items, definitions, annotations = [], [], []
    for _archive_name, details in sorted(audit.items()):
        for member, text in details["selected_text"].items():
            rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
            for index, row in enumerate(rows):
                record = {**row, "source_member": member, "source_row_index": index}
                if member.endswith("items.tsv"):
                    items.append(record)
                elif member.endswith("_annotation_labels.tsv"):
                    definitions.append(record)
                elif member.endswith("_annotations.tsv"):
                    record["start_ns"] = int(
                        pd.Timestamp(row["start_date"], tz="UTC").value
                    )
                    record["stop_ns"] = int(
                        pd.Timestamp(row["stop_date"], tz="UTC").value
                    )
                    assert record["start_ns"] <= record["stop_ns"]
                    annotations.append(record)
    assert len(items) == 54 and len(definitions) == 37 and len(annotations) == 1738
    assert len({int(r["id"]) for r in annotations}) == 1738
    return items, definitions, annotations


def event_runs(annotations):
    """Exact closed whole-second source intervals, retaining co-active labels."""
    edges = {}
    for row in annotations:
        assert row["start_ns"] % SECOND == row["stop_ns"] % SECOND == 0
        label = int(row["label_id"])
        edges.setdefault(row["start_ns"], []).append((label, 1))
        edges.setdefault(row["stop_ns"] + SECOND, []).append((label, -1))
    active, result = {}, []
    keys = sorted(edges)
    for index, key in enumerate(keys):
        for label, delta in edges[key]:
            active[label] = active.get(label, 0) + delta
            assert active[label] >= 0
        labels = tuple(sorted(label for label, count in active.items() if count))
        if labels and index + 1 < len(keys):
            result.append((key, keys[index + 1], labels))
    assert not any(active.values())
    return result


def label_values(times, runs, codebook):
    """Round only for association with the annotation UI; native times stay intact."""
    labels = np.full(len(times), -1, dtype=np.int32)
    for start, stop, active in runs:
        # Integer ceil(time/second-0.5) bounds select nearest-second associations.
        first = int(np.searchsorted(times, start - SECOND // 2, side="left"))
        last = int(np.searchsorted(times, stop - SECOND // 2, side="left"))
        labels[first:last] = codebook[active]
    # PostgreSQL round(float8) has platform-dependent tie handling. Only exact
    # half-second boundary cases with distinct adjacent sets are left unscored.
    ambiguous = 0
    boundaries = sorted({value - SECOND // 2 for run in runs for value in run[:2]})
    for edge in boundaries:
        a = int(np.searchsorted(times, edge, side="left"))
        b = int(np.searchsorted(times, edge, side="right"))
        if b <= a:
            continue
        before = tuple(
            next((r[2] for r in runs if r[0] <= edge - SECOND // 2 < r[1]), ())
        )
        after = tuple(
            next((r[2] for r in runs if r[0] <= edge + SECOND // 2 < r[1]), ())
        )
        if before != after:
            labels[a:b] = -1
            ambiguous += b - a
    return labels, ambiguous


def read_measurements(archive, member, work):
    """Stream gzip/TSV into reusable binary scratch, then stable chronological sort."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    times_path, values_path = work / "native-times.bin", work / "native-values.bin"
    n, reversals, adjacent_duplicates, previous = 0, 0, 0, None
    with times_path.open("wb") as times_file, values_path.open("wb") as values_file:
        with gzip.GzipFile(fileobj=archive.open(member)) as source:
            for frame in pd.read_csv(
                source,
                sep="\t",
                chunksize=250000,
                dtype={"item_id": "int32", "time": "str", "value": "float64"},
                float_precision="round_trip",
                na_values=["\\N"],
            ):
                assert list(frame.columns) == ["item_id", "time", "value"]
                item_id = int(Path(member).name.split("_")[1])
                assert np.all(frame["item_id"].to_numpy() == item_id)
                times = (
                    pd.to_datetime(frame["time"], format="mixed", utc=True)
                    .astype("int64")
                    .to_numpy()
                )
                assert np.all(times != np.iinfo(np.int64).min)
                values = frame["value"].to_numpy(np.float64)
                delta = np.diff(times)
                reversals += int(np.count_nonzero(delta < 0)) + int(
                    previous is not None and times[0] < previous
                )
                adjacent_duplicates += int(np.count_nonzero(delta == 0)) + int(
                    previous is not None and times[0] == previous
                )
                previous = int(times[-1])
                if (
                    shutil.disk_usage(work).free - times.nbytes - values.nbytes - 2**30
                    < RESERVE
                ):
                    raise RuntimeError(
                        "18 GiB reserve plus scratch/write allowance unavailable"
                    )
                times.astype("<i8", copy=False).tofile(times_file)
                values.astype("<f8", copy=False).tofile(values_file)
                n += len(times)
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    # Stable sort, native vectors, labels, Arrow concatenation and compression
    # coexist briefly. Refuse the trace before allocating those full arrays.
    working_bound = n * 72 + 2**30
    if working_bound > available:
        raise MemoryError(
            f"Trace {member}: conservative RAM bound {working_bound} exceeds "
            f"available {available}; preserve compressed source and checkpoint"
        )
    original_t = np.memmap(times_path, mode="r", dtype="<i8", shape=(n,))
    original_v = np.memmap(values_path, mode="r", dtype="<f8", shape=(n,))
    order = np.argsort(original_t, kind="stable")
    sorted_t, sorted_v = np.asarray(original_t[order]), np.asarray(original_v[order])
    return (
        sorted_t,
        sorted_v,
        order,
        {
            "source_adjacent_reversals": reversals,
            "source_adjacent_duplicates": adjacent_duplicates,
            "sorted_duplicate_times": int(
                np.count_nonzero(sorted_t[1:] == sorted_t[:-1])
            ),
        },
    )


def provenance_runs(sid, order):
    """Compact exact source-row index for each observation via consecutive runs."""
    start = 0
    for position in range(0, len(order), 262144):
        end = min(len(order), position + 262144)
        a = max(1, position)
        breaks = np.flatnonzero(order[a:end] != order[a - 1 : end - 1] + 1) + a
        for boundary in breaks:
            yield {
                "series_id": sid,
                "sorted_start": start,
                "source_start": int(order[start]),
                "length": int(boundary - start),
            }
            start = int(boundary)
    yield {
        "series_id": sid,
        "sorted_start": start,
        "source_start": int(order[start]),
        "length": len(order) - start,
    }


def acquire(root, pin, allow_new=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / pin["name"]
    size = pin["size"]
    if not path.exists():
        partial = path.with_suffix(path.suffix + ".part")
        checkpoint = path.with_suffix(path.suffix + ".http.json")
        identity = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        if partial.exists() and identity is None:
            partial.write_bytes(b"")
        offset = partial.stat().st_size if partial.exists() else 0
        while offset < size:
            last = min(offset + 32 * 2**20, size) - 1
            length = last - offset + 1
            if shutil.disk_usage(root).free - length - 64 * 2**20 < RESERVE:
                raise RuntimeError("18 GiB reserve unavailable")
            for attempt in range(5):
                command = [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "180",
                    "--range",
                    f"{offset}-{last}",
                    "--max-filesize",
                    str(length),
                    "-D",
                    "/dev/stderr",
                ]
                if identity:
                    command += ["-H", f"If-Range: {identity['etag']}"]
                response = subprocess.run(
                    command + [pin["download_url"]], capture_output=True
                )
                if response.returncode:
                    if attempt == 4:
                        raise RuntimeError(response.stderr.decode(errors="replace"))
                    time.sleep(min(2**attempt, 8))
                    continue
                headers = response.stderr
                assert len(headers) < 65536
                assert re.findall(rb"^HTTP/\S+ (\d+)", headers, re.M)[-1] == b"206"
                interval = re.findall(
                    rb"^Content-Range: bytes (\d+)-(\d+)/(\d+)", headers, re.M | re.I
                )[-1]
                assert tuple(map(int, interval)) == (offset, last, size)
                assert len(response.stdout) == length
                etags = re.findall(rb"^ETag: ([^\r\n]+)", headers, re.M | re.I)
                assert etags
                current = {
                    "etag": etags[-1].decode("ascii"),
                    "size": size,
                    "url": pin["download_url"],
                }
                assert identity is None or identity == current, (
                    "Source identity changed"
                )
                if identity is None:
                    identity = current
                    temporary = checkpoint.with_suffix(".json.part")
                    temporary.write_text(json.dumps(identity) + "\n")
                    temporary.replace(checkpoint)
                with partial.open("ab") as stream:
                    for start in range(0, length, 2**20):
                        block = response.stdout[start : start + 2**20]
                        if (
                            shutil.disk_usage(root).free - len(block) - 64 * 2**20
                            < RESERVE
                        ):
                            raise RuntimeError("18 GiB reserve unavailable")
                        stream.write(block)
                offset += length
                print(pin["name"], offset, size, flush=True)
                break
        candidate = partial
    else:
        candidate = path
    assert candidate.stat().st_size == size
    md5, sha = hashlib.md5(), hashlib.sha256()
    with candidate.open("rb") as stream:
        while block := stream.read(2**20):
            md5.update(block)
            sha.update(block)
    assert md5.hexdigest() == pin["computed_md5"]
    digest = sha.hexdigest()
    if "sha256" in pin:
        assert digest == pin["sha256"]
    elif not allow_new:
        raise RuntimeError("SHA pin required")
    pin["sha256"] = digest
    if candidate != path:
        candidate.rename(path)
    return path
