# Card template: what each builder must provide

`cards/dataset_card.md.tmpl` is filled by `tsseg_data.build.finalize`. The
structural sections (configs, columns, conventions) are generated from the files;
the builder provides the rest in its `card` dict and in `DatasetMetadata.rai`.

| Key | Content | Rule |
|---|---|---|
| `pretty_name` | Name of the source dataset | as the authors write it |
| `hf_license` | Hugging Face license id (`cc-by-4.0`, `mit`, `other`...) | `other` + `license_name`/`license_link` if not in the HF list |
| `tags` | `time-series`, `change-point-detection` and/or `state-detection`, domain tags | always include `tsseg` |
| `size_category` | `n<1K`, `1K<n<10K`... (number of series) | |
| `annotations_creators` | `expert-generated`, `crowdsourced`, `machine-generated`, `found` | |
| `summary` | 2-4 sentences: what is measured, how labelled, why useful for CPD/SD | |
| `facts` | Markdown table: task, domain, series, lengths, channels, sampling, label type, states, annotators, unlabeled share, license, source DOI | numbers computed by the builder |
| `labels` | State names per label column, `null_states`, default ground truth, change types | |
| `annotation` | Origin (`protocol`, `human`, `derived`, `concatenation`, `simulated`), known guidelines, quality control, **inter-annotator agreement computed by the builder** (or why none) | |
| `conversion` | What was changed (renaming, re-indexing, alignment, cuts), what was not (values), source files with checksums, command to rebuild | |
| `license` | Dataset license, attribution, NC/SA restrictions, license of the code | verified at the primary source |
| `citation` | BibTeX of the source paper(s) and dataset DOI | |

RAI texts (`DatasetMetadata.rai`) are reused in the card's "Responsible use"
section. Required for NeurIPS: `dataLimitations`, `dataBiases`,
`personalSensitiveInformation`, `dataUseCases`, `dataSocialImpact`,
`hasSyntheticData`, plus `prov:wasDerivedFrom` (primary source with DOI) and
`prov:wasGeneratedBy` (collection, annotation and our preprocessing activities).
