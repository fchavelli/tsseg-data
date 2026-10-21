# DEDDIAG native sparse electricity qualification (2026-10-21)

Status: complete primary metadata audit, two complete pilots and independent
exact pilot parity; all fifteen source archives acquired with MD5/SHA verified; full build
in progress. Pilot house08
passes Croissant/schema/source checks with **0 errors / 0 warnings**. A complete
corpus build is not yet claimed. Nothing is published or rehosted.

## Primary source and rights

- Fixed record: <https://api.figshare.com/v2/articles/13615073/versions/1>
- Fixed dataset DOI: <https://doi.org/10.6084/m9.figshare.13615073.v1>
- Primary paper: <https://doi.org/10.1038/s41597-021-00963-2>
- Author reader: <https://github.com/DEDDIAG/deddiag-loader>, pinned commit
  `d7b551bfa9692624e28238fbde5bd54806f0bda0`.

The primary record and distributed LICENSE both specify **CC BY 4.0**,
verified 2026-10-21. Attribution remains required. All fifteen native house ZIPs
total **15,301,162,142 bytes**. Provider sizes/MD5, selected metadata SHA256,
ZIP central-directory inventories and source-document digests are pinned in
`builders/checksums/deddiag.json`; complete archive SHA256 pins are fixed for all15 files. SQL and shell files are inspected only as text.
No downloaded code or database import is executed.

## Complete native selected scope

All **54 released measurement traces** are included: 50 appliances and four
mains traces (three phases plus total) in house08. Each trace is a separate
univariate `power_w` series, preserving float64 values and UTC source
microsecond timestamps as exact int64 nanoseconds. Anonymous house/item IDs,
categories and original non-demographic item descriptions remain available.
The household demographic/absence-schedule tables are excluded.

The sensor query rate is nominally about 1 Hz, but the released files store
value changes and an hourly heartbeat. Therefore `sampling_rate_hz` is null;
these are irregular observations, not a complete 1-Hz sample grid. No
resampling, interpolation, forward filling, dense expansion or clipping is
performed. In particular the author's optional SQL expansion and `value<4000`
filter are not applied. High-power measurements remain in the largest pilot.

Native TSV exports have timestamp reversals. Sort each trace chronologically
with a stable sort, preserving duplicate observations and ties in source order.
Every observation retains its exact source-row index through consecutive runs
in `source-order.parquet`:
`source_index = source_start + sorted_index - sorted_start`.
Runs cover both orders exactly, enabling independent inversion to the complete
original TSV order. Source metadata tables retain literal `source_row_index`.
Observed gaps longer than 3605 seconds are reported separately, following the
author reader's monitoring-gap convention. No intermediate samples are added.

## Positive annotations, overlaps and clocks

Preserve all **1,738 original event rows**, their original IDs, source label
IDs, literal fields, closed start/stop endpoints and original row positions.
All rows have valid endpoints and defined labels. There are 37 source label
definitions across 15 items, but actual events on only 14 items. Item35 has a
label definition and no event; it stays entirely unscored. Definitions alone
do not establish reviewed absence. Technical/error/unknown labels and original
spellings remain distinct, without inferred corrections.

The default `label_activity` is a reversible code for the complete set of
simultaneously active source labels. The global source vocabulary produces
39 nonempty sets, including overlapping programs; it never picks an exclusive
winner. All observations outside positive source intervals, all data-only
traces and ambiguous annotation-rounding boundary points are **-1**. No idle,
off or standby negative reference is invented. There is no supplied global
annotator identity, inter-rater agreement, consensus or train/test partition.
Split by household to avoid leakage between correlated device/mains traces.

The author annotation UI uses nearest-whole-second timestamps and closed
endpoints, while measurements have native subsecond clocks. Preserve native
timestamps unchanged and apply the UI convention only for reference
association. PostgreSQL documents platform-dependent tie handling for
`round(double precision)`:
<https://www.postgresql.org/docs/current/functions-math.html>.
An exact half-second boundary with different adjacent active source sets is
left unscored. Every source interval remains in the auxiliary table, even if
no native observation falls within it; no artificial frame or exact physical
change point is created. Sparse observation counts are not elapsed seconds.

## Measured pilots and complete storage gate

| Pilot | Source ZIP bytes | Native observations | Complete output + auxiliary bytes |
|---|---:|---:|---:|
| House01 | 77,164,768 | 5,892,665 | 53,675,356 |
| House08, largest house ZIP | 2,141,569,918 | 194,656,014 | 1,859,526,566 |

The largest house has nine traces, a maximum 34,314,544 observations in a trace,
and 7,344 compact source-order runs. Its measured output/source ratio is
0.8683006566, greater than house01's 0.6955940825. Use the larger ratio across
**all fifteen source ZIPs**, multiply by 1.25, then add 64 MiB:
**16,674,620,283 bytes** for complete output including all auxiliary tables.
Add **4 GiB** bounded scratch and the strict **18 GiB free reserve**. Cached
pilot outputs remain charged in current free space. Before complete
acquisition, remaining ZIP bytes were 13,082,427,456; measured free space
84,980,035,584 bytes leaves a projected 50,928,020,549 bytes after those costs,
well above the 19,327,352,832-byte reserve. No second heavy job runs alongside.

Acquisition uses capped 32-MiB HTTP ranges with exact final 206 status,
Content-Range and body-size checks, stable ETag/If-Range, bounded retries and
per-MiB reserve guards. Provider MD5 and full SHA256 are verified before atomic
promotion; per-file SHA checkpoints support safe restart. At most four bounded
streams run within the single acquisition job. Full source remains compressed;
gzip/TSV measurements are parsed into reusable on-disk vectors per trace.
Data and scratch stay under `raw/deddiag`, never `/tmp`.

Independent reconstruction imports no DEDDIAG reader, sorting, labeling or
writer helper. It reads original gzip/TSV with Arrow CSV instead of the
builder's pandas parser, inverts every source-order run and compares every
UTC timestamp/power value exactly, including duplicates/NaNs. It independently
reconstructs overlapping reference sets from the original interval rows,
checks source MD5/SHA, all annotation/label/item literal fields and source row
positions, native interval associations and observed monitoring gaps.
Both pilots pass: **3/3 and 9/9 traces, no mismatches**. The largest pilot also
passes the standard full validator: 17 checksummed files, nine series, eight
Parquet parts, Croissant excerpt loaded, **0 errors / 0 warnings**.

Evidence retained outside the eventual raw cleanup directory:
`raw/deddiag-{small,largest}-pilot-{build,reconstruction}.log`,
`raw/deddiag-largest-pilot-validation.log`,
`raw/deddiag-full-acquisition.log`. Complete final parity and validator 0/0
remain required before deleting only `raw/deddiag`. All other caches, pilot
outputs and logs remain untouched.
