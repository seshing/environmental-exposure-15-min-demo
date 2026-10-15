# Environmental Exposure · 15-minute City

A local, static research website with a minimal white interface.

- **United States:** switch between the Figure 2 population-weighted accessibility × EEI city profile and within-city CBG **local r**. Colours use the original Figure 2 palette and terciles; dot sizes retain the original population classes with larger circles and a 2–5M legend entry. The local-r map retains the paper’s `p < 0.01` filter.
- **MSA:** view its boundary and CBG access-time rings (≤15, 15–30, 30–60, >60 minutes). The city panel highlights the selected city among the 380 Figure 2a city profiles. Accessibility and exposure are shown as national empirical percentiles (P100 is highest), without population totals. The Access time / EEI tabs switch CBG map colouring; EEI classes use fixed national CBG quintiles and allow category filtering. Three dots on a 0–50% scale show the original Figure 3 availability (values beyond the scale keep their true labels): the population-weighted share of ≤15-minute building layers whose component-relative exposure reaches 1 against each outer ring. This is the published component-relative preservation capacity. Scatter plotting areas have equal width and height.
- **Chip:** 30 cities each display one verified 5 m chip. Washington retains `chip_64482_pid_103_36`; the other 29 cities were selected from the largest Figure 3 eligible metros. The chip lies near the median location of each city’s 50 most accessible CBGs. Cities with models have a `3D` label in the city menu. Click the softly glowing green point to enter its model.
- **5 m model:** switch **Nature view / Openness**. Click a building to focus it and see its mean, ID and footprint area; click again to inspect a 5 m voxel layer. Building and tree-canopy visibility are independent, and hiding canopy retains grass. Voxel layers are not surveyed floors.

## Local preview

```bash
cd /Users/seshing/Notebook/VoxCity-demo
python3 -m http.server 8876 --bind 127.0.0.1 --directory dist
```

Open http://127.0.0.1:8876/. Everything is read from static files; no simulation runs in the browser and no credentials are exposed. The basemap requires internet access. The website is published with GitHub Pages from `dist/`.

## Research results

The national and MSA maps use the specified publication outputs downloaded read-only from SSH host `5090`:

- Figure 2: `/home/xiucheng/projects/Voxcity/output/publication383_fig1245_preview_20261001/full/outputs/02_fig2/`. The saved city summary contains **380 eligible cities**. City coordinates use `mean_access_z` and `mean_eei_z`, with floor-population-weighted CBG means. Local correlations, p-values and sample sizes are read directly; the original `p < 0.01` filter and tercile palette are retained.
- Figure 3: `/home/xiucheng/projects/Voxcity/output/publication383_figure3_repaired_20261003/outputs/03_fig3/`. The saved result contains **212 eligible cities**. Preservation is the population-weighted share of valid ≤15-minute floors where `0.5 × (Nature / outer-ring Nature + Openness / outer-ring Openness) ≥ 1`. It is read from `fig3_floor_preservation_capacity.csv`, rather than computed from EEI loss. Washington's 15–30, 30–60 and >60-minute values are **30.0364%, 23.5178% and 14.2361%**.
- CBG exposure and access times use the latest Figure 2 table (167,659 valid CBGs). All 52,602 overlapping Figure 3 CBG rows match exactly. CBG EEI colours use national z-score quintiles. No exposure is imputed for missing records.
- MSA boundaries and the 196,266 CBG geometries come from the repaired 2020 geography used by the publication. CBG boundaries are simplified by 60 m for drawing only; metric values are unchanged.

Downloaded tables and code snapshots remain in `source/publication_latest/`, outside the website and Git. `dist/data/project/provenance.json` records versions, source checksums and definitions. The 30 precomputed chip models are retained. Building reference calculations are refreshed separately from the same latest publication parameters and repaired floor inputs.

## Real 5 m model

Files were pulled read-only from SSH host `5090`:

- `/mnt/data/xiucheng/voxcity/from_data2/model/us_top500/chip_64482_pid_103_36/`: model grid, building IDs, footprints and `meshsize.npy` (int64 scalar 5).
- `/data2/shared/xiucheng/voxcity/output/us_top500/simulation/chip_64482_pid_103_36/`: `bd_vegetation.csv` and `bd_openness.csv`. The vegetation field is labelled **Nature view** in the interface.

