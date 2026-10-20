# AnDy compact views and HA4M source audit

Checked 2026-10-20. No complete motion archive or HA4M corpus was downloaded.
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

## HA4M: selective primary access established

Primary sources:

- [Author repository](https://baltig.cnr.it/ISP/ha4m), revision
  `cc0b49cbf0bb39f63b368c5c4f10d0c27a6a452e`; README and LICENSE confirm CC BY 4.0.
- [Source paper](https://doi.org/10.1038/s41597-022-01843-z).
- [Author-linked ownCloud share](https://cloud.cnr.it/owncloud/index.php/s/j5BZvG1sXPzh6x1).
- [ScienceDB original-paper deposit](https://doi.org/10.57760/sciencedb.01872).

The ownCloud share supports public read-only WebDAV at
`https://cloud.cnr.it/owncloud/public.php/webdav/`, using the public share token
as the Basic-auth username with an empty password. This is public-link access,
not an account or a DUA. Depth-1 PROPFIND returned **217 trial folders**. Reading
all trial directory metadata found both `Skeletons` and `Labels.txt` in every
trial: **2,740,949,486 skeleton bytes**, **6,405,585 label bytes**. Entire-share
size is 4,584,482,309,887 bytes; the skeletons can be requested independently.
The live share is a growing source; reconcile trial IDs with the fixed paper
release before finalizing corpus scope and pins.

A bounded first-trial inspection (`IDU001V001`) found 2,427 skeleton TXT files
under camera `000124702712`, totaling 10,397,384 bytes, and 24,053 label bytes.
One 4,274-byte native skeleton file has 32 joint rows and these 14 columns:
`BodyID JointID Confidance X Y Z Qw Qx Qy Qz X2DColor Y2DColor X2DDepth Y2DDepth`.
Thus XYZ-only gives 96 coordinates, while preserving all numeric observations
requires **384 channels** (32 × 12, including confidence, quaternion and 2D
projections); body/joint IDs belong in structural metadata. Confirm body counts,
units, confidence coding, and missing detections before a complete builder.

Frame filenames carry both IDs and IR-device microsecond times. In this pilot,
frames 0 and 1 have the same timestamp `450817733`; the last frame is 2426 at
`531451066`. Preserve frame IDs and actual times; do not assert a strictly
increasing exact 30-Hz clock. Labels begin at frame 0, with source codes 0–12
and an action repetition index. Use frame-ID joins, audit missing skeleton files
and RGB-versus-IR alignment; never compress away missing detections. The two
researchers checking annotations do not constitute two released label tracks.
The primary README describes 4,123 annotated actions, correcting the registry's
unverified 4,124 claim. The semantics of ordinary don't-care 0 require an explicit
primary evaluation check before deciding whether it maps to -1.

The uncompressed skeleton cache alone uses 2.55 GiB, so a complete cache plus
Parquet cannot be assumed to fit the current headroom. Next: test a **bounded
single-trial compressed Skeletons download**, verify all file names/counts,
labels and native columns, measure Parquet size and acquisition cost, then apply
`free - source_cache - output*1.25 - working_overhead >= 18 GiB`. If this fails,
qualify per-trial streaming with pinned inputs before a heavy job. No imagery,
full trial archive, or multi-trial skeleton corpus has been downloaded.
