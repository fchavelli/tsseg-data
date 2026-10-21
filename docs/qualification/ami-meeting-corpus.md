# AMI Meeting Corpus: derived audio features qualification (2026-10-20–21)

Status: **complete171-meeting mixed-headset MFCC13 view, independently verified
and validated0 errors/0 warnings on2026-10-21**. The initial storage deferral and
resumptions below are historical audit checkpoints. Nothing is published.

## Primary sources and licence

- Corpus: <https://groups.inf.ed.ac.uk/ami/corpus/>
- Licence: <https://groups.inf.ed.ac.uk/ami/corpus/license.shtml>
- Download chooser: <https://groups.inf.ed.ac.uk/ami/download/>
- Audio format and common timeline: <https://groups.inf.ed.ac.uk/ami/corpus/signals.shtml>
- Transcription protocol: <https://groups.inf.ed.ac.uk/ami/corpus/transcription.shtml>
- Overview: <https://groups.inf.ed.ac.uk/ami/corpus/overview.shtml>

The current licence page explicitly applies CC BY 4.0 to the corpus and its
annotations. The download page also confirms public release of signals and
transcription under CC BY 4.0. This covers the selected audio and manual XML
release; derived features must identify the source and conversion. Verified
2026-10-20. The primary ZIP filename is ami_public_manual_1.6.2.zip, posted2017-04-10; its
internal README instead identifies release1.7 dated2014-06-16. This source
version discrepancy is retained explicitly; the immutable SHA identifies the
actual bytes used.

## Complete selected audio view and exact source size

Use the provider's single mixed-headset WAV for every meeting as the eventual
light diarization view. This is a provider-produced audio mix, not all original
microphone streams. Do not claim reconstruction or retention of the original
24-channel multimodal recording. Full multichannel audio would require a separate
explicit scope and larger storage gate.

The primary chooser produces **171 unique mix URLs**. HEAD requests for every
one succeeded, with a total Content-Length of **11,546,801,653 bytes** (10.754 GiB).
The chooser's rounded display says 10 GB. The exact per-file sizes and source
URLs are retained in `docs/qualification/ami-meeting-corpus-inventory.json`.
`scripts/qualify_ami.py --headers` reproduces this metadata-only inventory and
never downloads an audio body or executes generated source scripts.

Endpoint example:
<https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2002a/audio/ES2002a.Mix-Headset.wav>.
Its HEAD reports 40,724,524 bytes and Accept-Ranges: bytes. A HEAD advertisement
is not proof of successful bounded audio range support: no audio GET/range had
yet been performed at the initial metadata audit. Primary documentation says audio is downsampled from 48 kHz to 16 kHz
and shares a synchronized timeline. Actual WAV headers, channel counts, exact
sample lengths, full SHA256 and duration-to-annotation offsets remain unaudited.

## Manual timing coverage and alignment

The small primary manual archive was acquired for qualification only:
<https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip>.
It is 22,887,865 bytes, local SHA256
`b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d`.
It remains in `raw/ami-meeting-corpus/`; no source cache was removed.

The archive contains 687 speaker-specific segment XML files across exactly the
same 171 meetings as the audio manifest, with 93,637 segment elements. All have
transcriber_start/end. There are168 meetings with four segment files and three with five files. The
actual meeting roster is **five meetings with three agents,163 with four and
three with five** (EN2001a, EN2001d, EN2001e). Five absent D agents have empty
placeholder files in EN2002c,EN2003a,EN2009b,EN2009c,IN1001. Do not turn those
placeholders into scored negative tracks: the absent D track stays-1. All
93,637 real segments match roster participants; no participant is dropped.
`corpusResources/meetings.xml` maps local agents and microphone channels to
pseudonymous participants and supplies meeting/session context.

Two original segment intervals are reversed and must not be silently repaired:

| File | Original segment ID | Start | End |
|---|---|---:|---:|
| ES2011c.C.segments.xml | ES2011c.sync.496 | 78.122 | 78.001 |
| EN2005a.D.segments.xml | EN2005a.sync.1,118 | 91.472 | 90.461 |

The primary protocol describes human transcript passes and review of missed
speech. Its word and phoneme timestamps are subsequently obtained by **automatic
forced alignment**. Use original transcriber segment times for a segment-based
speaker-activity reference; do not describe all word boundaries as independently
manual annotations. Preserve original XML interval IDs and values, and document
any invalid intervals/unscored windows when designing the eventual mapping.
At the initial metadata-only checkpoint, no audio-based endpoint audit was yet possible. Final native endpoint findings are below.

