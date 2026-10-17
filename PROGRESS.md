# Progress

Resume point of the repository set-up (started 2026-10-18 from the pilot in
`tsseg/notes/datasets/pilot/`). Nothing is pushed or published; no remote.

## Done

- [x] 1. Skeleton: `pyproject.toml`, MIT `LICENSE`, `.gitignore` (`build/`, `raw/`,
  `.venv/`), `tsseg_data/` (sources, format writer, Croissant, labels, reader,
  build steps), `cards/` templates, `registry/` (shortlist + 50 retained entries,
  `scripts/sync_registry.py`).

## To do

- [ ] 2. Builders ported to format 1.0: mozilla-perf-cpd-annotations, opportunity,
  dreem-dod-h; built in `build/`.
- [ ] 3. `scripts/validate.py` (mlcroissant, Parquet schema, CP/label coherence);
  all three valid.
- [ ] 4. README (collection, one line per dataset), CONTRIBUTING.
- [ ] 5. `docs/NEURIPS_CHECKLIST.md`.
