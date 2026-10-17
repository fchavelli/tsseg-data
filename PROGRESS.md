# Progress

Resume point of the repository set-up (started 2026-10-18 from the pilot in
`tsseg/notes/datasets/pilot/`). Nothing is pushed or published; no remote.

## Done

- [x] Batch 1 final gate: all **12** local builds (3 pilots + 9 batch-1 datasets)
  pass full `scripts/validate.py` with **0 errors / 0 warnings**, including
  SHA256SUMS, Parquet, chunks, labels/CPs, configuration identity and Croissant
  record excerpts. Log retained locally at `raw/batch1-validation.log`.
  `ruff check .` passes; all nine new builders and the shared reporting module
  pass `ruff format --check`. Repository-wide formatting still flags ten
  pre-existing files: verified against baseline `6d77225` (all ten already fail
  there). No unrelated formatting rewrite applied. Builds total 2.1 GiB, raw
  cache 1.9 GiB; 81 GiB filesystem space remains. No remote/push/publication.

- [x] Batch 1 / USC-HAD: primary archive and existing TSB-SEG SHA256 pin verified;
  no explicit data licence at primary page/readme on 2026-10-18, **source-only**.
  All 840 native recordings represented in 70 explicitly artificial subject/trial
  concatenations, 2,811,490 samples, lengths 25,356 / 39,963 median / 56,251,
  six channels at 100 Hz. No recurrent state in either label representation:
  classified CPD. Default filename labels give 840 segments; separate MAT-declared
  activity track gives 839. **Four source metadata anomalies** retained/documented:
  Subject14/a3t2 internally declares activity 2/walking-left rather than filename
  activity 3; Subject13/a11t4 lacks activity_number (recovered from explicit
  elevator-up string); two trial fields disagree with filenames. No silent
  decision between contradictory source claims. Native recording offsets, names
  and flags in recordings.parquet; age/height/weight/date excluded. Build 43 MiB,
  validation passes 0 errors / 0 warnings.

- [x] Batch 1 / UTSA: all 32 source-only series using the exact CLaP transport
  revision/per-file SHA256 pins from the frozen TSB-SEG downloader. All 34 files
  reused from local cache only after hash verification; no download needed.
  422,320 samples, lengths 2,000 / 12,000.5 median / 40,000, 71 segments,
  recurrence only in SimpleSynthetic (1/32), no unlabelled points. CPs from
  desc.txt, state IDs explicitly attributed to CLaP properties.txt, not claimed
  as original semantic labels. No physical rate asserted. Primary Google Sites
  licence check on 2026-10-18 found no explicit data licence: tier C, no
  redistribution. Manifest and all per-file digests retained. Validation 0/0.

- [x] Batch 1 / MoCap: all 14 primary Barbič trials, 62 DOFs at 120 Hz,
  109,052 frames, lengths 4,579 / 8,370.5 median / 10,617, 124 action segments,
  recurrence in 14/14 after explicit walk/walking alias. Source transition
  triplets and action names preserved in segments.parquet; invalid 05/06 ordering
  and broad overlapping 04 window flagged, never silently repaired. Terminal label
  counts differ by up to eight frames: source endpoints retained, final action
  extended/clipped to actual signal rows; interior CP values unchanged. Both
  archives SHA256-pinned. CMU motion rights and absent annotation licence checked
  2026-10-18: **source-only, effective tier C** for labelled product. Validation 0/0.
  Provenance validator now accepts explicit primary HTTP(S) source URLs without
  inventing DOIs, matching NeurIPS rules; rejects planned collection HF destinations
  as sole provenance (two negative cases verified). Checklist and local HANDOFF §3
  updated. Existing DOI provenance remains supported.

- [x] Batch 1 / PAMAP2: complete UCI archive (CC BY 4.0 verified 2026-10-18),
  SHA256 `76b3580bd5a804121f507717cb498c66a312ef5c774f4a78ac470e6558add352`.
  **14 sessions** (9 Protocol + 5 Optional, correcting the registry's six-subject
  Optional claim), 3,850,505 samples, lengths 8,477 / 316,475.5 median / 447,000;
  240 segments including missing spans, recurrence in 9/14. Source readme II.2
  explicitly excludes activity 0: mapped to -1 in place (**29.2313%** unscored),
  without reconnecting labelled intervals. Default 9 recommended +/-16g axes
  (105 MiB), full all 52 attributes (500 MiB), nominal 100 Hz; sparse ~9 Hz HR
  readings and wireless-loss NaNs preserved, source-invalid orientations flagged.
  Demographic PDF excluded from output. Validation 0 errors / 0 warnings,
  including full/default identity and chunk reassembly. Archive cached locally.

