# Progress

Resume point of the repository set-up (started 2026-10-18 from the pilot in
`tsseg/notes/datasets/pilot/`). Nothing is pushed or published; no remote.

## Done

- [x] Batch 3 / Dog behavior (Vehkaoja): complete primary Mendeley v4 CSV,
  all 62 tests / 45 dogs, 10,611,068 samples at 100 Hz; all 12 native back/neck
  accelerometer/gyroscope channels. Lengths 146,584 / 170,040 median / 217,656.
  CC BY 4.0 verified at primary source; ZIP and description official SHA256/size
  pinned. CSV declared equivalent to MAT by primary paper: download only the
  440,933,845-byte ZIP plus 4,163-byte description; stream the 1,985,551,732-byte
  CSV without extraction. TXT says 63 MAT rows, but complete CSV has 62 tests
  (45 dogs + 17 repeats, matching paper); discrepancy retained, no synthetic test.
  **All 62 sensor arrays exactly duplicate BEBE vehkaoja_dogs after float32**,
  proven by complete per-series channel fingerprints against pinned BEBE source.
  Original annotations add distinct value: seven instructed tasks, 19 atomic
  behavior names, all simultaneous behaviors and Bark events; preserve explicit
  overlap IDs/group, never count independent sensor evaluations across the views.
  Two dense tracks: literal instructed task and reversible unordered behavior set
  (59 categories). Original task/three ordered behavior slots/PointEvent retained
  losslessly as 24,660 half-open spans, including undefined entries. Empty behavior
  sets/undefined tasks -> -1; unused slots do not discard other observed labels.
  Synchronization/Extra_Synchronization stay ordinary annotated technical states;
  substantive recurrence excludes these. Video resolution about 1 s, no invented
  100-Hz annotation precision. Behavior recurrence 62/62 (also substantive), task
  recurrence 14/62; 23,602 / 962 segments, unscored 34.392259% / 24.434402%.
  Two/three populated slots: 2,486,375 / 152,140 samples; three-slot duration
  1,521.4 s differs from paper 15,214 s. Bark 231 contiguous source spans,
  26,173 source samples; preserve source duration, no event expansion.
  CSV header/paper ANeck X/Y descriptions conflict with TXT row descriptions:
  keep explicit header positions, no inferred swap or unit conversion.
  No filtering, resampling, scaling, cropping or behavior rejection. Bounded
  24,778-row prefix pilot measured 35.16 compressed bytes/sample; builder uses
  55-byte floor +25% +64 MiB metadata, rolling guard after every test; minimum
  projection 20.54 GiB free. Output about 348 MB, two shared parts. Full validation
  **0 errors / 0 warnings**, eight checksummed files. All 62 exported sensor hashes
  match source/BEBE; exact time grids and full original-span coverage verified;
  both dense tracks reconstruct exactly from original spans on every test.
  Raw cache deleted after successful validation, pilot raw untouched; 21.37 GiB free.
  No publication. Next: DEDDIAG; Capture-24 remains deferred.

- [x] Batch 3 / BEBE: **seven licensed animal datasets**, all 369 formatted
  source clips / 105 individuals; explicitly exclude noncommercial HAR (HAPT
  duplicate) and rights-unclear turtles. This is a scoped provider-formatted
  track, not the complete nine-dataset collection or original raw reconstruction.
  Seven primary ZIPs (1,623,226,915 bytes) verified against Zenodo MD5/size and
  SHA256-pinned. Per-archive CC BY 4.0 grants and original animal-source notices
  audited; original bear source USGS public domain, crow raw grant also CC BY.
  Deposit-level terms never override the two excluded source restrictions.
  Dogs overlap dog-behaviour-vehkaoja; never independent evaluation datasets.
  All 3–12 released sensor columns per cohort retained (18-name union, structural
  absence NaN, native_channels explicit), one float32 cast, no new processing.
  Provider interpolation/normalization, selected gull rotations, whale tail
  cropping, preprocessed rattlesnake channels, source splitting/taxonomy grouping
  are documented by cohort. ZIP members streamed directly; no CSV extraction.
  Exact elapsed nanoseconds at released 1/5/16/25/50/100 Hz; global/config rate
  null, per-series frequency/step explicit, source clips kept whole in shared
  shards under this mixed-rate format. 100,902,705 samples; lengths
  151 / 10,606 median / 1,728,000. Five animal-grouped source folds preserved.
  Primary evaluation explicitly excludes local unknown=0: map to -1, including
  missing observations and provider-collapsed rare/mixed behaviors; no infilling.
  36 scored classes namespaced by cohort with reversible source-code maps;
  71,838 segments, recurrence 209/369, unscored 71.433829%. Missing gaps can
  separate repeated observations without proving an intervening state change.
  Per-cohort recurrence: rattlesnakes 2/146, crows 20/20, whales 8/8,
  bears 34/39, gulls 12/22, seals 71/72, dogs 62/62. Per-series stats retained.
  Bounded no-duplicate prefix pilot: 1.512 GiB cache + output estimate with 25%
  margin 1.049 GiB +64 MiB metadata, projected 20.12 GiB free. Rolling actual
  compression/source-byte projections after every clip; minimum projection
  20.02 GiB at recorded cohort ends, above the 18-GiB reserve. Final output 1,133,761,082 bytes,
  five shared Parquet parts, exact primary licences/metadata retained.
  Full validation **0 errors / 0 warnings**, 23 checksummed files. All 369 exact
  time grids verified; all channels/labels and structural NaNs equal pinned
  source on one complete clip per cohort. Raw cache deleted only after successful
  validation; pilot raw untouched, 21.70 GiB free. No publication. Next: dog-behaviour-vehkaoja;
  Capture-24 remains blocked by disk/primary access (see pending entry below).

