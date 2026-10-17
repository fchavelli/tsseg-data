# Registry

- `shortlist.yaml`: the 50 datasets selected in phase 2 (plus runners-up), with
  domain, task, license tier and the reason for selection.
- `datasets/<id>.yaml`: the phase-1 inventory entry of each selected dataset
  (source, DOI, license and where it was verified, size, label origin, notes).

Both are verbatim copies of the project's planning notes (refreshed with
`scripts/sync_registry.py`); free-text fields are partly in French. The raw
per-domain inventories (about 370 entries and the search logs) are not copied.
