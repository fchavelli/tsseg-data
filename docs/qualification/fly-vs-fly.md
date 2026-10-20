# Fly vs. Fly: native tracking qualification (2026-10-20)

Status: **complete tracking conversion, validator0 errors/0 warnings and independent
exact source reconstruction47/47**. Final results are recorded below. The initial shared storage pause is documented
in the historical storage section. Nothing is published.

## Primary source and selected scope

Primary record: <https://data.caltech.edu/records/zrznw-w7386>, DOI
<https://doi.org/10.22002/D1.1893>. The CaltechDATA API reports version 1.0 and
rights `cc-zero`, verified 2026-10-20. API evidence is cached locally as
`raw/fly-vs-fly-record.json`.

Read central directories by exact bounded HTTP206 ranges from the three primary
ZIPs. The complete archives total 3,686,320,054 bytes and cannot be cached while
protecting an 18-GiB reserve. Select every non-AppleDouble `*_track.mat`,
`*_actions.mat` (including `*_second_actions.mat`) and `traintest.mat`. This is the
complete released articulated tracking view; videos and derived `*_feat.mat`
features are outside the selected scope.

| Archive | Archive bytes | Selected members | Compressed selected bytes | Native selected bytes |
|---|---:|---:|---:|---:|
| Aggression.zip | 701,514,459 | 22 | 48,778,771 | 48,923,831 |
| BoyMeetsBoy_wo_movies.zip | 806,108,930 | 16 | 188,063,771 | 188,609,305 |
| Courtship.zip | 2,178,696,665 | 67 | 145,124,334 | 145,635,747 |

There are **47 track members**: 10 Aggression, six Boy meets boy and 31 Courtship;
47 primary action files; eight second action files (Aggression movie6;
Boy movies4/5/6; Courtship hyper movies6/7/8/9); three official split files.
All 47 tracks match the official split lists exactly: 24 train / 23 test scenes.
Courtship contains 21 wild and ten hyper trials. No trial selection was inferred
from a paper subset summary.

`curl -L` follows the API redirect to its short-lived signed storage endpoint.
Python urllib returned403 on this endpoint in the audit. Require final206,
exact `Content-Range` and exact body length. For a 30-byte local-header range,
curl's size cap must allow the small redirect body (~472 bytes); final-body
validation remains exact. Never execute downloaded visualizer MATLAB code.

## Native fields and annotation evidence

Primary FlyTracker documentation:
<https://kristinbranson.github.io/FlyTracker/documentation.html>.
Primary author visualizer: record file `visualizer.m`, read as text only.
Primary thesis: <https://thesis.library.caltech.edu/10281/7/eyjolfsdottir_eyrun_2017.pdf>,
chapter3/table3.2 (Boy200fps, Aggression/Courtship30fps). The visualizer's generic
30fps playback fallback is not evidence that Boy recordings are30fps.

Four bounded pilot tracks contain arrays `[2, n_frames, 17]`, 17 source names,
and a shared `flag_frames` vector. They contain 54,000 (Aggression movie1),
252,261 (Boy movie1), and 53,999 each (Courtship hyper/wild movie1) frames.
NaNs occur and must remain. Every fly's 17 fields must be retained.
Current documentation describes a five-column `trk.flags` identity-swap table,
whereas these pilots release `trk.flag_frames`; preserve literal values without
inventing an equivalent meaning. All 47 tracks have exactly these three fields. Five Courtship wild trials
(movie4/5/10/13/17) have 54,000 source flag entries for 53,999 pose frames. The
auxiliary table preserves every flag entry with its own length; no trajectory
frame is invented. Every flag is literally 0 or 1, without inferred meaning.

The author visualizer explicitly indexes bouts as `start:end`, establishing
**one-based inclusive** endpoints. Documentation names the third column
`certainty`; preserve it without inventing a confidence scale. Some action files
include explicit `unknown` intervals. Behaviors may overlap, so independent
binary behavior tracks per fly and released annotation slot are appropriate;
never impose an exclusive single class. A present behavior vocabulary permits
ordinary negative state 0 outside bouts. An absent vocabulary or absent second
annotation file gives missing ground truth-1. Explicit `unknown` bouts have no established behavioral ground truth: all
behavior tracks for that fly are masked to -1 there. Courtship traintest.mat
explicitly declares n_flies=1, and every second-row bout cell is empty; fly2
tracks remain -1 throughout. Empty cells for that unannotated fly cannot
establish negative labels.
Second annotation files do not establish independent raters or stable global
annotator identities. Metadata reports only concordance between released files
on common scored frames (accuracy and Cohen kappa), not inter-rater agreement.
All 11,040 original bouts are retained, including their literal order, behavior,
fly and certainty (four two-column bouts have null certainty). Certainty values
are 0/1/2/3 without an asserted confidence scale. All original endpoints satisfy
1 <= start <= end <= pose length; no clipping or endpoint repair is needed.