Speaker overlap requires independent activity tracks per local agent (or a
fully reversible active-speaker set); it cannot be resolved by choosing one
speaker. The eventual binary background denotes no active selected transcriber interval,
not independently verified acoustic silence. Missing roster agents, unreviewed intervals and invalid
source timing require distinct explicit handling. Word gaps alone do not prove
silence, especially around vocalizations and transcription errors. Meetings
from the same scenario day and recurring global participant IDs are correlated;
respect source meeting/session or documented participant partitions.

## Initial feature design (2026-10-20)

A feasible initial extractor uses fixed MFCCs with no pretrained model:
16-kHz PCM converted to floating amplitude, specified pre-emphasis (or explicitly
none), 25-ms frames, 10-ms hop, an explicit window, FFT size, mel convention and
filter count, log-energy floor and DCT-II normalization, with 13 coefficients.
Every numerical choice, channel mixing rule, frame-center timestamp, padding and
last-frame rule must be frozen in code and the card. Delta/delta-delta features
would expand this to 39 channels and must be identified as deterministic derived
features, not raw recordings. Pin numpy/scipy versions; compare an independently
implemented extractor on native audio before accepting the full build.

At about 100 h, 13 float32 coefficients at a 10-ms hop alone require roughly
1.872 GB uncompressed; 39 coefficients require 5.616 GB. These are projections,
not measured Parquet sizes. A source-pinned one-meeting pilot and full-output
projection with 25% margin are required before any complete audio acquisition.
Do not select fewer meetings or coarse frame rates merely to bypass storage.
Avoid learned speaker embeddings unless a separately documented model and its
training-data, licence, revision and leakage implications are explicitly chosen.

## Storage gate and resumption

At the initial storage gate, unrelated `/home/fchavell/misc/ipcc-net/results.zip` was growing and
must not be modified by this project. Free space fell during this read-only
source audit despite only about 23 MB of local annotation data being added.
At the decisive check, free was **30,837,972,992 bytes** (28.72 GiB), leaving
**11,510,620,160 bytes** above the 18-GiB reserve. The complete audio cache alone
is **36,181,493 bytes larger than that headroom**, before manual annotations,
features, working memory/disk buffers or further external consumption.

Therefore no complete audio download or audio pilot was started. Restore a
stable adequate data volume or stop the unrelated growth through the user's own
action, recheck df/free, audit native WAV headers and all annotation endpoints,
then finish the deterministic extractor and measured pilot. Require full source
cache + measured output*1.25 + buffer +18 GiB, with continuous reserve monitoring.
A genuinely bounded source streaming design would need explicit validation and
must preserve all meetings and the selected audio context. No builder existed at that initial checkpoint.

## Resumption after storage restoration (2026-10-20)

The initial deferral above remains the historical audit. An unrelated storage
cleanup later restored about88.8GB free; this project did not change the unrelated
file. Its size/mtime remained17,982,922,246 bytes /1792513603 across repeated
checks, and df remained stable for more than ten minutes. The gate was therefore
re-evaluated, without reducing meeting count or feature rate.

Four complete native pilots were acquired and SHA-pinned: EN2001a (five agents),
EN2005a (reversed source segment), ES2002a and ES2011c (other reversed segment).
All are mono16-kHz signed16-bit uncompressed PCM. They total433,733,896 bytes and
1,355,420 feature frames. The fixed13-MFCC conversion produced61,578,618 bytes in
13.5 seconds. Complete-cache scaling with25% margin and64MiB buffer projects
2,116,280,299 bytes of output, before the separate18-GiB reserve.

The extractor is now explicit:400-sample symmetric Hamming windows with source
anchor offsets[-200,199], anchors0,160,320,... strictly before EOF; zero padding
only outside native boundaries. Decode int16/32768 in float64; no pre-emphasis,
CMVN, learned model or speaker embedding. FFT512, power abs(FFT)^2/512,40 equally
spaced2595log10(1+Hz/700) mel triangles from0 to8kHz, evaluated continuously on FFT
frequencies without area normalization; natural log floor1e-10, orthonormal DCT-II,
coefficients0..12, float32 output. Output100Hz with exact10-ms anchor timestamps.
Only1000 feature frames and their native PCM context are processed per batch;
no full waveform is loaded or copied to temporary disk.

Independent pilot reconstruction uses numpy FFT, an analytic Hamming expression,
a separately built mel bank and an explicit cosine DCT matrix, in different
777-frame batches. All4/4 source/label/clock/segment comparisons pass; maximum
MFCC absolute difference is5.96046448e-8 (acceptance bound3e-5). The2 original
reversed timing spans are retained and conservatively unscored for their local
speaker; overlapping valid speakers remain independent. Original decimal interval
strings and IDs are preserved, not repaired or replaced with forced-aligned words.

