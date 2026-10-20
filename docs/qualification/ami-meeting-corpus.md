# AMI Meeting Corpus: derived audio features qualification (2026-10-20)

Status: **deferred before any audio acquisition**. Primary rights, complete
headset-mix inventory and manual timing annotations were audited. No feature
extractor, dataset build, validator result or full audio SHA manifest exists.
No source audio or video has been downloaded. Nothing is published.

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
2026-10-20. The annotation release date is 2017-04-10; the manual annotation
content itself is unchanged since 2014-06-16.

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
is not proof of successful bounded audio range support: no audio GET/range was
performed. Primary documentation says audio is downsampled from 48 kHz to 16 kHz
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
transcriber_start/end. There are 168 meetings with four agents and **three with
five agents** (EN2001a, EN2001d, EN2001e); do not hard-code four speakers.
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
No audio-based alignment or endpoint audit has yet been possible.

Speaker overlap requires independent activity tracks per local agent (or a
fully reversible active-speaker set); it cannot be resolved by choosing one
speaker. Ordinary reviewed non-speech is a scored silence/absence state, not
missing ground truth. Missing roster agents, unreviewed intervals and invalid
source timing require distinct explicit handling. Word gaps alone do not prove
silence, especially around vocalizations and transcription errors. Meetings
from the same scenario day and recurring global participant IDs are correlated;
respect source meeting/session or documented participant partitions.

## Reproducible feature design to complete later

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

The unrelated `/home/fchavell/misc/ipcc-net/results.zip` continues growing and
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
must preserve all meetings and the selected audio context. No current builder
claims that such a workflow exists.
