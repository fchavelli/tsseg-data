"""Bounded primary WESAD acquisition and numeric-only source decoding."""

from __future__ import annotations

import hashlib
import json
import pickle
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

RESERVE = 18 * 2**30
URL = "https://uni-siegen.sciebo.de/public.php/dav/files/HGdUkoNlW1Ub0Gx"
SIZE = 2249444501
MD5 = "e328980e7992502de30c96ba2a7cb3e2"
SHA1 = "bae786bf599ef28e42e1c2e18da9b84d685e84e7"
SUBJECTS = [f"S{i}" for i in range(2, 18) if i != 12]
CHEST = {
    "ACC": [f"chest_acc_{a}" for a in "xyz"],
    "ECG": ["chest_ecg"],
    "EDA": ["chest_eda"],
    "EMG": ["chest_emg"],
    "Resp": ["chest_respiration"],
    "Temp": ["chest_temperature"],
}
WRIST = {
    "acc": (32, {"ACC": [f"wrist_acc_{a}" for a in "xyz"]}),
    "bvp": (64, {"BVP": ["wrist_bvp"]}),
    "slow": (4, {"EDA": ["wrist_eda"], "TEMP": ["wrist_temperature"]}),
}


def acquire(root, pin=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "WESAD.zip"
    partial = path.with_suffix(".zip.part")
    if not path.exists():
        identity_path = root / "transfer-identity.json"
        identity = (
            json.loads(identity_path.read_text()) if identity_path.exists() else None
        )
        if partial.exists() and identity is None:
            partial.write_bytes(b"")
        offset = partial.stat().st_size if partial.exists() else 0
        assert offset <= SIZE
        while offset < SIZE:
            end = min(offset + 32 * 2**20, SIZE) - 1
            length = end - offset + 1
            if shutil.disk_usage(root).free - length - 64 * 2**20 < RESERVE:
                raise RuntimeError("18 GiB reserve unavailable")
            for attempt in range(5):
                command = [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "180",
                    "--range",
                    f"{offset}-{end}",
                    "--max-filesize",
                    str(length),
                    "-D",
                    "/dev/stderr",
                ]
                if identity:
                    command += ["-H", f"If-Range: {identity['etag']}"]
                response = subprocess.run(command + [URL], capture_output=True)
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
                assert tuple(map(int, interval)) == (offset, end, SIZE)
                assert len(response.stdout) == length
                etag = re.findall(rb"^ETag: ([^\r\n]+)", headers, re.M | re.I)[
                    -1
                ].decode("ascii")
                current = {"etag": etag, "bytes": SIZE, "url": URL}
                assert identity is None or identity == current, (
                    "Source changed during transfer"
                )
                if identity is None:
                    identity = current
                    temporary = identity_path.with_suffix(".json.part")
                    temporary.write_text(json.dumps(identity) + "\n")
                    temporary.replace(identity_path)
                with partial.open("ab") as stream:
                    for position in range(0, length, 2**20):
                        block = response.stdout[position : position + 2**20]
                        if (
                            shutil.disk_usage(root).free - len(block) - 64 * 2**20
                            < RESERVE
                        ):
                            raise RuntimeError("18 GiB reserve unavailable")
                        stream.write(block)
                offset += length
                print("source_bytes", offset, SIZE, flush=True)
                break
        candidate = partial
    else:
        candidate = path
    assert candidate.stat().st_size == SIZE
    hashes = {name: hashlib.new(name) for name in ["md5", "sha1", "sha256"]}
    with candidate.open("rb") as stream:
        while block := stream.read(2**20):
            for digest in hashes.values():
                digest.update(block)
    values = {name: digest.hexdigest() for name, digest in hashes.items()}
    assert values["md5"] == MD5 and values["sha1"] == SHA1
    if pin:
        assert values["sha256"] == pin["sha256"]
    if candidate != path:
        candidate.rename(path)
    return path, values


class _ArrayToken:
    def __new__(cls, *args, **kwargs):
        raise pickle.UnpicklingError("Direct ndarray calls forbidden")


def _reconstruct(subtype, shape, dtype):
    if subtype is not _ArrayToken or shape != (0,) or dtype not in ["b", b"b"]:
        raise pickle.UnpicklingError("Unexpected ndarray reconstruction")
    from numpy._core.multiarray import _reconstruct as reconstruct

    return reconstruct(np.ndarray, (0,), b"b")


def _dtype(*args):
    result = np.dtype(*args)
    if (
        result.hasobject
        or result.fields
        or result.subdtype
        or result.kind not in "biufSU"
    ):
        raise pickle.UnpicklingError("Unsafe dtype")
    return result


class NumericUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        allowed = {
            ("numpy.core.multiarray", "_reconstruct"): _reconstruct,
            ("numpy._core.multiarray", "_reconstruct"): _reconstruct,
            ("numpy", "ndarray"): _ArrayToken,
            ("numpy", "dtype"): _dtype,
        }
        if (module, name) not in allowed:
            raise pickle.UnpicklingError(f"Forbidden global {module}.{name}")
        return allowed[(module, name)]

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("Persistent IDs forbidden")


def load_subject(archive, sid):
    name = f"WESAD/{sid}/{sid}.pkl"
    entry = archive.getinfo(name)
    assert entry.file_size < 2 * 2**30
    with archive.open(entry) as stream:
        value = NumericUnpickler(stream, encoding="latin1").load()
        assert stream.read(1) == b""
    assert isinstance(value, dict) and set(value) == {"subject", "signal", "label"}
    assert value["subject"] == sid
    assert set(value["signal"]) == {"chest", "wrist"}
    return value


def channels(data, mapping):
    assert set(data) == set(mapping)
    result = {}
    for source, names in mapping.items():
        array = np.asarray(data[source])
        assert array.dtype.kind in "biuf" and array.ndim == 2
        assert array.shape[1] == len(names) and len(array) > 0
        for column, name in enumerate(names):
            result[name] = array[:, column]
    assert len({len(a) for a in result.values()}) == 1
    return result


class NativeWriter:
    """Shared auxiliary tables with exact values promoted losslessly to float64."""

    def __init__(self, root, group, names, rate, auxiliary, integer=False):
        self.root, self.group, self.rate = Path(root), group, rate
        self.names, self.auxiliary = names, auxiliary
        self.schema = pa.schema(
            [
                ("series_id", pa.string()),
                ("sample_index", pa.int64()),
                *[(name, pa.int8() if integer else pa.float64()) for name in names],
            ]
        )
        self.part, self.writer, self.path = -1, None, None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.writer:
            self.writer.close()

    def write(self, sid, values):
        n = len(next(iter(values.values())))
        for start in range(0, n, 262144):
            if shutil.disk_usage(self.root).free - 2**30 < RESERVE:
                raise RuntimeError("18 GiB reserve plus write buffer unavailable")
            if self.writer is None or self.path.stat().st_size >= 256 * 2**20:
                if self.writer:
                    self.writer.close()
                self.part += 1
                name = f"native_{self.group}-{self.part:05d}.parquet"
                self.path = self.root / name
                self.writer = pq.ParquetWriter(
                    self.path,
                    self.schema,
                    compression="zstd",
                    compression_level=9,
                    use_dictionary=["series_id"],
                )
                self.auxiliary[name] = (
                    f"All subjects' native {self.group} at {self.rate} Hz, zero-based sample_index; no resampling, interpolation, filtering or end trimming."
                )
            end = min(n, start + 262144)
            table = pa.Table.from_pydict(
                {
                    "series_id": [sid] * (end - start),
                    "sample_index": np.arange(start, end, dtype=np.int64),
                    **{name: array[start:end] for name, array in values.items()},
                },
                schema=self.schema,
            )
            self.writer.write_table(table)