The complete171-meeting acquisition was started as **one** transfer job with
at most four independent bounded streams. Every one-MiB block checks the18-GiB
reserve; byte count is capped by primary HEAD size. Each completed WAV is checked
as native PCM, SHA256-pinned and added to an atomic restart manifest. Source files
and partial checkpoints live only under `raw/ami-meeting-corpus/`. Acquisition,
feature conversion and full validation must remain sequential heavy jobs.
Observed individual transfers around0.8–1.3MB/s imply roughly3.5h serial download;
four streams may reduce wall time to50–90min if aggregate bandwidth scales.
No audio source is deleted before full build and both validation gates succeed.

Checkpoint artifacts: `raw/ami-meeting-corpus/audio-pins.json`,
`raw/ami-full-acquisition.log`, `raw/ami-pilot-build.log`,
`raw/ami-pilot-reconstruction.log`, `build/ami-pilot-work/ami-meeting-corpus/`.
At that resumption checkpoint the builder, helper and checker remained provisional
until complete acquisition and both validation gates. It did not yet establish
a complete build or full source-parity result; final evidence follows below.


### Native channel audit and fixed downmix

Before resuming audio transfer after a conservative mono assertion stopped the
job, all171 native headers were audited:55 local WAVs and116 primary256-byte
HTTP ranges, each requiring status206, exact Content-Range and exact body size.
All sources are16kHz signed16-bit uncompressed PCM.170 files are mono;
`ES2010d.Mix-Headset.wav` alone has two native channels. Source byte counts and
SHA pins cover the untouched WAV, and `source_audio_channels` retains the native
count in each index row. It must not be described as a native mono file.

On a bounded first30-second block of ES2010d (480,000 native frames), both
channels are sample-for-sample identical: maximum difference0, correlation1,
RMS219.9574647469748 and peak absolute6984 in each channel. This is a limited
probe, not a claim about unexamined samples. The fixed extraction rule for all
sources is to decode int16 to float64 by dividing by32768, then average native
channels arithmetically before windowing/FFT. No resampling or fitted clock
correction is performed. The independent verifier uses an explicit channel sum
and division, separate FFT/window/mel/DCT calculations, and checks the retained
native channel count against every WAV header.

RIFF size is not a proxy for source sample count: 29 WAVs contain trailing
cue/LIST/muma/chrp/bext metadata after their PCM block. Frame clocks use the WAV
PCM frame count exclusively. A bounded RIFF chunk audit records chunk tags,
declared RIFF bytes, PCM data bytes and bytes after PCM; metadata text is neither
interpreted as audio nor exported. Full-file hashes bind the original metadata
as well as PCM. Source transcripts, participant names and absolute recording
dates are excluded from the derived dataset.


### Released partitions