- [x] Batch 3 / EEGMMIDB: all 109 participants and all 1,526 source runs,
  including 218 provider-designated baselines and 1,308 motor/imagery task runs.
  All 64 native EEG channels in one `default` config, calibrated float32 uV;
  **disk-driven exception to light/default + full**: a second reduced view would
  duplicate physical samples and breach the conservative 18-GiB reserve projection.
  No channels, runs or participants rejected. Native rates: 1,490 runs at 160 Hz;
  task runs R03-R14 of S088/S092/S100 (36 runs) at 128 Hz. Their baselines remain
  160 Hz. Global/config rate is null; exact `time_ns` grids and per-series native
  frequency/step preserve timing without resampling. 27,813,376 samples,
  174,724 s; lengths 5,920 / 19,680 median / 28,960.
  Canonical ground truth: 39,569 literal EDF+ onset/duration/code intervals.
  T0 rest stays an ordinary scored state; T1/T2 meanings remain run-dependent
  with paradigm/state-meaning metadata. Preserve baseline eyes-open/closed context
  without inferring motor labels. S089R01/R02 actually contain T0 for 0.1 s then
  T1 for 60.05 s despite the baseline protocol: retain the raw codes, flag the
  anomaly and leave baseline T1 task semantics unresolved. Other baselines have
  only T0. Half-open intervals mapped from exact decimal fractions; outside
  explicit coverage and contradictory overlaps remain -1. 58,412 unscored samples
  (0.210014%), including 908 conflicts. 41,126 segments; recurrence 1,308/1,526,
  including substantive T1/T2 recurrence in all 1,308 task runs; per-state segment
  counts retained for every series. Evaluate by participant.
  Original WFDB conversions retained separately: 38,641 events; only 1,260 runs
  exactly match EDF intervals. Strict onset/code/duration comparison finds 1,036
  EDF intervals missing/non-identical and 108 non-identical WFDB events, including
  decimal-time quantization differences. Preserve sample-zero NOTE annotations
  using WFDB's byte-pair decoder; `rdann` otherwise removes genuine initial T0.
  No fabricated second annotator or agreement. Patient/recording text, dates and
  demographics excluded. ODC-By-1.0 verified at primary PhysioNet on 2026-10-19;
  all 3,052 EDF/event files + RECORDS/SHA256SUMS pinned against primary manifest
  and official S3 sizes. Sequential fetch, no archive extraction. Direct EDF
  decoder validates every record clock, geometry, channel and calibration;
  signals/TALs match pyedflib on standard, 128-Hz and long pilots.
  Fourteen-run size pilot: actual 65.74 bytes/sample for native64; worst isolated
  run 83.59. Worst ratio +25% +64 MiB projects 2.81 GiB output and 18.26 GiB free
  before build. Rolling projections after each run include buffered samples,
  actual compression, missing sources and metadata; actual minimum remained
  above 19.3 GiB. Final output 1.85 GB, seven shared data parts. Full validation:
  13 checksummed files, **0 errors / 0 warnings**. Exact native grids checked for
  all 1,526 runs; all 64 output channels equal source for S088R03/S089R01, including
  the unresolved baseline code. Raw cache deleted only after successful validation;
  pilot raw untouched, 22.75 GiB free. No publication. Next: Capture-24.

- [x] Batch 3 / PPG-DaLiA: all 15 synchronized participant recordings,
  8,287,296 native 64-Hz BVP samples (129,489 s); lengths
  336,000 / 573,312 median / 681,472. All 11 genuine channels retained:
  default BVP; shared native auxiliary stream groups for wrist ACC (32 Hz),
  EDA/TEMP (4 Hz), chest ECG/Resp/ACC (700 Hz). Thorax tables roll at about
  256 MiB, with bounded 262,144-sample row groups; no file per participant.
  Provider-documented dummy chest EDA/EMG/Temp excluded. Source synchronization
  and sparse clock-drift deletions preserved; no additional resampling,
  interpolation, scaling or duration trimming. S6 keeps its valid 1.5-hour portion.
  All nine activity codes retained; transient 0 is an ordinary scored null state.
  249 segments, no missing activity labels. Ordinary-state recurrence is 15/15,
  entirely due to transient 0; substantive activity recurrence is **0/15**.
  Supports protocol boundary CPD, with weak substantive SD recurrence; both
  metrics retained, and participant-level evaluation required. Original 4-Hz
  activity (517,956 samples), ECG-derived HR windows and literal corrected
  R-peak indices kept separately; HR is not segmentation truth. Questionnaires,
  demographics and absolute device timestamps excluded. CC BY 4.0 verified at
  primary UCI 495 on 2026-10-19. Existing 1.46-GB partial archive reused:
  UCI ignored Range, so streamed and compared its entire prefix before appending;
  exact size / primary wrapper CRC checked, then SHA256 pinned (archive and README).
  Restricted unpickler permits only numeric NumPy reconstruction primitives;
  object arrays and arbitrary globals rejected. Output: 1.32 GB total, one default
  part plus seven native sensor shards. Full Croissant/schema/checksum validation:
  15 checksummed files, **0 errors / 0 warnings**. All native per-subject grids and
  counts checked; first S1 row groups match source float32 exactly for all ten
  auxiliary channels. Raw cache deleted only after successful validation;
  pilot raw untouched, 25 GiB free (minimum observed about 22 GiB; reserve 18 GiB).
  No publication. Next: EEGMMIDB.

- [x] Batch 3 / Helsinki neonatal EEG: all 79 recordings, 103,123,200
  samples at native 256 Hz (402,825 s); lengths 802,048 / 1,143,808 median /
  3,946,496. Default: eight bilateral EEG electrodes
  Fp1/Fp2/C3/C4/T3/T4/O1/O2; full: all 19 EEG plus ECG and respiration.
  Every source channel has EDF physical dimension uV, including ECG and
  respiration. Three native layouts (17/45/17) mapped by normalized names,
  preserving original channel/calibration headers. eeg4/eeg29/eeg50 declare
  EDF+C without an annotation channel; direct int16 decoding validates record
  counters, one-second record durations and exact byte lengths. Calibrated
  float32 values match pyedflib exactly for eeg1/2/3/5 across all three layouts.
  Preserve record order and nominal 256-Hz grid; no invented gap durations.
  Corrected v4 A_fixed/B/C CSV labels equal MAT throughout all actual durations;
  no missing expert labels. Original 1-Hz labels retained auxiliary. Expert
  seizure events A/B/C: 402/429/548, segments 875/928/1,161; recurrence
  45/43/52 of 79. Strict derived unanimous consensus has 1,793 segments,
  recurrence 56/79 and 34,583 unscored disagreement seconds (8.5851%); 39
  recordings have unanimous seizures. Mean subject/pair kappa 0.68457 and
  agreement 0.94228 (237 pairs; constant agreeing kappa defined as 1).
  Clinical/demographic data, patient text and dates excluded. Reduced default
  spatial context can hide focal seizures; full preserves all observation channels.
  CC BY 4.0 verified at primary Zenodo v4 on 2026-10-19; all 83 sources
  SHA256-pinned and checked against primary MD5/size. Shared card helper now
  accepts an explicit licence verification date, preserving prior defaults.
  Default/full 2.59/6.14 GB (37 parts); full validation: 42 files,
  **0 errors / 0 warnings**. Three-layout sizing pilot justified the eight-channel
  default and 18-GiB stop reserve; minimum free space stayed about 23 GiB.
  Raw cache (4.1 GiB) deleted only after validation; 27 GiB remain available.
  Pilot raw and completed builds untouched. No publication.

