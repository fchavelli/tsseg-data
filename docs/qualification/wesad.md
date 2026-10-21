# WESAD native synchronized physiology qualification (2026-10-21)

Status: complete 15-subject local build and independent exact source parity;
final validator passes 0 errors / 0 warnings. Tier C, **source-only**;
no rehosting or publication. The user accepted this local source-only track.

## Primary source, rights and fixed archive

- Author page: <https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html>
- Linked provider share: <https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx>
- Public download: <https://uni-siegen.sciebo.de/public.php/dav/files/HGdUkoNlW1Ub0Gx>
- Source publication: <https://doi.org/10.1145/3242969.3242985>

The author page permits scientific, non-commercial use with attribution. It
supplies neither a named open licence nor an explicit redistribution grant.
The conversion code is MIT; the source and derived tables remain local and
must not be rehosted. Card/Croissant and registry preserve this restriction.
The UCI copy and its repository DOI do not replace the primary Siegen terms.
Rights verified at the primary page on 2026-10-21.

Primary HTTP metadata provides a 2,249,444,501-byte ZIP, last modified
2021-01-26, ETag `ac228d1dc0f066b9634f5f0026b6bf8b`, MD5
`e328980e7992502de30c96ba2a7cb3e2` and SHA1
`bae786bf599ef28e42e1c2e18da9b84d685e84e7`.
Both provider checksums agree after acquisition. Complete local SHA256:
`5e15d2606adf16d819ba535c1786d92e94bae5ff5392f7ae01fb63f9938fd71c`.
The manifest pins the entire archive, README PDF SHA and all 15 selected pickle
members' sizes/CRC. Its source inventory has 92 entries, 17,578,304,666 bytes
expanded. No global archive extraction is performed.

## Complete selected view and native clocks

The primary archive README explains that 17 participants were recorded, but
S1 and S12 were discarded after sensor malfunction. All released subjects
S2–S17 except S12 are included. The selected view is every provider-synchronized
`SX.pkl`; source unsynchronized RespiBAN TXT/E4 ZIP files are alternative
recordings, not an additional independently aligned reference. Self-report
questionnaires and demographic files are excluded from the derived view.

| Native stream | Signals | Rate | Representation |
|---|---|---:|---|
| Chest | ACC x/y/z, ECG, EDA, EMG, respiration, temperature | 700 Hz | Default eight-channel series |
| Wrist ACC | x/y/z | 32 Hz | Separate native auxiliary table |
| Wrist BVP | BVP | 64 Hz | Separate native auxiliary table |
| Wrist EDA/TEMP | EDA, temperature | 4 Hz | Separate native auxiliary table |
| Protocol | Original numeric code | 700 Hz | Separate original-code table |

Thus all **14 genuine signal channels** remain. The provider used a double-tap
pattern to synchronize the devices. No new resampling, interpolation, filtering,
calibration, drift correction, gap repair or common-duration truncation is
introduced. Preserve the released numeric arrays exactly; float64 storage
losslessly promotes the source float32 chest temperature while preserving the
other source float64 values. Original dtypes are reported.

All clocks use exact zero-based integer sample indices: physical time is
`sample_index / native_rate` seconds. The chest/labels share 700 Hz and a native
origin. Wrist tables keep their own indices and rates, with no invented common
grid or projected wrist labels. Actual per-stream end lengths remain explicit.
No absolute source timestamps are exposed.

## Protocol labels and quality

README section II.3 defines:

- 0: not defined / transient;
- 1: baseline;
- 2: stress;
- 3: amusement;
- 4: meditation;
- 5, 6, 7: ignore in this dataset.

The original 700-Hz code is preserved for every sample. The default evaluation
track maps **0 and 5–7 to -1**, preserving 1–4 literally. Undefined/transient 0
is never turned into rest or a negative state. Native code counts and masked
shares are reported per subject. Protocol timing is experimental schedule
reference, not a clinical diagnosis, independent expert affect annotation or
sample-exact onset of a physiological response. The separate self-report
questionnaires are not substituted as segmentation labels.

All subject README files were audited. S2 and S17 explicitly report that the
RespiBAN temperature sensor was not fully attached throughout the recording.
Those sensor-quality notes are retained in metadata; no value is deleted,
repaired or silently masked on that basis. Personal, questionnaire and unrelated
free-text participant notes are excluded. Preserve any nonfinite signal values
and report their counts. Split by participant; there is no invented source
train/test assignment, global annotator identity or consensus.

## Acquisition, pilot and resource gate