The [primary partition page](https://groups.inf.ed.ac.uk/ami/corpus/datasets.shtml)
provides three distinct variants: scenario-only, full-corpus and full-corpus-ASR.
Do not collapse these names. The SHA-pinned manual release XML supplies native
`visibility`, `seen_type`, `k5` and `k10` only for138 scenario meetings:98training,
20development and20unseen evaluation. All33 other meetings retain null XML
partition attributes in the derived index. The builder copies literal attributes
and the independent verifier compares them directly to the original XML.

The full-corpus web listing expressly excludes IB4005 because its participants
span multiple sets; IN1015 is not assigned in that listing either. We do not
guess assignments or claim the XML provides a full-corpus person-disjoint split.
Use an explicitly identified primary variant or a separately justified grouping.
The index preserves session groups while withholding global participant names
and encoded demographic IDs. Local speaker A in different meetings does not
identify the same individual.


### Source integrity convention

The provider publishes direct WAVs and a versioned manual ZIP, but no independent
provider audio digest was supplied by the chooser/HEAD inventory. Native audio
SHA256 pins are therefore computed on the first size-checked primary download,
not presented as provider checksums. The committed manifest binds complete source
bytes, PCM properties, RIFF layout and the manual release hash. Subsequent fresh
builds require exact size and SHA agreement before feature extraction; they
never silently accept a newly changed source under the same URL.


### Annotation package discrepancy and additional native fields

The ZIP internal README names release1.7 dated16June2014 despite the primary
filename1.6.2 and2017 posting date. Its known-issues text reports incomplete or
incorrect propagated timing for TS3009c channel3, EN2002a/c and EN2003a. These
notes concern timing propagation from forced alignment; they do not establish
that every selected manual transcriber interval has been independently checked.
We retain that limitation and do not infer repairs or remove complete meetings.
All93,637 segment channel values are preserved. The51 optional native starttime
and endtime pairs are retained as literal strings alongside transcriber times,
with no substitution into the activity reference. Dropped source meetings
IS1002a and IS1005d are absent from the complete primary171-meeting inventory
because the provider reports serious audio issues; no synthetic replacements.


### Robust transfer restart (2026-10-21)

An initial full-file curl transfer stopped with code18 (connection closed before
all declared bytes arrived). No incomplete WAV was promoted or SHA-pinned. The
remaining acquisition now uses at most four concurrent streams of32-MiB bounded
HTTP ranges. Each range requires final206 status, exact Content-Range including
complete source size, exact body length and a stable ETag; If-Range rejects a
changed source. Retry up to five times with bounded time/backoff, never append
a failed/truncated response. Native partial files have an HTTP identity sidecar
and can resume from their current validated prefix. Historical partials lacking
that identity restart only that WAV from byte0. Full-WAV SHA is computed after
all ranges, checked against an existing pin when present, then promoted and
checkpointed atomically. Reserve guards apply before each range and each MiB
written. Bounded response bodies stay in memory, not /tmp or duplicate raw files.

The corpus ZIP itself includes LICENCE.txt explicitly applying CC BY4.0 to the
corpus and annotations, consistent with the current primary web licence.


Complete RIFF audit after acquisition:142 WAVs have only fmt/data chunks;
25 have cue/LIST/LIST/muma/chrp/bext after data, three have cue/LIST/LIST and
one has cue/LIST. Thus29 contain trailing non-PCM metadata, including the25
odd-total-length IS files that first exposed the issue. All clocks are based
on the decoded PCM frame count, independently checked against PCM chunk bytes.
The complete source contains5,757,872,100 PCM frames (99.9630573h) and generates
35,986,766 feature anchors at100Hz without any resampling.


## Complete build and final gates (2026-10-21)

All171 primary selected mixed-headset WAVs were acquired intact and SHA-pinned:
11,546,801,653 bytes, plus the22,887,865-byte manual ZIP. The deterministic
conversion contains **35,986,766 MFCC13 frames at100Hz**, representing
99.9630573h of native PCM. Length min/median/max is47,788/213,590/541,524 frames.
All687 source segment files are audited against primary rosters, including five
empty absent-D placeholders; all93,637 original segment rows remain in the
auxiliary Parquet with literal IDs, channels, transcriber and optional timing
strings. No waveform, word text, participant name, encoded demographic ID,
absolute date or video is packaged.

Final source endpoint audit finds **seven defective intervals**: the two reversed
rows listed above and five TS3007c rows extending beyond the native WAV endpoint.
TS3007c PCM lasts exactly2420s, whereas meetings.xml says2430s and selected
segments reach2430.2s. Four intervals lie wholly outside observable audio; the
partly covered C interval2413.698–2422.692 masks630 observable feature centers.
No offset, repaired segment, invented waveform or extra feature frame is added.
The reversed intervals mask12 C and101 D centers. All other valid segments are
retained; uncertain masks override positives only on their own local track.

Five independent local tracks preserve **5,921,694 multi-active feature centers**
(16.4551991%); this measures overlapping selected segment times, not a fresh
acoustic overlap annotation. Positive recurrence exists for A/B/C in171meetings,
D in166 and E in3. Missing cells are A0/B0/C642/D1,425,158/E34,700,129, dominated
by genuinely absent roster agents. Background0 means no selected interval,
not independently confirmed silence. Native XML partition values remain literal
and nullable, without fabricated full-corpus or ASR assignments.

Full independent reconstruction passed171/171 meetings: every native source SHA,
PCM length/channel count, original segment field, roster, partition, feature
anchor and speaker label agrees. Separate NumPy FFT, analytic Hamming, independently
constructed mel filters and explicit cosine DCT reproduce every MFCC frame with
maximum absolute difference **4.76837158e-7**, below the fixed3e-5 tolerance.
Floating features are numerically verified, not claimed bit-for-bit identical.
Croissant and full structural validation pass **0 errors/0 warnings**,12 hashed
files and7 Parquet parts. Final output is **1,633,817,064 bytes**, below the
measured pilot projection including25% margin and64MiB buffer (2,116,280,299B).

Evidence logs remain outside the removable source cache:
`raw/ami-full-acquisition-20261021.log`, `raw/ami-full-build.log`,
`raw/ami-full-validation.log`, `raw/ami-full-reconstruction.log`.
The source manifest is `builders/checksums/ami-meeting-corpus.json`.
The old failed full-file transfer log and pilot logs also remain. Only the
AMI raw source directory may be removed after these successful gates; other
caches, pilot artifacts and unrelated files must remain untouched.


Targeted cleanup completed after both gates: only `raw/ami-meeting-corpus`
was removed, 275 files / 11,569,996,696 bytes.
Free space before/after was 59,678,584,832 /
71,249,760,256 bytes. Other source caches, the AMI pilot output,
validator samples, logs and unrelated files remain. The source manifest and
normal builder can reconstruct the complete view. No publication or remote
operation was performed.