- [x] Batch 3 / Sleep-EDFx: all 197 complete PSG/hypnogram pairs (153 SC,
  44 ST; 100 subjects), 1,385,653,000 samples at 100 Hz; lengths
  2,698,000 / 8,166,000 median / 8,640,000. Seven original R&K states,
  28,446 segments, recurrence 197/197; only unknown/uncovered samples are -1
  (0.870059%). No wake cropping or stage merging; Movement time retained.
  Default: both EEG derivations and EOG; full adds ST native 100-Hz EMG
  (SC dimension NaN). All 656 slow streams retained at native rates, including
  the ST marker at **10 Hz**, correcting the source summary's 1-Hz claim;
  28,529 original annotation intervals retained separately.
  Seven ST EDF+ hypnograms have stale Recordingfield dates one day before
  their fixed startdates (ST7021, ST7071, ST7092, ST7131/2, ST7141/2). Direct
  TAL decoding preserves sources unchanged, matches pyedflib exactly on its
  190 accepted files, and uses fixed EDF clocks consistently: all 197 offsets
  are zero. Both clock claims and conflict flags are retained in the index.
  Patient header text and demographic spreadsheets excluded; group by subject.
  ODC-By-1.0 verified at primary PhysioNet on 2026-10-18; all 394 source files
  SHA256-pinned against the freshly verified primary manifest. Citation follows
  Kemp 2000 and the current requested PhysioNet citation Pollard 2026.
  Default/full: 16.15/16.44 GB, 130 Parquet parts. Full validation: 136 files,
  **0 errors / 0 warnings**. Raw cache (8.2 GiB) deleted only after successful
  validation; pilot raw untouched. Filesystem headroom: 36 GiB. No publication.

- [x] Shared card metadata corrected after batch 2: `size_categories` now uses
  the number of series, giving `1K<n<10K` for the 1,119 measured 3W series and
  `10K<n<100K` for Neuroblastoma's 13,800 chromosome series. The shared
  annotation text now acknowledges independent expert tracks and their
  measured agreement for Lund and TCPD, instead of claiming they are absent.
  All four affected builds were regenerated from cached, SHA-pinned sources;
  each passes `scripts/validate.py` with 0 errors / 0 warnings. Other builders
  have fewer than 1,000 series or use their own card generator.

- [x] Batch 2 / Bee Dance source-only: all six original tracked trajectories,
  x/y/heading in float64; 4,966 samples, lengths 603 / 785.5 median / 1,125,
  three exact behavior names, 123 segments, recurrence 6/6, no missing labels.
  Only label0.btf is scored, explicitly identified as GT by primary manual
  section 4. Undocumented label1 in two sequences, tracking IDs, available
  framestamps and interval-like text retained unscored auxiliary; no fabricated
  second expert or consensus. Model outputs and executables never used as GT
  or run. Native timestamps advance by 33 units, but physical unit/rate is not
  established; sampling_rate_hz=None corrects unverified registry 30-Hz claim.
  Sequence6 overlaps TCPD bee_waggle_6; not independent evaluation material.
  Primary page/manual/archive have no redistribution licence: tier C/source-only,
  citation requested, verified 2026-10-18; docs/licenses/bee-dance.md.
  Archive SHA256 `9b1277fd38026570ecee6c5a5602439b0aae1264185abf41311ad6646387ccb0`,
  MD5 also matches primary TCPD source expectation. Raw 3.5 MiB, build 180 KiB.
  Validation 0 errors / 0 warnings.

- [x] Batch 2 / TCPD source-only builder: all **27 bundled measured signals**,
  6,660 observations, lengths 15 / 205 median / 816; all native dimensions retained
  (run_log two channels; absent dimensions NaN, native channel names in index).
  Eight expert IDs, five expert lists per series, all 320 CP markers; absent
  expert lists null versus scored no-change []. No semantic state/recurrence or
  CP consensus invented. Exact pairwise CP-set Jaccard auxiliary; native full
  calendar/numeric time structures remain auxiliary beside source integer index.
  Two native missing values in uk_coal_employ retained. All 37 real-series labels
  and per-source provenance retained even where signal pending; all five fully
  synthetic quality_control inputs excluded. **Ten non-bundled measured signals
  still require reconstruction**, listed in docs/licenses/tcpd.md and metadata.
  --extra-json-dir accepts native files only with primary MD5; --require-complete
  rejects missing signals. No downloaded collector executed. Primary README
  explicitly distinguishes MIT code from mixed upstream data rights; tier C,
  no rehosting. Source revision `e8f19a3635e3b7f1a8aff59ce7f4d9bea17525c0`, SHA256
  `056787f65d2a2e838d82e278d439887bd2fc093cb4209120ff0e28fa38fc2941`;
  checked 2026-10-18. Raw 4.7 MiB, build under 1 MiB. Validation 0/0.

