# Registry

- `shortlist.yaml`: the evolving selection (currently 50 datasets), runners-up,
  exclusions and candidates awaiting label checks. About 50 datasets is a target,
  not a fixed limit. Fully generated corpora are excluded.
- `datasets/<id>.yaml`: source and licensing facts for selected datasets. Two
  previously selected synthetic entries remain here for decision traceability;
  they are absent from the shortlist and generated README table.

Both started as copies of the project's planning notes; builder integrations
update measured facts and primary-source licence checks here. Do not overwrite
these updates with `scripts/sync_registry.py`. Free-text fields are partly in French. The raw
per-domain inventories (about 370 entries and the search logs) are not copied.
