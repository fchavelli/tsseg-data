# tsseg-data

Builders, metadata and checks for a collection of open, labelled time series
datasets for **change point detection (CPD)** and **state detection (SD)**, used
by [tsseg](https://github.com/fchavelli/tsseg) and its benchmark TSB-SEG.

**Status: work in progress, nothing published yet.** The datasets will be hosted
one per repository on the Hugging Face Hub (Parquet + Croissant, tagged
revisions), with an archival Zenodo snapshot (DOI) at publication. This repository
holds the code that rebuilds every dataset from its primary source, the dataset
cards, the Croissant metadata and the selection registry; it holds no data.

## Why this collection

Segmentation methods are still compared on a handful of small benchmarks, often
built by concatenating classification series. This collection gathers measured,
continuously recorded series whose segments come from documented sources
(human annotation, experimental protocol, a reference sensor), across physiology,
human activity, animal behaviour, industry, energy, motion capture and software
systems, with several annotators where they exist. Every dataset is converted to
one format and documented the same way, including its license, provenance,
annotation process and inter-annotator agreement.

## Format (version 1.1)

- Each dataset has its own directory, one `index.parquet`, and one or more
  Parquet part files per config under `data/<config>/` (about 256 MiB per part).
  Each part file contains multiple rows. A row holds one series or one chunk,
  with signals and labels as list columns; there is no file per row.
  `index.parquet` has one row per series (length, channels, split, label
  columns, annotators, change counts, files).
- Series longer than 1 h at 10 Hz or more are stored in one-hour chunks
  (`series_id`, `chunk_idx`), concatenated back by the reader.
- `-1` only where no ground truth exists (not scored, outside the protocol).
  Null / other / transition classes stay ordinary states, listed in `null_states`.
- Several annotators: `label_<annotator>` and `label_consensus` when the source
  defines one; several label semantics: `label_<track>`. `tsseg.json` keeps
  `annotators` and `tracks` apart. Pure CPD datasets: `cps_<annotator>`.
- Heavy datasets have a light `default` config and a `full` config. Configs may
  differ in sampling rate (e.g. `dreem-dod-h`: `default` resampled to 100 Hz,
  `full` at the native 250 Hz); each config's rate is in `tsseg.json`.
- Per dataset: `croissant.json` (Croissant 1.1 core + Responsible AI 1.0 fields,
  provenance), a Hugging Face dataset card (`README.md`), `tsseg.json` (loader
  metadata), `SHA256SUMS`.

Details: `tsseg_data/format.py`. Reference reader: `tsseg_data/reader.py`.

## Datasets

The evolving shortlist currently contains 50 datasets from an inventory of
about 370; about 50 is the final target, not a fixed quota. Fully generated
corpora are excluded. Selection criteria and license tiers are below. Tiers: A = permissive,
re-hosted with attribution; B = share-alike or non-commercial, re-hosted under the
same license; C = no license or "research only", built from the source only until
the authors allow re-hosting.

<!-- datasets:start -->
| Dataset | Domain | Task | License (tier) | Status |
|---|---|---|---|---|
| `tssb`: Time Series Segmentation Benchmark (TSSB) | generic_cpd | SD | BSD-3-Clause (TSSB repo); upstream UCR/UEA rights unresolved (C) | builder + validated local build (10/75 recurrent); source-only builder until the authors allow re-hosting |
| `utsa`: UCR Time Series Semantic Segmentation Archive (UTSA, FLOSS datasets) | generic_cpd | CPD | none at the source (C) | builder + validated local build (32 series; 1 recurrent); source-only builder until the authors allow re-hosting |
| `has`: Human Activity Segmentation Challenge 2023 (ECML/PKDD) | har | SD | CC-BY-NC-SA-4.0 (B) | builder + validated build (250 series, GPS removed) |
| `actrectut`: ActRecTut — Human Activity Recognition Tutorial dataset (Bulling et al.) | har | SD | GPL-3.0-or-later (B) | builder + validated build (walk + gesture) |
| `pamap2`: PAMAP2 Physical Activity Monitoring | har | SD | CC-BY-4.0 (A) | builder + validated build (Protocol + Optional; activityID=0 excluded, ~29% unscored) |
| `usc-had`: USC-HAD: USC Human Activity Dataset | har | CPD | none at the source (C) | builder + validated local build (70 artificial CPD series); source-only builder until the authors allow re-hosting |
| `pump`: Hydraulic End-of-Line Testing (Bosch) — PUMP | industry_energy | SD | CC-BY-4.0 (A) | builder + validated build (400 cycles) |
| `skab`: Skoltech Anomaly Benchmark (SKAB) | industry_energy | CPD | GPL-3.0 (B) | builder + validated build (all 129 source CP markers) |
| `mocap`: CMU MoCap subject 86 — segmentation ground truth (Barbič et al. 2004) | mocap_surgery_assembly | CPD | CMU motion terms; Barbič labels unlicensed (C) | builder + validated local build (14 Barbič trials); source-only builder until the authors allow re-hosting |
| `sleep-edfx`: Sleep-EDF Database Expanded | physio | SD | ODC-By-1.0 (A) | planned |
| `dreem-dod-h`: Dreem Open Dataset — Healthy (DOD-H) | physio | SD | MIT (A) | builder + validated build (3 of 25 nights) |
| `mitdb`: MIT-BIH Arrhythmia Database | physio | SD | ODC-By-1.0 (A) | builder + validated build (48 two-lead ECG records; rhythm + sparse beats) |
| `vfdb`: MIT-BIH Malignant Ventricular Ectopy Database | physio | SD | ODC-By-1.0 (A) | planned |
| `afdb`: MIT-BIH Atrial Fibrillation Database | physio | SD | ODC-By-1.0 (A) | planned |
| `helsinki-neonatal-eeg`: A dataset of neonatal EEG recordings with seizure annotations (Helsinki) | physio | SD | CC-BY-4.0 (A) | planned |
| `noneeg`: Non-EEG Dataset for Assessment of Neurological Status | physio | SD | ODC-By-1.0 (A) | builder + validated build (20 native 8-Hz records + native 1-Hz auxiliary) |
| `ppg-dalia`: PPG-DaLiA: PPG dataset for motion compensation and heart rate estimation in Daily Life Activities | physio | SD | CC-BY-4.0 (A) | planned |
| `eegmmidb`: EEG Motor Movement/Imagery Dataset | physio | SD | ODC-By-1.0 (A) | planned |
| `wesad`: WESAD: Wearable Stress and Affect Detection | physio | SD | Siegen scientific, non-commercial use; redistribution not granted (C) | planned; source-only builder until the authors allow re-hosting |
| `daphnet-fog`: Daphnet Freezing of Gait | physio | SD | CC-BY-4.0 (A) | builder + validated build (17 runs; outside-protocol 0 excluded) |
| `mosad`: MOSAD — Mobile Sensing Human Activity Data Set | har | SD | CC-BY-SA-3.0 (B) | planned |
| `opportunity`: OPPORTUNITY Activity Recognition | har | SD | CC-BY-4.0 (A) | builder + validated build |
| `hapt`: Smartphone-Based Recognition of Human Activities and Postural Transitions (HAPT) | har | SD | UCI CC BY 4.0; archive README prohibits commercial use (C) | builder + validated local build (61 raw experiments; licence conflict); source-only builder until the authors allow re-hosting |
| `harth`: HARTH — Human Activity Recognition Trondheim | har | SD | CC-BY-4.0 (A) | builder + validated build (22 complete recordings; timestamps retained) |
| `capture24`: CAPTURE-24: Activity tracker dataset for human activity recognition | har | SD | CC-BY-4.0 (A) | planned |
| `mhealth`: MHEALTH (Mobile HEALTH) dataset | har | SD | CC-BY-4.0 (A) | builder + validated build (10 complete logs; null state retained) |
| `casas-aruba-milan-tulum-cairo`: CASAS Smart Home dataset (aruba, cairo, milan, tulum) — labelled, with temperature | har | SD | CC-BY-4.0 (A) | planned |
| `bebe`: BEBE: Bio-logger Ethogram Benchmark (collection of 9 datasets) | ethology | SD | CC-BY-4.0 (repository); per-species licenses (A) | planned |
| `dog-behaviour-vehkaoja`: Movement Sensor Dataset for Dog Behavior Classification | ethology | SD | CC-BY-4.0 (A) | planned |
| `bee-dance`: Honey Bee Dance (PS-SLDS, Oh et al.) | ethology | SD | none; citation requested (C) | planned; source-only builder until the authors allow re-hosting |
| `petrobras-3w`: 3W Dataset 2.0.0 (undesirable events in offshore oil wells) | industry_energy | SD | CC-BY-4.0 (A) | planned |
| `cnc-mill-umich`: CNC Mill Tool Wear (University of Michigan SMART testbed) | industry_energy | SD | CC0-1.0 (A) | planned |
| `uci-gas-dynamic-mixtures`: Gas sensor array under dynamic gas mixtures (UCI 322) | industry_energy | SD | CC-BY-4.0 (A) | planned |
| `pneumatic-eol-strzinar`: Pneumatic Pressure and Electrical Current Time Series in Manufacturing (end-of-line test station) | industry_energy | SD | CC-BY-4.0 (A) | planned |
| `deddiag`: DEDDIAG — Domestic Electricity Demand Dataset of Individual Appliances in Germany | industry_energy | SD | CC-BY-4.0 (A) | planned |
| `andy-lab-oneperson`: AndyData-lab-onePerson (AnDy industry-oriented human movement and ergonomics dataset) | mocap_surgery_assembly | SD | CC-BY-4.0 (A) | planned |
| `ha4m`: HA4M — Human Action Multi-Modal Monitoring in Manufacturing (epicyclic gear train assembly) | mocap_surgery_assembly | SD | CC-BY-4.0 (A) | planned |
| `rosmag40`: ROSMAG40 — ROSMA subset with gesture annotations (dVRK) | mocap_surgery_assembly | SD | CC-BY-4.0 (A) | planned |
| `bimacs`: KIT Bimanual Actions Dataset (Bimacs) | mocap_surgery_assembly | SD | CC0-1.0 (annotations, derived data); RGB-D for scientific use (A) | planned |
| `lund2013-eye`: Lund 2013 hand-labelled eye-movement data (EyeMovementDetectorEvaluation) | mocap_surgery_assembly | SD | GPL-3.0 (B) | planned |
| `swimming-smartwatch`: Swimming Style Recognition and Lap Counting Using a Smartwatch (40 swimmers) | mocap_surgery_assembly | SD | MIT (A) | planned |
| `tcpd`: Turing Change Point Dataset (TCPD) | generic_cpd | CPD | mixed per series (CC BY, CC0, GPL-2.0, OGL, MIT, US PD; 9 not redistributable) (C) | planned; source-only builder until the authors allow re-hosting |
| `mozilla-perf-cpd-annotations`: Mozilla performance time series with multi-annotator change points (Besbes & Costa) | generic_cpd | CPD | CC-BY-4.0 (A) | builder + validated build |
| `rtt-ripe-atlas-labelled`: RTT change detection dataset (RIPE Atlas, manual labels), Shao et al. | generic_cpd | CPD | MIT (repository); RIPE Atlas data under RIPE NCC terms (A) | planned |
| `neuroblastoma-cnv`: Neuroblastoma copy number profiles with breakpoint annotations | generic_cpd | CPD | GPL-3.0 (B) | planned |
| `calms21`: Caltech Mouse Social Interactions (CalMS21) | ethology | SD | CC-BY-4.0 (A) | planned |
| `fly-vs-fly`: Fly vs. Fly (Boy meets boy, Aggression, Courtship) | ethology | SD | CC0-1.0 (A) | planned |
| `ais-fishing-semseg`: Dataset for Semantic Segmentation of Fishing Trajectories (128 AIS trajectories) | maritime | SD | CC-BY-4.0 (A) | planned |
| `ami-meeting-corpus`: AMI Meeting Corpus: diarisation, recurrent speakers (derived-feature track) | audio_speech | SD | CC-BY-4.0 (A) | planned |
| `rsdf-china-forest`: RSDF — Reference samples of Stable, Disturbed and Forestated forests over China (1986–2025) | remote_sensing | CPD | CC-BY-4.0 (A) | planned |
<!-- datasets:end -->

Inclusion criteria: continuous recordings (no pre-cut windows unless the raw
recording exists); dense state labels (SD and CPD) or annotated change points
(CPD only), at least two segments; documented label provenance, tagged as
`protocol`, `human`, `derived` or `concatenation`. Licenses are
checked at the primary source, never at a repackager.

## Usage

```bash
pip install -e ".[build,validate]"           # or reuse an environment with these packages
python -I builders/opportunity.py             # downloads to ./raw, writes ./build/opportunity
python -I builders/dreem-dod-h.py --raw-dir /path/to/cache
python -I scripts/validate.py                 # validates every build/<id>/
```

Builders read downloaded files: always run them with `python -I` (isolated mode).
Every source file is checked against a pinned sha256 (or the CRC32 of a zip
member fetched by HTTP Range).

## License

The code and documentation of this repository are under the MIT license
(`LICENSE`). Each dataset keeps its own license, stated in its card and its
`croissant.json`; cite the original authors when you use a dataset.

## Contributing

See `CONTRIBUTING.md`.