- [x] Batch 2 / MOSAD: 14 native recordings restored to all nine axes
  (accelerometer, gyroscope, magnetometer), rather than the 126 separate
  univariate benchmark views. All 481,056 samples at 50 Hz; lengths 11,131 /
  19,512 median / 62,110. Twenty exact activity names (not registry 21), 114
  segments, 100 source CP indices preserved; no repeated activity within any
  series, so requalified CPD. No missing labels or signals; no null class.
  Numeric NPZ read with allow_pickle=False, no provider code executed. Protocol
  indices retained as zero-based first new segment, with one-sample convention
  uncertainty explicitly documented. Exact nine-channel float32 SHA comparison
  against all 250 HAS builds found no complete duplicates; shared author/protocol
  and possible partial overlap remain a limitation, not evidence of independence.
  CC BY-SA 3.0 verified at primary README on 2026-10-18. Source revision
  `f5d4daf34cd94b7c7a150aa2a650d1d8a4971557`; NPZ SHA256
  `79b767f5bdad2e0bcd5ac96ac59bf287b1eb481be882003779d56ab4469c9687`,
  both annotation text files independently pinned. Raw 34 MiB, build 12 MiB.
  Validation 0 errors / 0 warnings.

- [x] Batch 2 / Bimacs body-pose view: all 540 trials, 221,108 frames,
  lengths 134 / 394 median / 1,035. Default all 25 joints x/y (50 channels),
  full adds 25 confidence scores. Left/right action targets stay separate,
  not annotators/consensus: 7,058 / 6,484 segments, recurrence 534 / 539 of 540;
  missing shares 0.405684% / 0.274979%. Idle 0 scored; 11 explicit source null
  intervals map -1. Every source endpoint equals frame_count-1; documented
  half-open bounds retained, final frame -1 for each hand (no invented extension).
  All raw intervals retained auxiliary. 4,513 frames have 2–5 person detections,
  contrary to the one-person format description; main signal is NaN there and
  every ambiguous detection is auxiliary with source rank, without arbitrary
  subject assignment. Native zero/zero-confidence joints otherwise unchanged.
  Only two primary CC0 annotation/body-pose ZIPs needed; both SHA match published
  hashes. No RGB-D downloaded. Mixed 15/30 fps cannot be assigned per trial from
  these ZIPs; sampling_rate_hz=None and frame indices retained. Primary server
  ignores HTTP Range (200); ~93 GiB image-archive metadata retrieval was stopped
  before reading bodies. Raw 269 MiB, build 52 MiB; build 20.2 s / RSS 522 MiB.
  Validation 0/0; terms verified at primary KIT site on 2026-10-18.

- [x] Batch 2 / CalMS21 task 1: all 89 sequences (70 train / 19 test),
  769,845 frames at 30 Hz (507,738 / 262,107), lengths 96 / 7,115 median /
  23,810. Default all 28 native body-point x/y coordinates for both mice; full
  additionally retains 14 MARS confidence scores. Native source sequence keys,
  expert ID 0 and train/test split retained. Four labels including ordinary
  other/background 3; 6,431 segments, recurrence 88/89, no missing ground truth.
  JSON streamed from ZIP one sequence at a time using declared ijson 3.4.0;
  no pickle, downloaded code, learned features or video loaded. No interpolation,
  confidence masking, normalisation or synthetic data. Scope explicitly task 1;
  multiple-annotator task 2 and new-behavior task 3 are not silently claimed.
  CC BY 4.0 verified at primary CaltechDATA on 2026-10-18; primary archive MD5
  matched, SHA256 `f1cd2f46771cc3834020d187604da53e5ff330121f5a816146f14192fb0bf427`.
  Raw 437 MiB, build 144 MiB; 17.0 s / RSS 323 MiB. Validation 0/0.

- [x] Batch 2 / AIS fishing: full primary CSV has **123 released trips**, not
  the 128 claimed in filename/title, from 84 vessel-ID prefixes. All 1,026,279
  observations, ten numeric position/trajectory variables in float64, native
  irregular second timestamps, lengths 901 / 5,610 median / 45,251. Five native
  source-phase strings preserved reversibly; activity track strips only the
  numeric prefix to keep literal sailing/fishing names. Both have 369 segments;
  source phase recurrence 0/123, activity recurrence 121/123. No missing labels
  or signals, no backward/duplicate timestamps, max gap 47,172 s. Group evaluation
  by source vessel to avoid leakage. No interpolation, timezone inference,
  speed-unit correction or invented missing trips. Primary author labels and
  CC BY 4.0 verified at Zenodo 7283281 on 2026-10-18; primary MD5 checked for CSV
  and README. CSV SHA256
  `787bd946fadf0c114f4925dd3ee792e64034311fd4940ea47b91b4ddd804b8ad`.
  Raw 162 MiB, build 55 MiB, 3.4 s / RSS 503 MiB. Validation 0/0.

- [x] Batch 2 / Swimming smartwatch: all 206 sessions / 40 swimmers,
  1,962,177 observations at provider-resampled 30 Hz; lengths 1,321 / 6,442.5
  median / 53,421. Default all 11 measured sensor channels (74 MiB); full also
  retains 12 native derived norms (143 MiB). Seven scored states: the README
  omits code 6 Kick and -1 Unknown, confirmed in author-linked code constants
  downloaded only as inert text and independently SHA-pinned. All 77,943 source
  Unknown samples remain -1 (3.97227%); Null 0/rest, Turn 5 and Kick 6 stay scored.
  2,410 segments, recurrence 205/206, no nonfinite sensors or reversed/duplicate
  uptime timestamps. Original pandas row IDs retained auxiliary. **Rights hold:**
  no licence grant in complete primary repository tree/README; prior registry
  MIT attribution unsupported. Tier C/source-only; docs/licenses/swimming-smartwatch.md.
  Source revision `468ee355675b51fb3b9ad9d992ef7b807ae1af4f`, archive SHA256
  `d607802935eaca9504082c053f6d6f3308b0cf4c696fc47375cb4a4fbb395c12`.
  Raw 407 MiB, build 218 MiB; build 11.8 s, RSS 451 MiB. Validation 0/0.