- [x] Batch 1 / HAS: all 250 labelled master CSV series (125 public / 125 private),
  1,929,951 samples, 1,035 segments, recurrence in 83/250, no missing labels,
  lengths 340 / 4,985.5 median / 41,465. Nine inertial columns, six present for
  outdoor recordings (missing gyroscopes padded with NaN), nominal 50 Hz verified
  in primary README. All **100 exact activity names** preserved via a global
  mapping, including ordinary transition/rest/break classes. Latitude, longitude
  and speed are excluded. Master/challenge IDs retained. Safe literal/numeric
  parsing replaces the provider's eval-based loader. CC BY-NC-SA 4.0 verified at
  primary source on 2026-10-18, revision `a77bf78d1ff7e7115e64b2214da809660f99d943`;
  archive SHA256 pinned. Validation passes with 0 errors / 0 warnings.

- [x] Batch 1 / TSSB: 75 series built locally from revision
  `e0c7a1f6cee6874e60cbacd3b8601f2de259606e`, SHA256-pinned archive; 359,497
  samples, 265 segments, lengths 240 / 3,456 median / 20,700, recurrence in
  **10/75** (65/75 without recurrence), no missing labels. Class IDs reconstructed
  from provider properties using subsegment index // (label_cut+1), matching
  every source CP. No physical rate asserted. Croissant/Parquet validation 0/0.
  **Rights hold:** BSD-3-Clause verified for TSSB repository, but UCR/UEA source
  redistribution rights not established by their primary archive pages.
  Conservatively moved to tier C, source-only; rationale in docs/licenses/tssb.md.
  Local build 1.2 MiB; no redistribution or publication.

- [x] Batch 1 / ActRecTut: all four walk/gesture matrices from primary Codeberg
  revision `6d65a5a646f9d12ac45509db9dfe59c01f3183e4`, GPL-3.0-or-later verified in
  settings.m on 2026-10-18; SHA256-pinned archive. 197,227 samples, lengths
  31,392 / 47,528.5 median / 70,778, 1,232 segments, recurrent states in 4/4,
  no missing labels, shortest segment 8. settings.m confirms 32 Hz and **does
  document walk classes**, correcting the earlier audit. Walk has 24 actual
  columns but only 20 names in settings.m: preserve all columns by source index.
  Gesture has 15 columns (documented names in tsseg.json), with nine NaN padding
  columns in the shared schema; n_source_channels distinguishes the counts.
  Subset positions are not physically aligned sensors. Class IDs are scoped to
  subset (walk 1..6, gesture 101..112); NULL remains ordinary state in both.
  Validation passes with 0 errors / 0 warnings.

- [x] Batch 1 / SKAB: 34 labelled v0.9 experiments, 37,401 samples, eight channels
  nominally at 1 Hz (timestamps and maximum gap retained), 100 binary-label
  segments, recurrence in 32/34 series, no unlabelled points. The CP track retains
  **all 129 source markers**: 29 series have four markers, three have three, two
  have two; no phase semantics or absent markers are invented. The separate
  anomaly-free training CSV has no labels and is excluded. GPL-3.0 verified in
  source LICENSE on 2026-10-18; revision `b2c0d46c2971dcbfe71e26087b6d231998bb91c2`
  and archive SHA256 pinned. Build 768 KiB; validation passes with 0 errors /
  0 warnings, including every source CP and Croissant record excerpts.

- [x] Batch 1 / PUMP: source revision `2e1765e35f37a214b371ebba18b5e66d104fca9f`,
  CC BY 4.0 verified at the primary Bosch README on 2026-10-18 (URL recorded in
  the card and Croissant). All 400 cycles: 12,937,489 samples, 9 channels at 100 Hz,
  lengths 20,365 / 33,225 median / 43,870; 22,686 segments, recurrent states in
  400/400 series, no unlabelled samples, shortest segment 1 sample. Source PC
  states include **17.5**, so codes are categorically encoded with a reversible
  `state_source_codes` mapping; never truncated. Generation B model predictions
  are excluded from ground truth. Original time stamps and source normalisation
  retained; no smoothing. The 120 TSB-SEG DC cycles are flagged in the index.
  SHA256-pinned archive (879 MiB), Parquet 266 MiB. Validation: full Parquet,
  SHA256SUMS, Croissant 1.1 + RAI, and one-row record excerpt pass with 0 errors /
  0 warnings. Source archive retained in `raw/pump/` for reproducibility.

- [x] 1. Skeleton: `pyproject.toml`, MIT `LICENSE`, `.gitignore` (`build/`, `raw/`,
  `.venv/`), `tsseg_data/` (sources, format writer, Croissant, labels, reader,
  build steps), `cards/` templates, `registry/` (shortlist + 50 retained entries,
  `scripts/sync_registry.py`).

- [x] 2. Builders ported to format 1.0 (now 1.1) (`builders/<id>.py`) and built in `build/`
  from the pilot raw cache (`--raw-dir .../pilot/raw`, sha256 checked):
  mozilla-perf-cpd-annotations (0.75 MB), opportunity (default 17 MB, full 193 MB),
  dreem-dod-h, 3 nights (default 231 MB at 250 Hz then, full 4 files, 930 MB). Pilot fixes: Dreem
  aligned by `record_id` (window rule reproduces every h5 length exactly, no
  agreement search); Opportunity's 24 repeated `accX` renamed X/Y/Z by position.

