# Cavendish torsion balance: laser tracking and time-series analysis

This repository documents a Cavendish torsion balance experiment using video-based laser-spot tracking, calibrated position reconstruction, and uncertainty-aware analysis of the gravitational constant.

## What the code does

- Track the reflected laser spot from video with OpenCV
- Convert pixel coordinates to physical displacement
- Reconstruct equilibrium shifts and oscillation behavior across multiple runs
- Recompute Method II results and the systematic-error table used in the report
- Export processed datasets and summary tables from the raw inputs

## Reproduce the analysis artifacts

```bash
pip install -r requirements.txt
python scripts/reproduce_report_artifacts.py
```

Generated outputs include:

- `data/processed/*.csv`
- `results/method2_summary.csv`
- `results/systematics_table3.csv`
- `results/data_catalog.csv`

## Repository structure

```text
data/raw/        Raw laser-spot tracking CSVs
data/metadata/   Calibration and fit metadata used by the report
data/processed/  Generated calibrated position tables
figures/         Key plots used in the report
results/         Recomputed summary tables
scripts/         Reproducibility scripts
src/             Core tracking and analysis code
reports/         Final PDF report and LaTeX source
```

## Raw data fields

The tracking CSV files contain:

- `Frame`: video frame index
- `Time_Sec`: time in seconds
- `X`, `Y`: laser-spot centroid in pixels
- `Mode`: `TRACKING` or `RECOVERED`
- `Area`, `Circularity`: blob-shape diagnostics

## Report

- Final report: `reports/report_final.pdf`

## Author

Hongyu Wang  
Lab partner: Cici Zhang