- [x] Batch 2 / Lund 2013: **34 distinct article trials**, stored as 39
  series (29 identical-signal expert pairs + five unequal trials × two native
  copies). Trial/participant/annotator IDs in index prevent treating copies as
  independent; split and uncertainty grouping must use trial/participant IDs.
  All four measured channels (gaze x/y and horizontal/vertical pupil), 500 Hz,
  119,017 stored samples, lengths 453 / 2,823 median / 4,990. MN/RA labels
  retained; provider Zemblys2018 correction changes 75 MN labels and complete
  original/corrected arrays remain auxiliary. Undefined 6 and blink 5 are ordinary
  states. Paired consensus requires exact agreement (disagreement -1); individual
  copies use their one available expert, unavailable track -1. Consensus has
  2,508 segments, recurrence 39/39 stored copies, 6.7058% missing labels.
  Agreement on 88,749 exact paired samples: 91.0072%, Cohen kappa 0.84585;
  no agreement is invented for unequal copies. Native timestamps retained,
  11,447 missing timestamps remain NaN. GPL-3 explicitly covers data in primary
  README.docx (checked 2026-10-18). Pinned revision `3e12416ab3fd6254c81811cf03f8e5d67c5d7129`,
  SHA256 `a6ebfaf3eb1a7bc4dcee64d6952c0b508eb2127f0174bf084d92297f4bb1eb1a`.
  Raw 85 MiB, build 1.6 MiB. Validation 0 errors / 0 warnings.

- [x] Batch 2 / Neuroblastoma: all 575 native profiles, split into 13,800
  profile/chromosome series, 4,616,846 probe values; lengths 2 / 149 median /
  5,937. All 3,418 expert regions preserved (2,845 normal = zero changes,
  573 breakpoint = at least one change), covering 3,418 chromosome series.
  These are weak genomic constraints: no exact CP, dense state, consensus or
  recurrence is invented. Unannotated positions remain unconstrained; normal
  is an ordinary zero-change constraint. Native region endpoints are preserved
  without inventing an inclusion convention. Float64 normalized logratios and
  irregular integer base-pair coordinates retained; no missing values or duplicate
  positions. GPL-3 package terms verified at primary CRAN on 2026-10-18;
  version 2023.9.3 SHA256
  `3076d317455067bf55d6475119472ec4116461890624777bb1fc90d5b3f6c2a2`.
  Reproducible pure Python RData reader declared in build dependencies; no R
  source code executed. Raw 7.9 MiB, build 38 MiB. Validation 0 errors / 0 warnings.

- [x] Batch 2 / RIPE Atlas RTT: all 50 measured source traces, 408,087 RTT
  values in milliseconds, lengths 1,646 / 8,501 median / 12,001, and all
  **1,047 manual change point markers**. No synthetic traces from the same
  repository are included. No semantic states or recurrence are claimed.
  Native source order and two timestamp formats retained; observations are
  irregular around four minutes apart, including four short backward steps and
  gaps up to 18,003 s. One released annotation track has no per-person IDs or
  agreement statistic. Pinned source revision `d090227f1e6deb158ac0d5c06966318d5e163d83`,
  archive SHA256 `4c653cf6f840bdf85816c77b1b5b73de01cb36ceebbe54a1ebca15119fac275b`.
  Repository MIT licence and RIPE Atlas terms v3.5 art. 4.5 checked on
  2026-10-18: **tier C/source-only** pending upstream permission; see
  `docs/licenses/rtt-ripe-atlas-labelled.md`. Raw 9.3 MiB, validation 0 errors /
  0 warnings.

- [x] Batch 2 / Petrobras 3W 2.0.0: all **1,119 measured** source instances
  by default, all 27 channels at provider-interpolated 1 Hz, 32,872,250
  observations, lengths 5,215 / 21,354 median / 768,314. Source registry
  erroneously attributed all-origin totals to real data: exact Parquet metadata
  totals are real 32,872,250 + simulated 40,748,658 + drawn 2,966,410 =
  76,587,318. Default class track: 2,393 segments, **no recurrence** (CPD).
  Operational track: 2,306 segments, recurrence only 10/1,119. Unknown labels
  map NaN -> -1 in each track (12.2547% in real data; 5.26% used all-origin
  denominator). Normal/Open code 0 stays scored. Missing/frozen sensors and
  outliers retained; no new interpolation. Explicit --include-generated option
  retains source origin and RAI synthetic flag; default counts/build exclude
  every simulated/drawn instance. Entire archive MD5 primary + SHA verified;
  CC BY 4.0 checked at primary Figshare and Petrobras on 2026-10-18.
  Raw 1.67 GiB, measured build 199 MiB. Validation 0 errors / 0 warnings.

- [x] Batch 2 / UCI Gas dynamic mixtures: both complete measured recordings,
  all 16 sensor channels at nominal 100 Hz; **8,386,765** samples (CO:
  4,208,261; methane: 4,178,504, correcting registry total/length). Reversible
  concentration-pair labels, 178 mixture-scoped states, 725 segments, recurrence
  2/2, no missing labels. Zero exposure is ordinary state; concentration
  setpoints are labels, never input channels. Exact source timestamps retained,
  including 122,672 / 104,950 duplicate steps and gaps up to 0.38 / 0.27 s,
  no reversal. **Rights hold:** same primary UCI page displays CC BY 4.0 but
  restricts use to research and excludes commercial purposes. Conservatively
  tier C/source-only; docs/licenses/uci-gas-dynamic-mixtures.md records conflict.
  Archive SHA256 pinned; raw 352 MiB/build 270 MiB. Build 25.16 s, peak
  RSS 1.91 GiB; validation 0 errors / 0 warnings.

- [x] Batch 2 / Pneumatic EOL: all 468 CSV files form 156 triplets, not
  468 series. 4,751,340 native sensor samples and all 3,673 original PLC
  events retained; never unpickle source alternatives. Main two-channel stream
  uses exact sensor timestamp union (2,390,995 rows, lengths 430 / 16,650
  median / 19,840), irregular despite nominal 100-Hz sensors. No interpolation
  or nearest matching; repeated timestamps retain occurrence ranks. Native
  source order preserved in streamed auxiliary (631 reversals, 214 duplicate
  sensor timestamps). PLC steps-post labels only actual measurements: no
  PLC-only rows/initial all-NaN idle state. 3,536 segments, recurrence 66/156
  **only in state 0**; no nonzero state recurs, so SD coverage is limited.
  Zero is an ordinary PLC state; no unlabelled samples. Two one-second PLC
  filename differences explicitly mapped, with timestamp overlap verified;
  no time shifts. Primary Mendeley v3 CC BY 4.0 verified 2026-10-18, all 468
  primary SHA pins committed. Final cached build: 5.94 s, 277 MiB peak RSS,
  one triplet in memory. Raw 100 MiB/build 41 MiB. Validation 0/0.