The model contains 8,403 source building IDs and 710,594 recorded triangles. Historical VoxCity open-air geometry is reconstructed from the source voxels. Its triangle order was verified exactly against the previously saved original mesh, and every reconstructed face ID and building ID matches both CSV files. All source values and missing values are preserved, with Float32 precision in browser exports. The north-axis orientation is checked against the source footprint locations; the median alignment residual is about 1.27 Mercator metres. Original simulations are not rerun. Displayed building and layer means remain area-weighted over their recorded finite model faces. Building EEI is now the mean of the latest national Nature and Openness z-scores, with no 0–1 rescaling, clipping or missing-value imputation.

Building rankings use the repaired/deduplicated 2020 primary floors, the publication's two-sided exposure limits and positive area/population filters. Within each building, reference Nature and Openness means use face-count weights so they are comparable to model surface means. Each metro fit uses all eligible reference buildings, with equal weight per building, against log1p(mean nine-category CBG travel time). It is a building-level comparison, distinct from Figure 2's population-weighted CBG statistics. Only the rendered dots are sampled.

Model footprints are matched to original unsimplified repaired CBG boundaries. City/Chip rankings use midpoint percentiles; lower travel time ranks higher. The EEI raw-metric rank and the fit-residual Top 10% badge remain separate. Access index is the reversed city min-max of log1p(time), spanning the reference and selected chip; EEI axes use the actual z-score range. Unmatched CBGs retain unavailable travel-time results. Clicking a voxel layer does not change the building-level rank or fit point.


Raw files and reconstruction metadata live in `source/`, outside the served `dist/` tree and excluded by `.gitignore`. The previous 2 m app and documentation are retained in `backups/`; its original data are not deleted.

## Regenerate or extend

Use `/Users/seshing/anaconda3/envs/voxcity/bin/python` with NumPy, pandas and GeoPandas:

```bash
python scripts/prepare_project_data.py
python scripts/import_paper_chip.py --chip chip_64482_pid_103_36
python scripts/prepare_model.py --source source/chip_64482_pid_103_36 --out dist/data/chips/chip_64482_pid_103_36 --id chip_64482_pid_103_36 --name "Washington · chip 64482"
python scripts/prepare_tradeoff.py --model-dir dist/data/chips/chip_64482_pid_103_36
python scripts/prepare_eei_tradeoff.py --cbsa 47900 --model-dir dist/data/chips/chip_64482_pid_103_36 --name Washington
```

To add a region, export its manifest and assets under `dist/data/chips/<chip-id>/`, register its city and manifest in the project index, and mark its actual chip polygon available. The viewer loads the selected manifest dynamically. Other-model face IDs must pass the import checks before use.

[Research project](https://github.com/seshing/environmental-exposure-15-min) · [VoxCity](https://github.com/kunifujiwara/VoxCity)

## 30-city model collection

The active city/chip registry is `scripts/demo_chips.json`. `dist/data/project/demo-cities.csv` lists cities, chip IDs, resolution and building counts. `prepare_project_data.py` retains this registry when regenerating maps.

`python scripts/expand_demo.py` can resume verified imports using `scripts/demo_candidates.json` and the locally retained `source/demo_remote_probe.json`. It reads models and both simulation CSVs over SSH from 5090. Each import requires an exact match of every reconstructed surface ID and building ID with both source result files, followed by geometry, footprint-registration and exposure-value checks. Only completed models are registered. Source files and processing logs remain outside the web directory in `source/`.

The viewer loads one selected model at a time and disposes its GPU resources when switching to another city. National figures and EEI normalization retain the existing local paper-data version.

## Model compression

Run `python scripts/compress_models.py` after exporting new models. It gzip-compresses the binary assets, verifies byte-for-byte equality, updates each manifest, and moves originals into `source/compression-originals/` outside the published website. Already compressed models are skipped. The browser decompresses `.gz` assets with `DecompressionStream` before reading their original arrays. Geometry, resolution and simulation values are unchanged. `source/compression-report.json` records the compression results.

## Refresh building ranks

Run `python scripts/recalculate_building_ranks.py` with the geospatial Python environment. It streams the repaired primary floor inputs once for all 30 cities over read-only SSH, calculates the city references, then verifies and updates each `tradeoff-eei.json`. No remote files are written. Use `--cbsa 47900` to refresh one registered metro. Previous JSON files and calculation logs remain under `source/`.
