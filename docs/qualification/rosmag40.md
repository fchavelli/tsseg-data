# ROSMAG40: complete published kinematic view

Primary audit and full local build, 2026-10-20. No video corpus downloaded.

## Sources and rights

- [Primary Zenodo v1](https://zenodo.org/records/10719748),
  doi:10.5281/zenodo.10719748: metadata explicitly grants **CC BY 4.0** and
  describes included kinematics, MD and FGD annotation files. Metadata snapshot
  was read from its API; the rights apply to the dataset, not inferred from code.
- [Primary paper](https://doi.org/10.3390/app14093701), especially section2.3.1
  (released structure and labels), section2.5.1 and table8 (34-feature selection).
- [Author repository at 7042e7d](https://github.com/irivas-uma/rosma/tree/7042e7d2dff084ad860bc1f4bb9022fb1bb82662):
  gestureSegmentation/gestureSegmentation.mlx directly pairs the kinematic matrix
  and two label columns by row. Its SHA256 is provenance evidence in the pins;
  the downloaded MATLAB code is not executed or redistributed in the build.

The full ZIP is 3,980,673,198 bytes, provider MD5
`c8deeb9eb5cf631159aad985ace5c86d`. It was **not downloaded in full**, so that
whole-archive digest is provider metadata, not a locally verified SHA256.

## Scope and source discrepancy

The actual central directory has **40 kinematic files, 40 MD files, 40 FGD files
and 40 videos**. They represent five users (X01/02/06/07/08), two tasks, four
trials per user/task (01/02/04/05). All 120 selected files are retained. Their
72,843 rows agree with the paper and Zenodo frame count; the Zenodo description's
22-video count is stale/inconsistent. Lengths are **1,185 / 1,710 / 3,121**
(minimum / median / maximum), not the registry's earlier estimated mean3,311.

Each published signal row has exactly **34 columns**: for each PSM, orientation
XYZW (4), linear/angular velocity XYZ (6), force/torque XYZ (6), followed by
provider-derived inter-tool distance and angle (2). Preserve original header
spelling through an explicit lowercase name mapping. This complete *published
ROSMAG40 view* is already provider-selected/processed; it is not the original
ROSMA154/160-channel, 50-Hz corpus. No new features, centering, scaling, filtering,
quaternion normalization, interpolation or temporal averaging are applied. All
source numeric observations are finite and converted once to float32.

Units are not printed in these selected TXT headers. Physical units and a
provider aggregation formula are not newly asserted from expected dVRK practice.
Master-tool, joint and Cartesian-position data are outside this published view.
Videos, questionnaires, subject attributes and performance scores are excluded.

## Alignment, time and labels

All 40 triplets have identical row counts. The pinned author loader uses these
matrices and labels directly by row; no guessed offset, frame-rate ratio,
resizing, stretching or cross-correlation is needed. The conversion preserves
zero-based **source_row_index**, without claiming it is the original camera's
absolute frame ID. The primary paper reports nominal video capture15 fps and
original ROSMA kinematics50 Hz, but no timestamps or explicit resampling recipe
are provided in these 34-feature text files. Decimal values suggest provider
aggregation; that does not establish its algorithm or bin origin.
**sampling_rate_hz is null**, nominal video cadence is provenance only. Use row
resolution for segmentation and do not claim physical timing or sub-frame onset
precision. This timing uncertainty does not prevent the author-defined row join.

Four label tracks preserve both instruments and semantic levels:

| Track | Source columns / classes |
|---|---|
| label_fgd_psm1 | FGD column1: 1 idle, 2 picking, 3 placing, 4 free motion, 5 load motion, 6 collaboration |
| label_fgd_psm2 | Same classes, column2 |
| label_md_psm1 | MD column1: 1 idle, 2 precision, 3 displacement, 4 collaboration |
| label_md_psm2 | Same classes, column2 |

They are instrument/semantic tracks, **not four annotators**. Annotator identity,
repeated independent ratings and inter-rater agreement are not released. The
conventional default is label_fgd_psm1, not a consensus. Idle1 is annotated rest,
retained as an ordinary scored null state; there is no unknown/missing label.
Every row/tool satisfies F1→G1, F2/F3→G2, F4/F5→G3, F6→G4 exactly (145,686 checks).
No additional joint bilateral taxonomy is fabricated.

| Track | Semantic runs | Recurrence with idle | Recurrence excluding idle |
|---|---:|---:|---:|
| FGD PSM1 | 1,414 | 40/40 | 39/40 |
| FGD PSM2 | 1,437 | 40/40 | 40/40 |
| MD PSM1 | 1,399 | 40/40 | 39/40 |
| MD PSM2 | 1,417 | 40/40 | 40/40 |

All tracks have zero missing-label share; minimum run1 row. Literal class counts
are retained in tsseg.json rather than correcting paper table typographical
inconsistencies. Use subject-disjoint evaluation; tools/levels from one scene
are correlated views, not independent records. Data concern robotic bench
training, not patients or clinical validation.

## Acquisition and storage gate

Free space before source acquisition: **21,955,457,024 bytes (20.448 GiB)**;
RAM available23 GiB, reserve strictly18 GiB. A suffix Range206 read of131,072
bytes exposed the central directory, including all sizes, CRCs and offsets.
All selected compressed members occupy the initial **12,980,548-byte prefix**;
this excludes the video members entirely. Selected native TXT bytes:

| Content | Members | Compressed bytes | Native bytes |
|---|---:|---:|---:|
| Kinematics | 40 | 12,956,804 | 37,096,697 |
| FGD | 40 | 7,673 | 291,372 |
| MD | 40 | 7,691 | 291,372 |

The acquisition budget reserves the prefix plus **twice all native TXT bytes**
and64 MiB overhead:155,448,294 bytes total, already conservative versus measured
7.9-MB complete Parquet output. Including the optional37.7-MB audit text copies
still leaves over20.26 GiB, comfortably above18 GiB. No full archive duplication,
unsafe bulk job, downsampling or reduced trial scope was needed. Build rechecks
the complete output budget and the reserve after each series.

The committed manifest pins the prefix's exact SHA256 and all120 native member
SHA256s, plus size, CRC, offset, method and header names. Acquisition requires an
exact HTTP206 Content-Range; a source ignoring Range is rejected before reading
its body. ZIP decoding is bounded by each pinned native byte count. Paths are
matched to explicit member names, not extracted to the filesystem by the builder.
The initial audit's source copies and prefix are temporary cache only.

## Verification and reproduction

`python -I builders/rosmag40.py` reproduces the complete selected view from pinned
primary ranges; no author MATLAB or downloaded executable is run. Validate via
`scripts/validate.py` with the existing pilot Python containing mlcroissant.
The final build passes **0 errors / 0 warnings**, five checksummed files and one
main shard. `python -I scripts/verify_rosmag40.py` independently decodes selected
ZIP blocks and literal text without reusing the builder parser: all40 trials,
72,843 rows, 34 signal values, four labels, row order and subject IDs compare
exactly after float32 conversion. Native SHA256 and CRC are also rechecked.

Final logs are outside the removable cache: raw/rosmag40-validation.log and
raw/rosmag40-reconstruction.log. Only raw/rosmag40 was deleted after both
successful gates and a final reserve check; no other cache was touched.
Cleanup and free-space measurements are recorded in PROGRESS/HANDOFF.