- [x] Batch 2 / CNC Mill UMich: all 18 experiments, all 47 numeric channels
  at 10 Hz; 25,286 samples, lengths 462 / 1,341 median / 2,332; 158
  process segments, recurrence 14/18, no missing ground truth. All eleven
  exact source state strings retained (End/end kept distinct); Starting, Prep
  and Repositioning are ordinary protocol states. Original tool/clamp/feed/
  inspection metadata retained; unavailable inspection remains metadata null.
  Source known invalid-variable conditions and control-channel label leakage
  risk documented; no silent repairs. Primary Sharon Sun/SMART Kaggle v4 CC0
  verified 2026-10-18, version URL and SHA pinned. Validation 0/0.

- [x] CASAS timestamp audit: independent datetime.fromisoformat over original
  source lines reproduces largest backward jumps exactly (Aruba source row
  1,571,287: 2011-05-23 23:39:59.215044 -> 00:02:56.715882; Milan row
  124,569: 2009-11-24 17:21:24.000069 -> 00:00:09.000084). They are
  source anomalies, not pandas date parsing or row alignment artefacts.

- [x] Batch 2 / CASAS: five original event logs for four homes (both Tulum
  sessions distinct), 4,452,569 events, lengths 433,665 / 726,534 median /
  1,719,558; 42 sensor-ID columns with sparse updates, no regular rate or
  forward fill. 45,506 joint-state segments, recurrence 5/5, 52.1403%
  unannotated/ambiguous. Simultaneous activities preserved as 182 reversible
  activity sets plus exact markers and intervals; per-activity recurrence
  counts also retained. All 51,291 timestamp reversals retained (Aruba up to
  85,022 s, Milan 62,475 s); task explicitly uses original event order.
  Five anomalous Tulum2 intervals mask 10,823 events; no marker spelling
  correction. All 167 invalid sensor messages retained verbatim in auxiliary,
  represented by signal NaN. CC BY 4.0 verified at official Cook/WSU Zenodo
  deposit on 2026-10-18; primary MD5 and calculated SHA256 checked. Validation 0/0.

- [x] Batch 2 / VFDB: all 22 original records, both calibrated ECG channels at
  250 Hz; 11,550,000 samples (525,000 each). Rhythm track: 488 segments,
  recurrence 17/22, 3.69281% unknown before first explicit cardiac rhythm.
  Quality track: 183 segments, recurrence 14/22, 0.12676% before first
  annotation unscored. Primary provider explicitly says rhythm continues through
  NOISE until next annotation: preserve that rhythm and encode noise separately,
  never invent a noise cardiac state. If noise precedes a known rhythm, rhythm
  remains -1. NSR/N and VFIB/VF aliases canonicalised with raw notes preserved.
  ASYS remains ordinary clinical state. ODC-By-1.0 verified at PhysioNet on
  2026-10-18; all 66 files SHA-pinned; validation 0 errors / 0 warnings.

- [x] Batch 2 / AFDB: all 23 source records with ECG signals (00735/03665
  annotation-only excluded), both channels at 250 Hz; 210,851,720 samples,
  lengths 8,325,000 / 9,205,760 median/max; 628 rhythm segments, recurrence
  21/23, 0.000937% before first explicit rhythm annotation unlabelled (-1).
  N means other rhythms, not necessarily sinus rhythm. Source-inserted zero
  blocks in 04043/08405/08434 preserved and documented; 06453 shorter duration
  retained. Manual rhythm annotations kept sparse as well; automated unaudited
  .qrs detections excluded from ground truth. ODC-By-1.0 verified at PhysioNet
  2026-10-18; all signal/header/rhythm files SHA-pinned, official public S3
  transport. Validation 0 errors / 0 warnings.

- [x] Batch 2 / MITDB: all 48 source records, both calibrated ECG channels
  at 360 Hz, 31,200,000 samples (650,000 each); 1,338 rhythm segments,
  recurrence 29/48, 0.007913% before first explicit rhythm annotation left -1.
  Dense rhythm states come only from parenthesised .atr notes; sparse beat,
  quality and other annotations preserved intact in annotations.parquet, never
  expanded into beat-state intervals. Variable lead names retained in index.
  All 144 files SHA-pinned against primary PhysioNet manifest; ODC-By-1.0
  verified 2026-10-18. Official public S3 transport bypasses primary host
  throttling (100.dat: 0.84 s versus 110 s, identical SHA). Validation 0/0.

- [x] Batch 2 / nonEEG: 20 native 8-Hz acceleration/temperature/EDA series,
  368,852 samples, lengths 18,175 / 18,247 median / 20,255; 180 segments,
  recurrence 20/20. Four semantic states (not five); mini-emotional instruction
  phase shares EmotionalStress. WFDB zero-based annotation positions preserved: first
  annotation at sample 1, leaving exactly one initial sample unlabelled per
  record (0.00542%). All SpO2/HR samples retained separately at native 1 Hz in
  physiology_1hz.parquet; device durations differ, no synthetic synchronisation.
  Exact transitions retained in annotations.parquet. Demographics omitted.
  ODC-By-1.0 verified at PhysioNet on 2026-10-18; source ZIP SHA256 pinned.
  WFDB 4.3.1 added to build dependencies and tsseg-env. Validation 0/0.

- [x] Batch 2 / Daphnet FoG: 17 actual sensor runs (not 29 archive entries),
  ten subjects, nine acceleration axes at 64 Hz; 1,917,887 samples, lengths
  38,774 / 109,886 median / 195,737; 561 segments, recurrence 16/17.
  Source code 0 explicitly outside experiment -> -1 (40.5160%); codes 1/2
  retained, timestamps and all rows preserved. Runs stay separate; subject-level
  grouping recommended by provider. CC BY 4.0 verified at UCI on 2026-10-18;
  archive SHA256 pinned. Validation 0 errors / 0 warnings.