- [x] 3. `scripts/validate.py`: files + SHA256SUMS, Croissant (mlcroissant 1.1.1 of
  `pilot/.venv`, required RAI, DOI in `prov:wasDerivedFrom`, three
  `prov:wasGeneratedBy` activities, record-set fields = Parquet columns, records
  read from a 1-row excerpt), Parquet schema, chunks, labels, change points,
  identity across configs. The three datasets pass (10 s, 1 GB RAM); a corrupted
  index is caught. Fixed on the way: an empty `tsseg:nullStates` object made
  mlcroissant recurse forever (empties are now omitted).

- [x] 4. README (collection, format, one line per dataset with license tier and
  status, generated by `scripts/collection_table.py`), CONTRIBUTING,
  `registry/README.md`.

- [x] 5. `docs/NEURIPS_CHECKLIST.md`: every requirement of the 2026 hosting
  guidelines with status and location, tier C datasets needing an author contact,
  collection website. `ruff check .` passes.

- [x] 6. Decisions 1-6 applied (2026-10-18, see "Decisions"). Format 1.1: a
  sampling rate per config (`DatasetSpec.config_rates`; `tsseg.json`
  `configs.<cfg>.sampling_rate_hz`; `index.parquet` `length_<cfg>`,
  `n_chunks_<cfg>` when the rates differ; Croissant `tsseg:configSamplingRateHz`,
  per-config field descriptions; card "Rate" column). Dreem `default` resampled
  to 100 Hz (`resample_poly(x, 2, 5)` in float64, cast to float32, documented in
  the `preprocessing` activity and `rai:dataPreprocessingProtocol`). Croissant
  1.1 (`isArray` / `arrayShape` instead of the deprecated `repeated`, 1.1 context
  keys of mlcroissant 1.1.1). `validate.py`: identity across configs by
  per-epoch labels and durations when the rates differ (raw values only between
  configs at the same rate); a shifted label is caught. The 3 datasets rebuilt
  from the pilot raw cache and valid (0 error, 0 warning, 7 s, 1.2 GB RAM).

## Sizes (build/ vs pilot/out)

| Dataset | build/ | pilot/out |
|---|---|---|
| mozilla-perf-cpd-annotations | 0.8 MB (1 part) | 3.8 MB (174 files) |
| opportunity | 16 MiB default + 184 MiB full | 235 MB |
| dreem-dod-h (3 nights) | 89 MiB default (100 Hz) + 888 MiB full (4 parts) | 1.3 GB |

Gains come from zstd level 9 + byte-stream-split encoding of the float columns.

## To do

- [ ] Decision 7 (below) remains for user review; 38 builders remain after the
  three pilots and nine completed batch-1 source builders. Next: batch 2 and
  tier C author contacts; TSSB upstream rights now also require clarification.
- [ ] Dreem: the 22 other nights (`--all-records`, ~20 GB download, ~7 GB of
  Parquet `full`); the record_id of `63b799f6...` (lights off at 60) is unknown
  until its h5 is read.
- [ ] Verify against the papers: Mozilla author list (arXiv:2606.18377);
  Dreem DOD-H acquisition site and scorer details (Guillot et al. 2020), BibTeX
  volume / pages of Chavarriaga 2013 and Guillot 2020.
- [ ] Before publication: create the HF repos and the GitHub remote (user decision),
  make `contentUrl` absolute, run the online Croissant checker.
- [ ] Collection website (GitHub Pages) generated from the cards.

## Decisions

Decided by the user on 2026-10-18:

1. Opportunity: the 24 repeated `accX` object-sensor columns renamed
   `accx`/`accy`/`accz` by position (documented, source columns recorded).
2. Opportunity split = challenge split of Chavarriaga et al. 2013 (test = ADL4-5
   of S2, S3, S4), not the S2-S3-only variant common in deep learning papers.
3. Configs: Opportunity default = 15 IMU accelerometers (unchanged); Dreem
   default = C3-M2, F3-F4, EOG1, EMG **resampled to 100 Hz** (usual sleep staging
   rate, as Sleep-EDFx; anti-aliasing + `scipy.signal.resample_poly(x, 2, 5)` in
   float64, then float32; a 30-s epoch = 3 000 samples), `full` = 16 channels at
   250 Hz (no feature view). Required a sampling rate per config (format 1.1).
4. Dreem: consensus computed on the evaluation window only (outside: -1 in
   `epochs.parquet`); `label_h5` kept beside the 5 scorers and the consensus.
5. Mozilla: all change types stored with their type; default evaluation types =
   mean, mean_variance (as the authors).
6. Croissant `conformsTo` **1.1** (`http://mlcommons.org/croissant/1.1`) + RAI
   1.0; HF `task_categories: other` + tags.

To validate:

7. mlcroissant record reading is done on a one-row excerpt (full files are
   checked by `validate.py` itself).
