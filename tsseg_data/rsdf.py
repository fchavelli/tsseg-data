"""Parse pinned RSDF native CSVs and retain ambiguous event references explicitly."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections import defaultdict

import numpy as np
import pandas as pd

CHANNELS = ["blue", "green", "red", "nir", "swir1", "swir2", "sensor", "qa"]
SOURCE_CHANNELS = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2", "Sensor", "QA"]
HEADER = [
    "PID",
    "Lon",
    "Lat",
    "Year",
    "Month",
    "Day",
    "Sensor",
    "Blue",
    "Green",
    "Red",
    "NIR",
    "SWIR1",
    "SWIR2",
    "QA",
]


def annotations(path):
    grouped = defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as stream:
        for i, row in enumerate(csv.DictReader(stream)):
            row["source_row_index"] = i
            grouped[row["PID"]].append(row)
    return grouped


def signal(data, pid):
    frame = pd.read_csv(
        io.BytesIO(data), encoding="utf-8-sig", float_precision="round_trip"
    )
    assert frame.columns.tolist() == HEADER
    assert (frame.PID.astype(str) == pid).all()
    assert frame.Lon.nunique() == frame.Lat.nunique() == 1
    dates = pd.to_datetime(
        frame[["Year", "Month", "Day"]].rename(columns=str.lower)
    ).to_numpy("datetime64[ns]")
    reversals = int(np.count_nonzero(dates[1:] < dates[:-1]))
    order = np.argsort(dates, kind="stable")
    assert set(frame.Sensor) <= {5, 7, 8, 9} and set(frame.QA) <= {0, 1}
    values = frame[SOURCE_CHANNELS].to_numpy(dtype=np.float32)
    return (
        values[order],
        dates[order],
        float(frame.Lon.iloc[0]),
        float(frame.Lat.iloc[0]),
        order.astype(np.int32),
        reversals,
    )


def reference(rows, dates):
    """Conservative evaluable CPs; retain literal contradictory/unmapped rows."""
    events = []
    empty = 0
    mapped = defaultdict(list)
    issues = []
    for row in rows:
        record = dict(row)
        record["series_id"] = row["PID"]
        record["event_date"] = None
        record["normalized_type"] = None
        record["next_observation_date"] = None
        record["preceding_observation_date"] = None
        record["mapped_cp"] = None
        if not row["Year"]:
            assert not row["Doy"] and not row["Type"]
            empty += 1
            record["mapping_status"] = "source_stable_claim"
        else:
            year = int(row["Year"])
            doy = int(row["Doy"])
            date = dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)
            assert date.year == year and doy >= 1
            kind = row["Type"].strip()
            assert kind in {"harvest", "fire", "other", "forestation"}
            target = np.datetime64(date, "ns")
            cp = int(np.searchsorted(dates, target, side="left"))
            record["event_date"] = date
            record["normalized_type"] = kind
            record["mapped_cp"] = cp
            if cp == 0 or cp == len(dates):
                record["mapping_status"] = "outside_interior_observation_window"
                issues.append("event_outside_interior_observation_window")
            else:
                record["mapping_status"] = "first_observation_on_or_after_event_date"
                mapped[cp].append((date, kind))
            record["next_observation_date"] = (
                None
                if cp == len(dates)
                else dates[cp].astype("datetime64[us]").astype(dt.datetime)
            )
            record["preceding_observation_date"] = (
                None
                if cp == 0
                else dates[cp - 1].astype("datetime64[us]").astype(dt.datetime)
            )
        events.append(record)
    if empty and len(rows) > empty:
        issues.append("stable_and_event_claims_same_pid")
    for values in mapped.values():
        if len(set(values)) > 1:
            issues.append("distinct_events_share_one_observation_boundary")
    points = sorted(mapped)
    cps = (
        None
        if issues
        else (np.asarray(points, dtype=np.int32), [mapped[p][0][1] for p in points])
    )
    return cps, events, sorted(set(issues))
