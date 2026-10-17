# TSSB licence scope review — 2026-10-18

Status: **source-only; do not redistribute the converted signals yet**.

The primary [TSSB repository licence](https://github.com/ermshaua/time-series-segmentation-benchmark/blob/e0c7a1f6cee6874e60cbacd3b8601f2de259606e/LICENSE)
is BSD-3-Clause, copyright Arik Ermshaus (2021). The archive at this revision
contains the licence and 75 derived series. Its README explicitly attributes
those series to UCR/UEA classification datasets, grouped by class, concatenated,
normalised and resampled. This establishes the repository's stated licence but
does not independently establish redistribution rights for every upstream source.

The primary [UCR archive page](https://www.cs.ucr.edu/~eamonn/time_series_data_2018/)
and [UEA collection page](https://www.timeseriesclassification.com/dataset.php)
were checked on 2026-10-18. They provide downloads, usage information and citation
requests; no blanket licence covering these 75 underlying datasets was found
there. Absence of a licence on these pages does not prove that each original
dataset lacks one. A source-by-source check or rights clarification is required
before redistribution of the converted collection.

Consequently the registry marks TSSB tier C pending clarification, despite its
repository BSD declaration. The builder fetches the primary TSSB archive and
creates a local build with the scope restriction in its card, loader metadata
and Croissant. It makes no claim that BSD automatically relicenses upstream data.
No third-party repackage is used as evidence of upstream rights.