The ZIP central directory and README were first inspected with bounded ranges;
README decompression was checked against its exact ZIP size and CRC. Complete
acquisition then used 32-MiB capped ranges with exact final HTTP206 status,
Content-Range/body size, stable ETag and If-Range. At most five bounded retries;
only validated bytes are appended. A partial HTTP-identity checkpoint supports
safe restart. Full provider MD5/SHA1 and local SHA256 are checked before promotion.
Reserve guards run before each range and each MiB written. Source files stay
under `raw/wesad`; no data is placed in /tmp or extracted into adjacent repos.

The S15 pilot contains 3,676,400 chest/protocol samples; wrist counts are
168,064 ACC, 336,128 BVP and 21,008 EDA/TEMP samples. Every native stream spans
exactly 5,252 seconds for this pilot. Output is 63,736,876 bytes. Conservative
projection `15 * pilot * 1.5 + 64 MiB` is **1,501,188,574 bytes**. The pre-download
and build gate reserved the entire 2.249-GB source plus 12 GiB for output and
working allowance, beyond the strict 18-GiB free reserve. One heavy job at a time.

The pilot contains all eight native codes; 1,557,501 samples (42.36484%) are
unscored after the explicit 0/5–7 mask. Its original codes remain unchanged.
An independent decoder/mapping comparison checks every pilot chest/wrist value,
native index, original code and evaluation label exactly. It passes with no
mismatches. No WESAD mapping, mask or writer helper is imported by that verifier.

Evidence: `raw/wesad-acquisition.log`, `raw/wesad-pilot-build.log`,
`raw/wesad-pilot-reconstruction.log`. Source pins:
`builders/checksums/wesad.json`. The full build and both final gates must pass
before deleting only `raw/wesad`; all other caches and pilots remain untouched.


## Complete source parity and final gates

All 15 subjects contain **60,807,600 native chest/protocol samples (24.13 h)**.
Length min/median/max is 3,656,100 / 3,883,600 / 4,949,700 samples. Wrist totals:
2,779,776 ACC, 5,559,552 BVP and 347,472 EDA/TEMP samples. Every released subject
has equal physical duration across the four native groups, without any
conversion-induced trimming or resampling. No nonfinite signal value occurs.
All eight chest plus six wrist channels are compared exactly at native rates.

| Source code | Samples | Evaluation |
|---|---:|---|
| 0 | 27,654,897 | -1, undefined/transient |
| 1 | 12,327,702 | baseline |
| 2 | 6,976,201 | stress |
| 3 | 3,902,501 | amusement |
| 4 | 8,264,199 | meditation |
| 5 | 552,300 | -1, source ignore |
| 6 | 552,998 | -1, source ignore |
| 7 | 576,802 | -1, source ignore |

Thus **29,336,997 samples (48.2456091%) are unscored**. Original codes are
preserved for every one of the 60,807,600 samples. Direct source reconstruction
finds exactly one baseline, stress and amusement episode and two meditation
episodes in each of the 15 subjects. Valid-state recurrence is therefore genuine
meditation recurrence, not an artefact of including undefined0 as a scored state.

Independent reconstruction uses a separately loaded restricted numeric decoder
and its own literal channel mapping and explicit per-code evaluation masking;
no WESAD builder mapping/mask/writer helper is imported. It compares all subjects,
all 14 signal channels, every source code/evaluation label and sample index,
source SHA/MD5/SHA1, native lengths, per-code counts and sensor-quality notes.
Every numeric value and label matches exactly; no mismatches or tolerance-based
signal equality is needed. Evidence: `raw/wesad-full-reconstruction.log`.

Full Croissant/schema/chunk/label/SHA validation passes **0 errors / 0 warnings**,
12 checked files, 15 series, 4 default Parquet parts and 4 native auxiliary tables.
The first metadata pass exposed a nested empty `nullStates` list producing an
empty RDF node and infinite recursion in mlcroissant. No null class remains
scored, so the correct representation is an empty top-level mapping, omitted
from Croissant by the existing generator. Fixing this metadata changed no signal,
source code or evaluation label. Card limitations also explicitly retain the
S2/S17 sensor-attachment caveat. Final metadata is validated again after edits.

Complete output: **1,052,303,494 bytes**, below the pilot projection of
1,501,188,574 bytes. The entire source remained compressed, and only one heavy
job ran at a time with free space well above the 18-GiB reserve. Final logs:
`raw/wesad-full-build.log`, `raw/wesad-full-validation.log`,
`raw/wesad-full-reconstruction.log`; the source pins and dataset card retain
source-only/no-rehosting status. No upload, publication or remote commit occurs.


After both final gates, only `raw/wesad` was deleted: 7 files,
2,249,841,394 bytes. Free space before/after was
67,786,424,320 / 70,036,291,584 bytes. All other
source caches, pilot outputs, validator excerpts and logs remain. Cleanup proof:
`raw/wesad-cleanup.json`. The SHA-pinned source-only builder can reacquire the
complete primary archive; no source or derived data was rehosted.