- [x] Batch 2 / HARTH: all 22 complete recordings, six accelerometer axes at
  nominal 50 Hz, 6,461,328 samples, lengths 137,646 / 329,936.5 median /
  418,989; 6,971 segments, recurrence 22/22, no missing labels. All twelve
  source states retained, including shuffling/inactive cycling; no null class
  invented. Source timestamps retained; discontinuities reach 302.18 s (S010),
  so the physical time grid is not uniformly continuous. CC BY 4.0 verified
  at UCI on 2026-10-18; SHA256-pinned archive. Validation 0 errors / 0 warnings.

- [x] Batch 2 / HAPT: all 61 raw experiments, 30 subjects, six axes at 50 Hz,
  1,122,772 samples, lengths 9,898 / 17,963 median / 32,089; 1,847 segments,
  recurrence 61/61, 27.3571% outside source annotation intervals mapped to -1.
  All twelve states including postural transitions retained; original subject
  train/test split recovered. One-based inclusive interval convention declared;
  source readme leaves origin implicit (one-sample boundary uncertainty).
  **Licence conflict:** UCI CC BY 4.0 versus archive README non-commercial
  prohibition; conservatively tier C/source-only pending clarification, recorded
  in docs/licenses/hapt.md and card/Croissant. SHA256 pinned; validation 0/0.

- [x] Batch 2 / MHEALTH: ten complete subject logs, all 23 motion/ECG channels at
  50 Hz, 1,215,745 samples, lengths 98,304 / 120,960 median / 161,280; 262
  segments, recurrence in 10/10, no missing labels. Code 0 explicitly called
  null by the primary readme: retained as an ordinary state (not -1). Source
  column-12 typo documented. CC BY 4.0 verified at UCI on 2026-10-18; archive
  SHA256 pinned. Croissant/Parquet validation: 0 errors / 0 warnings.

