# AnDy compact views and HA4M source audit

Checked 2026-10-20. AnDy remains deferred. The HA4M follow-up below supersedes
the initial access-only audit.
The 18-GiB free-space reserve remains mandatory. Small source pilots remain in
`raw/andy-lab-oneperson/` and `raw/ha4m/`; these are qualification evidence,
not validated dataset builds. No cache was deleted.

## AnDy: alignment evidence and complete view scope

Primary sources:

- [Zenodo v2](https://zenodo.org/records/3254403), DOI
  `10.5281/zenodo.3254403`, CC BY 4.0 in its metadata.
- [Author paper](https://hal.science/hal-02289107/document),
  *Human Movement and Ergonomics: an Industry-Oriented Dataset for Collaborative
  Robotics*, DOI `10.1177/0278364919882089`, sections 2.3–3.1.

The paper establishes 240-Hz Xsens acquisition, annotations on 24-fps avatar
videos, and matching starts and ends for those videos and Xsens recordings.
Annotation CSVs contain both video-relative and Unix times. Physical camera
videos have no automatic sensor synchronization and must not supply the clock.
The three annotation columns per semantic track are independent judgments within
a trial. The paper says each trial's three annotators were drawn from four people:
`Annotator1` must not be treated as one stable person across all 195 trials.

The compact exports are distinct native representations, not equivalents of all
Xsens CSV measurements:

| View | Complete trial members | Native scope inspected | Archive bytes |
|---|---:|---|---:|
| BVH | 195 | 72 columns: root XYZ plus root/joint Euler rotations; all CHANNELS declarations retained | 1,808,149,444 |
| C3D | 195 | 64 model-derived anatomical points, XYZ (192 coordinates), millimetres; no analog channels | 1,379,554,812 |
| Labels CSV | 195 matching trials | general posture, detailed posture, current action; three annotator slots each | 4,074,552 |

A full bounded BVH member was read for
`Participant_9875_Setup_B_Seq_4_Trial_5`: 26,687 rows, 72 columns,
`Frame Time: 0.004167`. Its matching C3D header independently reports 26,687
frames at exactly 240 Hz. BVH's decimal frame time is rounded; it must not silently
replace the source's documented native clock with a new sampling rate.
The label file contains 2,670 video frames: its tail extends 13 native sample
intervals beyond the motion duration. For
`Participant_909_Setup_A_Seq_5_Trial_5`, BVH/C3D both have 30,240 motion frames
and the labels have 3,024 frames. Thus an unconditional `repeat(labels, 10)`
is not a valid complete-series converter. A future builder can use the
paper-established common origin and half-open video-frame intervals, preserve
all source video labels separately, and report trailing coverage discrepancies
per trial. It must audit all trials, without stretching labels or optimizing an
offset against signal content. An attempted all-C3D-header range audit stopped
on a response contract failure after more than 125 headers; it did not produce
a complete validated manifest. Only the two matched trials above are relied on.

The fully decoded C3D pilot is the second trial above: little-endian int16,
scale `0.0742809921503067`, first frame 1, last frame 30,240, 64 points, data
block 11, all residual/camera fields zero. These are avatar landmark coordinates,
not physical Qualisys markers, raw IMUs, or the 23 segment position channels.
BVH retains Euler values and skeleton offsets directly; a future builder must
preserve every hierarchy/offset and rotation order, with no forward kinematics
or unsupported physical unit conversion.

The full 4-MB label ZIP was downloaded and matched primary size/MD5; its SHA256
is `9e34eae460835b83c79b93282de7f672d321f40fd4dd9c258d32fec47a3c9a46`.
Single motion members were fetched with exact HTTP Content-Range checks, bounded
reads, DEFLATE length and CRC checks. No archive was extracted on disk.

## AnDy: failed storage gate

Pilots cast all motion columns to float32 and write a one-row Parquet using zstd
level 9 and byte-stream-split encoding. Each complete selected view is projected
using its archive-directory total uncompressed bytes. These are estimates from
one trial per view, not guarantees. Estimates exclude label overhead; adding it
can only worsen the failed gate.

| View | Pilot source bytes | Pilot Parquet bytes | Total uncompressed source bytes | Projected output bytes | Output with 25% margin |
|---|---:|---:|---:|---:|---:|
| BVH | 18,752,778 | 4,899,333 | 4,279,156,916 | 1,117,968,479 | 1,397,460,598 |
| C3D | 15,488,512 | 8,483,720 | 3,109,578,240 | 1,703,248,905 | 2,129,061,131 |

At the C3D gate, free space was 22,481,264,640 bytes (20.94 GiB).
Subtracting the complete source archive, projected output with margin, and
64 MiB working overhead leaves **17.89 GiB for BVH** or **17.61 GiB for C3D**.
Both are below 18 GiB. Even before label/metadata overhead or between-trial
compression variation, neither complete cached workflow is authorized by the
storage gate. No full archive or partial dataset build was started.

Resume with a larger volume, or separately validate a bounded source-streaming
workflow with complete provenance pins and no omission of channels/trials.
Recheck free space and RAM immediately before any download. A larger pilot is
required before interpreting the small numeric gap as a safe capacity target.
Do not delete existing builds or unrelated caches to make room.

## HA4M: complete native skeleton conversion

Primary sources checked 2026-10-20:

- [Author repository](https://baltig.cnr.it/ISP/ha4m), revision
  `cc0b49cbf0bb39f63b368c5c4f10d0c27a6a452e`; README and LICENSE grant CC BY 4.0.
- [Primary data paper](https://doi.org/10.1038/s41597-022-01843-z) and
  [ScienceDB DOI](https://doi.org/10.57760/sciencedb.01872).
- [Author-linked original-data share](https://cloud.cnr.it/owncloud/index.php/s/j5BZvG1sXPzh6x1).
- [Later author feature repository](https://github.com/ispstiima/HA4Mfeatures),
  used solely as trial39 association evidence, as explained below.

The original public share exposes 217 trials from 41 numbered subjects, matching
the original paper, with independent Skeletons and Labels.txt access via public
WebDAV. All trial directory sizes were inspected before acquisition:
2,740,949,486 native skeleton TXT bytes plus 6,405,585 label bytes. No images,
point clouds, full multimodal trial archive, demographic table, or source
feature array was downloaded. The entire multimodal share is about 4.58 TB;
only the complete original skeleton/annotation view is selected.

### Published scope and clocks

All 217 trials are retained: 642,268 frame positions, lengths 997 / 2,900 / 7,262
(minimum / median / maximum). A single complete main config stores 384 native
observations (32 joints × confidence, XYZ, quaternion WXYZ, color XY and depth
XY); duplicating a reduced config would consume the storage reserve. Native
`Confidance` spelling is retained in channel names. XYZ units are mm; projections
are pixels; confidence and quaternion components are dimensionless. Preserve
zeros, predicted/occluded joints and native values, with one float32 cast and
no filtering, centering, coordinate conversion or quaternion normalization.

The frame grid is nominally 30 fps, indexed by original frame IDs. Actual
IR-device microsecond timestamps are in source_frames.parquet, with 1,469
repeated timestamps and no reversals. Do not substitute an exact increasing
clock for those native counters. Missing detections are not compressed away.
The primary paper describes RGB-to-IR delay as much smaller on average than a
frame and verifies annotation using wrist trajectories; this supports frame-ID
joins, not exact sub-frame physical onset claims. No wall-clock dates are used.

All 639,590 published 32-joint blocks are represented exactly once: 639,517 main
poses plus 73 auxiliary blocks. The main view has 2,751 unavailable-pose frames:
2,697 have no native skeleton file, 50 have only an invalid SDK ID, and four
have multiple valid-ID blocks. Their frame annotations remain known. Every
published pose estimate is retained; unobservability in main is structural NaN,
not a change to annotation ground truth.

### Body IDs and complete numeric reconstruction

Some source TXT files contain multiple 32-row blocks. The
[official SDK 1.1.x definition](https://microsoft.github.io/Azure-Kinect-Body-Tracking/release/1.1.x/k4abttypes_8h_source.html)
identifies 0xFFFFFFFF as the invalid body-ID sentinel; its
[accessor contract](https://microsoft.github.io/Azure-Kinect-Body-Tracking/release/1.1.x/group__btfunctions_ga1d612404d133a279af847974e9359a92.html)
uses that value for failed lookups. The
[author's exporter](https://gitlab.com/roberto.marani/multiple-azure-kinect-gui/-/blob/main/AzureKinectGUI/AzureKinect.cpp)
can assign an invalid ID from joint/body-map lookup and exports every block.
Its current code helps interpret the sentinel but is not asserted to be the
exact historical acquisition binary. Invalid-ID blocks contain nonzero poses;
never discard them or treat their values as zeros.

The main 384 channels contain a pose only when exactly one valid-ID block exists.
All invalid-ID blocks, and every block on an ambiguous multi-valid frame, are
stored in unassigned_skeletons.parquet with original frame, full unsigned BodyID,
original block index, explicit reason, and all 384 observations. There are 65
invalid-ID blocks plus eight valid blocks from four ambiguous frames. Ordinary
unique-valid blocks are not duplicated. No actor is chosen from order, size,
coverage or agreement with action labels; valid IDs do not establish physical
identity or cross-ID continuity. Actions label source frames/trials, not bodies.

To reconstruct native numerical blocks, take all auxiliary blocks at their
original indices. When main has a valid BodyID, insert its 32 joint rows at the
sole unused block index. If main is NaN, every native block is already auxiliary.
Frames with no skeleton file have neither. This preserves every published
observation and block order after the documented float32 cast, while avoiding
whole-corpus pose duplication. Literal source bytes remain SHA256-bound.

### Trial39 association evidence and original labels

Original IDU039V001 has 2,284 skeleton frames but 3,474 annotation rows;
IDU039V002 has 3,474 skeleton frames but 2,284 annotation rows. Lengths alone do
not justify a swap. The later primary-author repository links a public feature
share whose groundTruth/IDU039V001.txt contains 2,284 actions, exactly identical
at every row to original IDU039V002 Labels.txt; the later V002 GT contains 3,474
actions, exactly identical to original V001 Labels.txt. Later source feature
file sizes also agree with the corresponding original native frame counts.
Both evidence URLs were downloaded independently and checked against their pins:

| Author evidence | Bytes | SHA256 |
|---|---:|---|
| IDU039V001 | 5,586 | `2dd69280e96f68842ad63488ac6063b5e30a71b0e4f0a535cc7e73d08303a9b8` |
| IDU039V002 | 7,712 | `5be64e1fa49850d026c9521c92d9abce0fcb83f09cf252b903ea2cd6f3b8a7ea` |

The default therefore uses the author-supported reversed association of the two
**original CC-BY CSVs**, including their original action/repetition row tuples.
This is a documented derived association, not an author-issued erratum or an
offset fitted to motion. source_label_trial records the original annotation
file used. Every original declared trial/frame/action/repetition row is retained
unchanged in original_labels.parquet; source_frames.parquet gives the associated
annotations on the canonical native grid. No original annotation is dropped.

The feature repository has no LICENSE and its GitHub licence endpoint returns
404. Its GT files are pinned evidence only: no grant is assumed, and neither
file nor any feature data is packaged or rehosted in the build. Converted labels
come exclusively from the original licensed annotations. No additional
annotator or consensus is invented.

### Annotation semantics and recurrence

One manual reference is released, cross-checked by two researchers. Source 0
means annotated transitions or unexpected events, such as losing a component;
it stays an ordinary scored null state. The paper excludes it from descriptive
assembly analysis only; masked evaluation can be a sensitivity analysis.
All 13 source action codes remain scored, with no missing default labels after
the documented trial39 association. Original repetition index 0–2 is a separate
source attribute, not a new rater or semantic state taxonomy.

Semantic action-class runs total 3,224. **Recurrence including null 0 is 204/217;
recurrence of substantive action classes 1–12 is 49/217.** Consecutive repetitions
of one action can share a class and therefore do not constitute semantic state
changes. Joint action/repetition runs total 4,124, including 435 null instances,
matching the paper; the repository README's 4,123 count differs by one. Every
trial has the expected three executions of actions 2/3 and two of action 11 in
this source attribute representation. Native repetition boundaries remain
available even when the main semantic action label does not change.

### Storage qualification and reproducibility

One first/smallest/largest trial pilot covers both cameras:

| Trial | Frames | Native TXT bytes | Lossless gzip ZIP bytes | Main Parquet bytes |
|---|---:|---:|---:|---:|
| IDU001V001 | 2,427 | 10,397,384 | 4,248,655 | 2,562,446 |
| IDU034V006 | 997 | 4,268,903 | 1,783,952 | 1,169,858 |
| IDU017V003 | 7,262 | 31,147,197 | 12,695,894 | 7,125,649 |

ownCloud generates ZIPs without useful compression. Each bounded per-trial ZIP
is read in memory, CRC/schema/size checked, then stored losslessly as gzip;
there is no second full on-disk archive. The complete gzip cache totals
1,117,172,096 bytes. SHA256 covers sorted native UTF-8 member names, uint32-LE
name-length prefixes, uint64-LE byte-length prefixes and original member bytes;
ZIP dates/order/compression are excluded from this content contract. Every
literal Labels.txt has its own SHA256. A mutation test changes the digest,
whereas repacking the same files preserves it. All 217 source pairs and the two
small non-rehosted evidence files are pinned in builders/checksums/ha4m.json.

The full-cache/output gate uses a 0.45 cache ratio floor and the worst measured
output ratio (about 0.274), with 25% margins on both and 96 MiB overhead. Initial
projected free was 18.494 GiB. Affected multi-body pilots including auxiliary
output measured 0.2385–0.2495, below the same conservative floor. One qualifier
process used at most four bounded requests, checkpointing each trial; every
batch rechecked the complete remaining-cache/output projection. Build measured
minimum free 19.268 GiB, projected minimum 18.873 GiB, above the 18-GiB reserve.
Final output is about 624 MB in three main shards plus typed auxiliary tables.

Reproduce from committed pins with `python -I builders/ha4m.py`. Validate with
`scripts/validate.py` using the existing pilot environment containing mlcroissant.
Before deleting the raw cache, run `python -I scripts/verify_ha4m.py`: it checks
every source label, repetition, original annotation, main/auxiliary numerical
block, BodyID/index and native timestamp independently of the builder decoder,
including both corrected action vectors against pinned primary-author evidence.
Current gate status and cleanup/commit are recorded in PROGRESS.md and HANDOFF.
