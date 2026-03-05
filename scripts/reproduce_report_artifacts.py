"""
Reproduce the key processed datasets + result tables used in the final report.

Outputs:
- data/processed/*.csv
- results/method2_summary.csv
- results/systematics_table3.csv
- results/data_catalog.csv
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_params() -> dict:
    with open(ROOT / "data" / "metadata" / "params.json", "r", encoding="utf-8") as f:
        return json.load(f)


def ruler_calibration(pixel_x0_cm0: float, pixel_x100_cm100: float, ruler_length_cm: float = 100.0) -> dict:
    a = ruler_length_cm / (pixel_x100_cm100 - pixel_x0_cm0)
    b = -a * pixel_x0_cm0
    return {"method": "ruler", "a_cm_per_px": a, "b_cm": b}


def anchor_calibration(df: pd.DataFrame, t_transition: float, S1_cm: float, S2_cm: float, guard: float = 60.0) -> dict:
    pre = df[df["Time_Sec"] < t_transition - guard]
    post = df[df["Time_Sec"] > t_transition + guard]
    x1 = float(np.median(pre["X"]))
    x2 = float(np.median(post["X"]))
    a = (S2_cm - S1_cm) / (x2 - x1)
    b = S1_cm - a * x1
    return {"method": "anchor", "a_cm_per_px": a, "b_cm": b, "x_pre_median": x1, "x_post_median": x2}


def apply_calibration(df: pd.DataFrame, cal: dict, run_name: str) -> pd.DataFrame:
    out = df.copy()
    out["position_cm"] = cal["a_cm_per_px"] * out["X"] + cal["b_cm"]
    out["run"] = run_name
    return out


def compute_G0_method2(deltaS_cm: float, params: dict, beta: float, T_sec: float) -> float:
    c = params["constants"]
    m1 = c["m1_kg"]
    d = c["d_m"]
    r = c["r_m"]
    b = c["b_m"]
    L = c["L_m"]
    factor = d**2 + 2 * r**2 / 5
    deltaS_m = deltaS_cm / 100.0
    G = (math.pi**2) * deltaS_m * b**2 / (m1 * L * d) * factor / (T_sec**2)
    return G / (1 - beta)


def rel_u_deflection(deltaS_cm: float, u_deltaS_cm: float, params: dict, u_T_sec: float, T_sec: float) -> float:
    c = params["constants"]
    ub = c["u_b_m"]
    b = c["b_m"]
    uL = c["u_L_m"]
    L = c["L_m"]
    um1 = c["u_m1_kg"]
    m1 = c["m1_kg"]
    return math.sqrt(
        (u_deltaS_cm / deltaS_cm) ** 2
        + (2 * ub / b) ** 2
        + (uL / L) ** 2
        + (2 * u_T_sec / T_sec) ** 2
        + (um1 / m1) ** 2
    )


def main() -> None:
    params = load_params()
    c = params["constants"]

    # --- Load metadata used by the report ---
    with open(ROOT / "data" / "metadata" / "fit_3videos_summary.json", "r", encoding="utf-8") as f:
        fit_summary = json.load(f)
    deltaS_by_run = {d["case"]: float(d["delta_s_cm"]) for d in fit_summary}

    with open(
        ROOT / "data" / "metadata" / "youtube_bimodal_100cm_mb140_scale05_msec_t0_transition2880.json",
        "r",
        encoding="utf-8",
    ) as f:
        yt_meta = json.load(f)

    beta = float(yt_meta["beta"])
    T_sec = float(yt_meta["T_sec"])
    u_T_sec = float(yt_meta["u_T_sec"])
    u_deltaS_cm = float(yt_meta["u_DeltaS_cm"])

    # --- Create calibrated "processed" position tables ---
    # YouTube run (ruler calibration)
    yt_csv = ROOT / params["runs"]["youtube_100min"]["raw_csv"]
    yt_df = pd.read_csv(yt_csv)
    cal_yt = ruler_calibration(
        pixel_x0_cm0=float(yt_meta["pixel_x0_cm0"]),
        pixel_x100_cm100=float(yt_meta["pixel_x100_cm100"]),
        ruler_length_cm=float(yt_meta.get("ruler_length_cm", 100.0)),
    )
    yt_proc = apply_calibration(yt_df, cal_yt, "youtube_100min")
    yt_proc.to_csv(ROOT / "data" / "processed" / "youtube_100min_position_cm.csv", index=False)

    # In-lab runs (anchor calibration to the fitted equilibria shown in the report)
    for run_key in ["video_alt_full", "video_main_100min"]:
        run_cfg = params["runs"][run_key]
        df = pd.read_csv(ROOT / run_cfg["raw_csv"])
        cal = anchor_calibration(
            df,
            t_transition=float(run_cfg["transition_time_sec"]),
            S1_cm=float(run_cfg["S1_cm"]),
            S2_cm=float(run_cfg["S2_cm"]),
            guard=60.0,
        )
        proc = apply_calibration(df, cal, run_key)
        proc.to_csv(ROOT / "data" / "processed" / f"{run_key}_position_cm.csv", index=False)

        # Save calibration metadata too
        with open(ROOT / "data" / "processed" / f"{run_key}_calibration.json", "w", encoding="utf-8") as f:
            json.dump(cal, f, indent=2)

    # --- Method II summary table (ΔS from fit summary, G0 from PASCO formula) ---
    rows = []
    for case, deltaS_cm in [
        ("youtube_100min", deltaS_by_run["youtube_100min"]),
        ("video_alt_full", deltaS_by_run["video_alt_full"]),
        ("video_main_100min", deltaS_by_run["video_main_100min"]),
    ]:
        G0 = compute_G0_method2(deltaS_cm, params, beta=beta, T_sec=T_sec)
        rel_u = rel_u_deflection(deltaS_cm, u_deltaS_cm, params, u_T_sec=u_T_sec, T_sec=T_sec)
        rows.append(
            {
                "run": case,
                "deltaS_cm": deltaS_cm,
                "beta": beta,
                "T_sec": T_sec,
                "u_T_sec": u_T_sec,
                "G0_SI": G0,
                "uG0_stat_SI": rel_u * G0,
                "rel_uG0_stat_pct": 100 * rel_u,
            }
        )
    pd.DataFrame(rows).to_csv(ROOT / "results" / "method2_summary.csv", index=False)

    # --- Expected signal scale ΔS_exp (using accepted G) ---
    factor = c["d_m"] ** 2 + 2 * c["r_m"] ** 2 / 5
    deltaS_exp_cm = (
        c["G_true"]
        * (1 - beta)
        * c["m1_kg"]
        * c["L_m"]
        * c["d_m"]
        / (math.pi**2 * c["b_m"] ** 2)
        * (T_sec**2 / factor)
        * 100.0
    )

    # --- Systematics table (Table 3 in the paper) expressed as δ(ΔS) ---
    F_sig = c["G_true"] * c["m1_kg"] * c["m2_kg"] / (c["b_m"] ** 2)
    tau_sig = 2 * F_sig * c["d_m"]

    # 1) Stray gravity: 70 kg at 1 m
    r1, r2 = c["r_person_m_examples"]
    F1 = c["G_true"] * c["m2_kg"] * c["M_person_kg"] / (r1**2)
    F2 = c["G_true"] * c["m2_kg"] * c["M_person_kg"] / (r2**2)
    dS_person_cm = (F1 * c["d_m"] / tau_sig) * deltaS_exp_cm
    dS_move_cm = ((F1 - F2) * c["d_m"] / tau_sig) * deltaS_exp_cm

    # 2) Base tilt: δS ≈ 4 L δθ
    def dS_from_tilt_mrad(mrad: float) -> float:
        return 4 * c["L_m"] * (mrad * 1e-3) * 100

    dS_tilt_01 = dS_from_tilt_mrad(0.1)
    dS_tilt_05 = dS_from_tilt_mrad(0.5)

    # 3) Ribbon drift example (user-observed scale)
    dS_drift_cm = c["ribbon_drift_cm_example"]

    # 4) Source-mass spacing asymmetry (δb ≈ 2 mm)
    b = c["b_m"]
    db = c["delta_b_asym_m"]
    f = 0.5 * (1 + (b / (b + db)) ** 2)  # effective torque factor / (2/b^2)
    dS_asym_cm = (1 - f) * deltaS_exp_cm

    # 5) Finite-twist geometry (small)
    theta_exp = (deltaS_exp_cm / 100.0) / (4 * c["L_m"])
    db_exp = c["d_m"] * theta_exp
    rel_force_exp = 2 * db_exp / b
    dS_hidden_cm = rel_force_exp * deltaS_exp_cm

    # 6) Scale calibration: two endpoints each ±5 px uncertainty
    u_sep_px = math.sqrt(c["scale_endpoint_px_unc_each"] ** 2 + c["scale_endpoint_px_unc_each"] ** 2)
    rel_scale = u_sep_px / c["scale_pixels_example"]
    dS_scale_cm = rel_scale * deltaS_exp_cm

    table3 = [
        ("70 kg person at 1 m", r"$F=Gm_2M/r^2;\ \tau\sim Fd$", dS_person_cm),
        ("Person moving 1m→2m", r"$\Delta F = F(1)-F(2)$", dS_move_cm),
        ("Base tilt 0.1 mrad", r"$\delta S\approx 4L\delta\theta$", dS_tilt_01),
        ("Base tilt 0.5 mrad", r"$\delta S\approx 4L\delta\theta$", dS_tilt_05),
        ("Ribbon drift (example)", r"slow drift over hours", dS_drift_cm),
        ("Source-mass spacing asymmetry (δb≈2 mm)", r"$f=\frac{(1/b^2+1/(b+\delta b)^2)}{2/b^2};\ \delta(\Delta S)\approx(1-f)\Delta S_{\rm exp}$", dS_asym_cm),
        ("Finite-twist geometry", r"$\delta F/F\approx 2(d\theta)/b$", dS_hidden_cm),
        ("Scale calibration (example)", r"$\delta(\Delta S)/\Delta S\sim \delta s/s$", dS_scale_cm),
    ]
    sys_df = pd.DataFrame(
        {
            "effect": [t[0] for t in table3],
            "model_formula_latex": [t[1] for t in table3],
            "delta_deltaS_cm": [t[2] for t in table3],
        }
    )
    sys_df["frac_of_deltaSexp_pct"] = 100 * sys_df["delta_deltaS_cm"] / deltaS_exp_cm
    sys_df["deltaS_exp_cm_used"] = deltaS_exp_cm
    sys_df.to_csv(ROOT / "results" / "systematics_table3.csv", index=False)

    # --- Data catalog (sizes + row counts) ---
    catalog_rows = []
    for p in sorted((ROOT / "data").rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(ROOT).as_posix()
        size_mb = p.stat().st_size / (1024 * 1024)
        row_count = ""
        if p.suffix.lower() == ".csv":
            try:
                row_count = int(sum(1 for _ in open(p, "rb")) - 1)
            except Exception:
                row_count = ""
        catalog_rows.append({"path": rel, "size_mb": round(size_mb, 3), "rows": row_count})
    pd.DataFrame(catalog_rows).to_csv(ROOT / "results" / "data_catalog.csv", index=False)

    print("Done. Artifacts written to data/processed and results/.")


if __name__ == "__main__":
    main()