- [x] Selection review (2026-10-18): removed the fully generated Time2State and
  PaTSS corpora from the active shortlist. Retained TSSB and USC-HAD constructions
  from measured recordings, as requested. The target remains about 50 datasets,
  without an interim hard cap. Checked tsseg-exp issue #1: MIT-BIH Arrhythmia and
  Sleep-EDFx were already selected; added VFDB (22 rhythm-annotated ECG records,
  ODC-By-1.0) and WESAD (15-subject stress/affect dataset, source-only under
  Siegen's scientific non-commercial terms). Google Trends `mail_week.csv` is a
  separate real-data candidate in the PaTSS deposit; reference CP/SD labels are
  not established. Rbeast's `beach` example is another signal, not verified
  benchmark ground truth. The issue's example loaders make univariate views;
  builders will preserve the original multivariate signals. Sources and caveats
  are in registry/shortlist.yaml.

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
  `pilot/.venv`, required RAI, explicit primary source URI in `prov:wasDerivedFrom`
  (DOI when established; no future collection destination as sole provenance), three
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

## Pilot sizes before the full Dreem build

| Dataset | Pilot build | pilot/out |
|---|---|---|
| mozilla-perf-cpd-annotations | 0.8 MB (1 part) | 3.8 MB (174 files) |
| opportunity | 16 MiB default + 184 MiB full | 235 MB |
| dreem-dod-h (3 nights) | 89 MiB default (100 Hz) + 888 MiB full (4 parts) | 1.3 GB |

Gains come from zstd level 9 + byte-stream-split encoding of the float columns.

- [ ] Batch 3 / Capture-24 — **deferred before corpus download** (2026-10-19).
  Primary author paper (doi:10.1038/s41597-024-03960-3, Data Records) confirms
  CC BY 4.0 **data**, distinct from the academic/non-commercial Oxford utilities
  software licence. 151 participants, 3,883 h at released 100 Hz, three XYZ g
  channels; 2,562 h annotated, 206 CPA codes and six derived label mappings.
  Camera images are not released. Missing camera/diary ground truth must remain
  -1; dictionary mappings are derived taxonomies, not independent annotators.
  Provider processing already includes nearest-neighbour rate correction and
  gravity calibration; retain the released signal, without new resampling.
  Native sensor timing does not imply sample-exact 100-Hz behavioral annotation
  (camera images about every 20 s). Source counts are paper-reported, not yet
  recomputed from files. Dataset ORA landing page currently returns HTTP 403;
  official archive Range probe returns HTTP 200 without Content-Range or length,
  so the response was closed without reading corpus bytes. A later ordinary
  archive GET also returned 403. The source team's download documentation says
  the ZIP is **over 6.5 GB** (prepare_data.py progress estimate 6.9e9 bytes).
  Measured free 22.743 GiB leaves only 4.743 GiB above the 18-GiB reserve;
  even the documented 6.5-GB lower bound alone would leave 16.689 GiB, before
  any Parquet output. No full archive, CSV extraction, subject subset or reduced
  frequency build downloaded; no safe selective pilot available on this endpoint.
  **Next step:** supply a separate data volume for future Capture-24 raw/output,
  or a primary Range-capable subject endpoint; obtain a pinned one-subject pilot
  there, then require free >= source cache + measured full output * 1.25 + 18 GiB
  before downloading the corpus. Recheck current ORA licence/privacy wording when
  its landing page is accessible. Keep all 151 subjects/three released channels
  in the eventual build. Continue with BEBE qualification; no existing data deleted.

## To do

- [ ] Batch 3 / DEDDIAG storage gate (2026-10-19): the primary Figshare v1
  manifest lists 15 house ZIPs totaling 15,301,162,142 bytes (14.25 GiB).
  With about 21.37 GiB free and the 18-GiB reserve, a complete local cache
  cannot fit even before conversion. Only primary metadata/README were read;
  no house ZIP or build was started. Resume when storage is available, or
  design and validate a genuinely bounded source-streaming workflow.
- [ ] Batch 3 / AnDy compact views deferred (2026-10-20): primary paper confirms
  common Xsens/avatar-video starts, 240-Hz motion and 24-fps annotations. Full
  native BVH has 72 position/Euler channels; C3D has 64 model-derived XYZ points
  (192 channels). Three rater slots are trial-local, sampled from four people.
  Two paired pilots reveal a 13-sample-equivalent video tail in one trial;
  future interval mapping must audit all trials without stretching labels.
  Complete-view output projections with 25% margin and source caches leave
  17.89 GiB (BVH) / 17.61 GiB (C3D), below the 18-GiB reserve. No complete motion
  archive or build downloaded; bounded pilots and 4-MB labels cache retained.
  Detailed sources, sizes and resume rules: docs/qualification/andy-ha4m.md.
- [x] Batch 3 / HA4M completed locally (2026-10-20): all 217 native skeleton
  trials / 41 subjects, 642,268 frame positions, 384 observations per frame;
  nominal 30 fps, native timestamps retained (1,469 duplicates, no reversals).
  All 639,590 native body blocks are preserved exactly once: 639,517 main poses
  plus 73 auxiliary blocks. Main is NaN on 2,751 unavailable/ambiguous frames;
  no interpolation, geometric actor choice or person-specific labels.
  One released manual reference checked by two researchers; ordinary null 0
  stays scored. Recurrence is 204/217 including null, versus 49/217 for
  substantive action classes 1–12; 3,224 semantic runs, 4,124 action/repetition
  runs including 435 null instances. The README's 4,123 count differs by one.
  IDU039V001/V002 use the reversed association of the original CC-BY CSVs,
  supported by exact full-vector agreement with pinned later author GT files.
  Those unlicensed evidence files are not packaged; every original annotation
  row and repetition index is retained separately.
  Complete build about 624 MB, SHA-pinned native content and original CSVs.
  Final validator: 0 errors / 0 warnings, all 10 checksummed files, 3 main parts.
  Independent literal-source reconstruction passed 217/217: every observation,
  body ID, source block index, timestamp, original/corrected label and repetition
  is exact after the documented float32 cast. Logs raw/ha4m-validation.log and
  raw/ha4m-reconstruction.log remain outside the removable cache.
  The full job stayed above 18 GiB: measured build minimum 19.268 GiB,
  projected minimum 18.873 GiB.
  Only raw/ha4m was deleted after both successful gates (1,177,011,113 bytes).
  Free before/after cleanup: 19.351 / 20.448 GiB; other caches remain untouched.
  Detailed source rights, association evidence, reconstruction and storage:
  docs/qualification/andy-ha4m.md. ROSMAG40 completed below.
- [x] Batch 3 / ROSMAG40 complete (2026-10-20): all 40 actual released trials,
  72,843 frame-aligned rows, five users, two tasks, all 34 published features.
  Source Zenodo description says 22 videos; actual archive and primary paper
  contain 40. This is the complete provider-processed ROSMAG40 view, not a
  reconstruction of the original ROSMA154/160-channel 50-Hz corpus.
  Four human tracks retain MD/FGD independently for PSM1/PSM2; no invented
  annotator/consensus. Exact author row pairing, all triplet lengths agree and
  hierarchy exact everywhere. Idle1 stays scored, no missing labels. Recurrence
  40/40 each track including idle; substantive39/40 PSM1 and40/40 PSM2.
  Native timestamps and explicit provider aggregation recipe absent, so retain
  source_row_index and physical sampling_rate_hz=null; nominal video15 fps is
  provenance only. No guessed synchronization or conversion to50 Hz/15 Hz.
  Primary Zenodo CC BY4.0 verified. HTTP206 selective prefix12,980,548 bytes
  contains all120 selected TXT members, zero video members; prefix/member SHA256
  and native CRC/size pinned. Full archive3.98GB never acquired.
  Complete build about7.93MB; conservative full source/output+64MiB gate
  155,448,294 bytes, additional audit copies still leave>20.26GiB projected.
  Final validator0 errors/0 warnings (5 files,1 part); independent exact literal
  source comparison passed all40 trials, every34-float row, four labels, row order,
  subject ID and source SHA/CRC. Logs raw/rosmag40-validation.log and
  raw/rosmag40-reconstruction.log remain outside removable cache.
  Only raw/rosmag40 deleted after successful gates (50,874,306 bytes).
  Free before/after: 20.393 / 20.441 GiB; other caches untouched.
  See docs/qualification/rosmag40.md. Next: Fly vs. Fly
  tracking features only; no next heavy job started.
- [ ] Continue batch 3 one heavy dataset at a time, using the size and
  alignment gates above; WESAD remains source-only. Tier C author contacts
  and TSSB upstream rights also require attention.
- [ ] TCPD: reconstruct the ten non-bundled measured native JSONs; default local
  build is explicitly 27/37 and --require-complete fails until they are supplied.
- [ ] Verify whether the real Google Trends series in the PaTSS deposit has
  independent reference boundaries, or find a better labelled primary source.
  Do not treat method predictions or visually chosen changes as ground truth.
- [x] Dreem: all 25 nights built with `--all-records` and validated (0 errors,
  0 warnings; 49 checksummed files, 44 Parquet parts). All 25 H5 files and 125
  scorer JSONs are SHA256-pinned. The full/native config has 184,987,500 samples
  across 16 channels at 250 Hz; the default has 73,995,000 samples across four
  resampled channels at 100 Hz. Full-series lengths: 4,650,000 / 7,395,000 /
  8,940,000 (min / median / max). Consensus: 2,649 segments, recurrence in all
  25 nights, no missing epochs within evaluation windows. Mean pairwise scorer
  kappa 0.701, ARI 0.593, transition F1 within one epoch 0.540. The file
  `5bf0f969-304c-581e-949c-50c108f62846.h5` has record_id
  `63b799f6-8a4f-4224-8797-ea971f78fb53`, so its lights-off cut starts at
  epoch 60. Native/default Parquet: 9.30 / 0.94 GB. The 20 GB raw cache was
  deleted after successful validation to preserve disk space; the pilot raw
  cache remains untouched. Source licence confirmed at the primary Zenodo
  deposit (MIT, deposited by paper co-author Valentin Thorey).
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

7. Accepted: local Croissant record read on a one-row excerpt: the full files
   are checked by `validate.py` itself (SHA256, Parquet schemas and all rows),
   while `mlcroissant` on a full long-series file has taken 433 s and 10.5 GB RAM.
   Keep this local split of checks, then run the official online
   Croissant checker before publication; revise sharding if it times out.
