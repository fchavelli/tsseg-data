# Honey bee dance: source-only rights and reference labels

Verified 2026-10-18 at the primary Georgia Tech author site:
<https://sites.cc.gatech.edu/~borg/ijcv_psslds/> and its
[instruction manual](https://sites.cc.gatech.edu/~borg/ijcv_psslds/instruction.pdf).
The page requests citation, but neither it nor the inspected manual/archive
provides a redistribution licence. Classification: **tier C/source-only**.
Public availability and downstream BSD/MIT wrappers do not change these rights.

Only the original 3.6-MB source archive is required:
<https://sites.cc.gatech.edu/~borg/ijcv_psslds/psslds.zip>.
SHA256 `9b1277fd38026570ecee6c5a5602439b0aae1264185abf41311ad6646387ccb0`;
MD5 `039843dc15c72fd5450eeb11c6e5599c` also matches the pinned primary TCPD
collector's expected source archive. Included executables are never run.

## Ground truth and clock

Manual section 4 identifies each `sequenceN/btf/label0.btf` as reference labels,
distinguishing these from inferred label files. Only this field is scored.
The `label1.btf` files in sequences 1/2 have no documented purpose or annotator;
they remain auxiliary, without a second-expert or consensus claim. Source model
outputs are not treated as human annotations.

The timestamp field advances by 33 units in every sequence. Units and exact
physical frame rate were not established by the inspected source documentation.
The builder retains the integer timestamp and leaves physical sampling rate
unspecified; the registry's former 30-Hz assertion was not verified. Native
framestamps, where available, remain auxiliary. The archive HTTP Last-Modified
date (2009-03-06) is distinguished from the original paper date (May 2008).

Sequence 6 is also used by TCPD as `bee_waggle_6`, with independent boundary
annotations and a different heading feature representation. These are not
independent measurements and must not be placed in separate evaluation folds.
