# RSDF China forest: native trajectory qualification (2026-10-20)

Status: complete native conversion and exact independent reconstruction; validator0 errors/0 warnings. Final
measurements and cleanup are recorded below.
No remote or publication action is authorized or performed.

## Primary source and rights

Fixed dataset version1: <https://doi.org/10.6084/m9.figshare.33313359.v1>.
Primary manifest: <https://api.figshare.com/v2/articles/33313359/versions/1>.
It reports CC BY4.0, verified2026-10-20. Dataset authors: Rong Shang,
Shengwei Xu, Ziyi Yang and Jing M. Chen. The repository article version1 is
not the same numbering system as the scientific dataset's historical v3 label.

Primary preprint: <https://doi.org/10.5194/essd-2026-705>, under review as of
2026-10-20. It documents consensus visual interpretation, native calendar-day
Year/DOY event references, null triples as stable forest, validity QA0/1, and
provider preprocessing of Landsat Collection2 Level2 data. No individual rater
tracks or reproduced inter-rater agreement are claimed by this conversion.

Selected complete time-series view:

| File | Bytes | Provider MD5 |
|---|---:|---|
| RSDF_SurfaceReflectance.zip | 340,399,479 | 19d4421ba925824a2efbc4ed2b3ae328 |
| RSDF.csv | 677,547 | b1eb380e091bbaad051bfa74a79b77d3 |

Both files match provider MD5 and size, and are SHA256-pinned in
`builders/checksums/rsdf-china-forest.json`. The1,170,609,789-byte diagnostic PDF
archive is outside this time-series view and was never downloaded. Source ZIP
members are read with CRC validation in place, without extraction or execution.

## Native observations and reversible chronology

The ZIP contains exactly12,991 sample CSVs (1,746,880,440 native CSV bytes),
matching all annotation PIDs. The actual14-column schema includes PID, Lon, Lat,
Year, Month, Day, Sensor, six reflectance bands and QA. Preserve all six bands
**and** Sensor/QA (eight observation columns), date and both coordinate sources.
Coordinate columns are constant within each trajectory; PID is checked in every
native row against filename and annotation join. No pixel/sample is dropped.

Native QA0 observations remain; invalid reflectance codes are not silently
promoted to valid measurements. No additional cloud mask, interpolation,
resampling, filtering, reflectance scaling or spectral-index computation occurs.
The published reflectance integer scale/offset is not established by the CSV
header, so no calibration is guessed. Published adaptive filtering is provider
processing, not a new operation or a raw-scene reconstruction claim.

The source has genuine non-monotone date sequences (first detected PID405110011).
Stable-sort by original calendar date for the chronological time-series view,
retaining relative source order among duplicate dates. `source-order.parquet`
contains a `source_row_index` list for **every** sample: chronological position
maps back to its zero-based original CSV row. The independent check applies its
inverse and compares every original value/date in native order. Only derived
CP indices are projected into this sorted order; original event dates and native
CSV values are unchanged. Per-PID native reversal and duplicate-date counts are
retained. Sampling is irregular; no global or fabricated physical rate is used.

## Original reference claims and evaluability

All13,765 annotation rows are retained, with original row indices, PID,
coordinates, Year, Doy, Type, Confidence strings and mapping metadata.
There are10,343 PIDs with only stable claims and2,648 with explicit events;
46 of the latter also contain a blank stable claim. The conflict is preserved.
An empty reference means only stable claims, while **null** means the default
reference is unscored due to an explicit ambiguity. Do not turn a conflicting
stable claim into a false negative/no-change reference.

For a well-formed event, reconstruct its calendar date from Year/DOY and map it
to the first chronologically ordered acquisition on or after that date. Keep the
original event date, mapped index, previous/next acquisition dates and raw type
in `source-annotations.parquet`; normalize only trailing type whitespace for
CP type identifiers (four literal `other ` entries remain raw in the auxiliary).
The CP list deduplicates identical date/type records only. Mark the entire
default reference null for stable/event contradictions, events mapping outside
0 < CP < n, or distinct date/type events sharing a single observation boundary.
These rows and proposed mappings remain visible in the auxiliary table.

No exclusive forest-state taxonomy, latent state recurrence or invented rater
identity is derived. Event timing is calendar-day interpretation with irregular
acquisition gaps, not sample-exact onset. Evaluate elapsed-day timing/tolerance,
and separately inspect QA0/1 sensitivity and ambiguous reference coverage.
Confidence strings are consensus support as published, not new probabilities.

## Pilot and storage

A conservative pre-download gate reserved complete340.4MB source +10GiB output
+18GiB reserve, with89.16GB free after unrelated user storage was removed.
No unrelated user file was modified by this project. Seven pilot samples include
smallest/largest native CSVs, all four event types and a stable/event conflict.
The pilot has10,158 observations,873,340 native CSV bytes and235,857 output bytes.
Extrapolating by complete native CSV bytes with25% margin and64MiB buffer gives
656,819,029 bytes, far below the conservative budget. Final conversion and checks
run sequentially, with df/free checks and an18-GiB guard after every sample.

Final measurements, validation, exact reconstruction and targeted cache cleanup
will be recorded after the gates finish.


## Complete conversion measurements

All12,991 PIDs contain19,637,038 native observations, lengths639 /1268 median /
3798. Complete output232,025,704 bytes, below the656,819,029-byte pilot projection.
There are1,025 PIDs with7,006 native date reversals. Every chronological trajectory
and reversible source permutation is retained. There are2,307,256 duplicate dates;
these are separate observations, not collapsed acquisitions.

Native QA0 occurs in12,031,665 observations (61.270264%); QA1 in7,605,373.
The quantity of invalid observations is a substantial limitation: do not treat the
complete CSV view as uniformly clean reflectance. All183 native missing numeric values remain NaN, without imputation. Default reference is evaluable for12,944 PIDs:
10,343 stable-only controls and2,601 points with3,322 CPs. Forty-seven are explicitly
unscored:46 stable/event conflicts and PID427210048 with distinct events mapped to
one observation boundary. No event lies outside the interior observation window.

Independent complete reconstruction passed12,991/12,991 PIDs and19,637,038
observations: all six bands, Sensor/QA, original dates, stable sort and exact
inverse to source order, all coordinates/PIDs, member SHA/CRC, all13,765 source
annotation rows, raw confidence/type/date and conservative CP lists/types match.
All183 native missing numeric values remain NaN. Log:
`raw/rsdf-reconstruction.log`, outside the removable dataset cache.

Final validator:0 errors /0 warnings, including Croissant1.1 metadata and record
excerpts, all7 checksummed files,12,991 series and one main part. Log:
`raw/rsdf-validation.log`. Both final logs remain outside the source cache.

Only after both successful gates, `raw/rsdf-china-forest/` alone was removed:
357,066,734 file bytes (including source CSV/ZIP and audit-only paper). Free space
before/after:88,504,078,336 /88,861,163,520 bytes, above18GiB throughout this build.
All other caches, AMI qualification files and pilot output remain. No publication
or adjacent repository edits. Source build code, SHA pins, audit and independent
reconstruction are committed locally as one dataset integration.