## Historical storage stop (resolved before the complete build)

Before acquisition, measured free21,888,061,440 bytes (~20.38GiB). Native selected
cache reached247,648,796 bytes; draft pilot output directory is only16,384 bytes.
The shared filesystem then dropped to18,695,249,920 bytes (~17.41GiB), later
18,433,294,336 bytes (~17.17GiB). The change exceeds this dataset's consumption
by roughly3GiB. Acquisition and pilot automatically raised the reserve guard;
all downloads/builds were stopped. No unrelated data was deleted.

The pilot conversion did **not** finish, so no usable output-size measurement or
source-parity proof exists. SHA256 values currently exist only for successfully
acquired pilot/incremental members; the final manifest must not be committed as
complete until every selected member is acquired and checked. Local logs:
`raw/fly-vs-fly-download.log`; partial source cache `raw/fly-vs-fly/` retained.

The original resumption gate was: resume only after the shared writer/storage change is resolved and sufficient
space is available. Run `df -B1 /` and `free -h`; one heavy job at a time. Measure
one complete pilot's native output, then require remaining complete source cache
+ measured full-output projection*1.25 + buffer +18GiB. The draft1GiB output
allowance is provisional, not an empirical gate. Reuse already CRC-checked files,
complete SHA pins and all-member schema/bout audit, verify independent exact
source parity, run full validator0 errors/0 warnings, update registry/README and
progress, then make one local dataset commit. Only after successful full build
and both validation gates may `raw/fly-vs-fly/` alone be deleted.

## Completed conversion and measured storage

The user resolved the external storage pressure; free space was rechecked at
46,790,352,896 bytes before the resumed pilot. The four-scene pilot produced
24,079,474 bytes for 414,259 frames (58.1266 bytes/frame). A conservative five-million
frame extrapolation with 25% margin is 363,291,352 bytes. The builder reserves
one GiB output plus the complete 383,168,883-byte source cache and 64 MiB buffer;
this exceeds both the pilot estimate and the final measured source-frame projection.
All subsequent downloads, builds and checks run sequentially, with df/free checks.

The complete corpus contains 3,702,554 native frames: 540,000 Aggression,
1,488,585 Boy meets boy, 1,673,969 Courtship. It has all 34 float32 observations,
40 independent binary label tracks, every original bout and a lossless flag run
table. Native NaNs are preserved exactly after the documented float32 cast.
No resampling, pose interpolation, smoothing, geometric normalization, identity
repair or source-derived feat.mat reconstruction is performed.

Global rate is null because scenes have native 30/200 fps. Per-scene rate and
`time_ns = floor(frame_index * 1e9 / fps)` encode nominal frame timing, without
asserting measured camera timestamps. Scene source split and both fly trajectories
remain together. Default label_primary_fly1_wing_extension is a convenience;
Aggression is unscored for this behavior. Binary negative state 0 remains ordinary
and scored; positive-run recurrence is reported separately from recurrence
that includes absence. Unknown intervals can fragment positive runs.

Final output is211,915,716 bytes: one main part, index, two auxiliary tables,
card, Croissant and loader metadata (seven checksummed files). Final validator:
**0 errors /0 warnings**, including Croissant1.1 metadata and record excerpts.
Independent reconstruction compared all47 scenes and3,702,554 frames: every
34-dimensional float32 vector including5,373,590 NaNs, every40-label vector,
all official splits, nominal time grids, every source flag and11,040 original
bouts match exactly. Logs remain outside the removed cache:
`raw/fly-vs-fly-validation.log`, `raw/fly-vs-fly-reconstruction.log`.

Forty-six of47 scenes contain overlapping positive behaviors. The convenience
default wing-extension track has2,920 runs, recurrence37/47 including absence,
and36/47 with repeated positive runs;14.861957% is unscored. These counts include
fragmentation by explicit unknown masks and must not imply37 diverse semantic
states. Per-track/scene counts and56 file-concordance comparisons are in metadata.

After both successful gates, only `raw/fly-vs-fly/` was removed (383,352,980 file
bytes). Free before/after cleanup:35,269,808,128 /35,653,214,208 bytes. Every other
cache and the four-trial pilot output (`build/fly-vs-fly-pilot-work/`) remain.
The shared filesystem continued to consume unrelated space during validation;
all resumed dataset jobs stayed above the18-GiB reserve and were sequential.
No remote or publication action was performed.
