# Contributing

## Adding a dataset

1. The dataset must be in `registry/shortlist.yaml` (selection is discussed
   first). Check its license at the primary source and note it in the registry.
2. Write `builders/<id>.py` from an existing builder (`opportunity.py` for dense
   states, `mozilla-perf-cpd-annotations.py` for annotated change points,
   `dreem-dod-h.py` for several annotators, long series or remote zips):
   - fetch every source file with `tsseg_data.sources.fetch` and a pinned sha256
     (or `RemoteZip` + CRC32 for members of large archives); put long checksum
     lists in `builders/checksums/<id>.json`;
   - declare the columns with `DatasetSpec` and write with `DatasetWriter`; never
     change signal values beyond a lossless cast, and document every renaming,
     re-indexing, alignment or cut;
   - use `-1` only where no ground truth exists; keep null / other classes as
     states and list them in `null_states`;
   - compute the inter-annotator agreement when there are several annotators;
   - fill `DatasetMetadata` (all RAI fields, `derived_from` with the DOI of the
     primary source, the three `Activity` entries) and the card dict
     (`cards/TEMPLATE.md`), then call `finalize`.
3. Build with `python -I builders/<id>.py` and run `python -I scripts/validate.py
   build/<id>`; it must pass without error.
4. Update `STATUS` in `scripts/collection_table.py`, run it, and update
   `docs/NEURIPS_CHECKLIST.md`.

## Conventions

- Code, docs and commits in English; Conventional Commits (`feat:`, `fix:`,
  `docs:`, `chore:`...).
- Python >= 3.10, `ruff` (line length 88).
- Never commit `build/`, `raw/` or any data file.
