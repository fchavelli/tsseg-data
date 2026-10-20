# Fly vs. Fly: native tracking qualification (2026-10-20)

Status: **incomplete; stopped by a shared filesystem reserve breach**. No complete
build, validation, independent reconstruction or dataset commit exists. Draft
builder/helper scripts are unvalidated and must not be treated as integrated.
Nothing has been published. Existing unrelated caches/builds remain untouched.

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
Confirm source split coverage and trial counts before integration: the complete
released member inventory is broader than common paper subset summaries.

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
inventing an equivalent meaning. Audit the complete corpus for other fields.

The author visualizer explicitly indexes bouts as `start:end`, establishing
**one-based inclusive** endpoints. Documentation names the third column
`certainty`; preserve it without inventing a confidence scale. Some action files
include explicit `unknown` intervals. Behaviors may overlap, so independent
binary behavior tracks per fly and released annotation slot are appropriate;
never impose an exclusive single class. A present behavior vocabulary permits
ordinary negative state0 outside bouts. An absent vocabulary or absent second
annotation file gives missing ground truth-1. Audit explicit unknown semantics
before finalizing the proposed masking of all behaviors on unknown intervals.
Second annotation files do not establish stable global annotator identities.
Keep every original bout (including certainty) in an auxiliary Parquet table.

## Storage stop and resumption

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

Resume only after the shared writer/storage change is resolved and sufficient
space is available. Run `df -B1 /` and `free -h`; one heavy job at a time. Measure
one complete pilot's native output, then require remaining complete source cache
+ measured full-output projection*1.25 + buffer +18GiB. The draft1GiB output
allowance is provisional, not an empirical gate. Reuse already CRC-checked files,
complete SHA pins and all-member schema/bout audit, verify independent exact
source parity, run full validator0 errors/0 warnings, update registry/README and
progress, then make one local dataset commit. Only after successful full build
and both validation gates may `raw/fly-vs-fly/` alone be deleted.
