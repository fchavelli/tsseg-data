# TCPD: mixed upstream rights and incomplete default signals

Verified 2026-10-18 at the primary TCPD repository, revision
`e8f19a3635e3b7f1a8aff59ce7f4d9bea17525c0`:
<https://github.com/alan-turing-institute/TCPD/blob/e8f19a3635e3b7f1a8aff59ce7f4d9bea17525c0/README.md>.

Its MIT licence covers repository code. The primary README explicitly says that
individual data files have different terms and that some are not redistributed
because of licensing restrictions. This is **tier C/source-only**, not a grant
to rehost the complete compilation. No upstream licence is inferred from the
code licence or the mere presence of a file in Git.

The builder retains a provenance inventory for all 37 measured series, including
the primary per-series README URL, its SHA256, its upstream attribution links,
and the availability and MD5/SHA256 of each included JSON. Curator claims cover
CC BY, CC0, CC BY-SA, GPL, MIT, government/public-domain and Eurostat terms;
others are unclear (e.g. Centralia). These are not a substitute for fresh
upstream rights review before rehosting. Original source attribution remains
required even for bundled signals. The card's custom licence is deliberately
not a purported new licence over upstream data.

## Local scope and reproducibility

The default build contains all **27 bundled measured JSONs**, with native MD5
checked against the primary `checksums.json`, itself SHA-pinned in the source
archive. Five fully generated `quality_control_*` inputs are excluded pursuant
to the user's collection policy.

Ten measured signals are not bundled: `apple`, `bee_waggle_6`, `bitcoin`,
`iceland_tourism`, `measles`, `occupancy`, `ratner_stock`, `robocalls`,
`scanline_126007`, `scanline_42049`. Their collector recipes remain in the pinned
primary repository, but are not executed by this builder. Some depend on mutable
Yahoo APIs, historic patches, or archived pages; reconstruction and current
access are not yet verified. The builder does not claim these signals failed to
download or are impossible to obtain.

`--extra-json-dir PATH` accepts independently obtained native JSONs only when
their exact bytes match primary TCPD MD5 values; their SHA256 is recorded in
provenance. `--require-complete` fails unless all 37 measured signals are present.
All measured expert annotations remain auxiliary even for pending signals.
Missing signals are never replaced with synthetic examples or unverified
third-party repackagings.
