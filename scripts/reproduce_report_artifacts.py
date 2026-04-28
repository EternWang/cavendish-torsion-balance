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
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
BLUE = "#2F6B9A"
ORANGE = "#D97935"
GREEN = "#5B8C5A"
GRAY = "#4A5568"
LIGHT = "#EEF2F6"


def set_plot_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 240,
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": "#D9DEE7",
            "grid.linewidth": 0.8,
            "grid.alpha": 0.75,
            "legend.frameon": False,
        }
    )


def save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_card(ax: plt.Axes, x: float, y: float, w: float, h: float, title: str, body: str, color: str) -> None:
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.018,rounding_size=0.025",
        facecolor="white",
        edgecolor="#CBD5E1",
        linewidth=1.0,
    )
    ax.add_patch(box)
    title_y = y + h - 0.075 if body else y + h / 2
    title_va = "top" if body else "center"
    ax.text(x + 0.035, title_y, title, ha="left", va=title_va, fontsize=10.2, weight="bold", color=color)
    if body:
        ax.text(x + 0.035, y + h - 0.215, body, ha="left", va="top", fontsize=8.45, color="#172033", linespacing=1.18)


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


def plot_readme_overview(method_df: pd.DataFrame, sys_df: pd.DataFrame, params: dict) -> None:
    set_plot_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4), gridspec_kw={"width_ratios": [1.15, 1.0]})

    labels = ["YouTube run", "Alt in-lab run", "Main in-lab run"]
    y = np.arange(len(labels))
    g_values = method_df["G0_SI"].to_numpy(dtype=float) * 1e10
    g_sigma = method_df["uG0_stat_SI"].to_numpy(dtype=float) * 1e10
    accepted = params["constants"]["G_true"] * 1e10

    axes[0].errorbar(g_values, y, xerr=g_sigma, fmt="o", color=BLUE, ecolor="#7FA7C7", capsize=5, ms=7)
    axes[0].axvline(accepted, color=GREEN, ls="--", lw=1.5, label="Accepted G")
    axes[0].set_yticks(y, labels)
    axes[0].set_xlabel("G estimate (10^-10 SI)")
    axes[0].set_title("Method II estimates from calibrated deflection")
    for x, yy, sigma in zip(g_values, y, g_sigma):
        axes[0].text(x + sigma + 0.08, yy, f"{x:.2f} +/- {sigma:.2f}", va="center", color=GRAY, fontsize=9)
    axes[0].legend(loc="lower right")

    top_sys = sys_df.sort_values("frac_of_deltaSexp_pct", ascending=False).head(5).iloc[::-1]
    axes[1].barh(top_sys["effect"], top_sys["frac_of_deltaSexp_pct"], color=ORANGE)
    axes[1].set_xlabel("Effect size (% of expected deflection)")
    axes[1].set_title("Largest systematic-error scales")
    for idx, value in enumerate(top_sys["frac_of_deltaSexp_pct"]):
        axes[1].text(value + 0.4, idx, f"{value:.1f}%", va="center", color=GRAY, fontsize=9)

    fig.suptitle("Cavendish torsion balance: traceable measurement pipeline", y=1.03, fontsize=15, fontweight="bold")
    save_figure(fig, FIG_DIR / "method2_overview.png")


def plot_research_snapshot(method_df: pd.DataFrame, sys_df: pd.DataFrame, params: dict) -> None:
    set_plot_style()
    fig = plt.figure(figsize=(11.2, 5.5), facecolor="white")
    grid = fig.add_gridspec(2, 3, height_ratios=[0.92, 1.08], width_ratios=[1.05, 1.0, 1.0])

    accepted = params["constants"]["G_true"] * 1e10
    main_run = method_df.loc[method_df["run"] == "video_main_100min"].iloc[0]
    top_sys = sys_df.sort_values("frac_of_deltaSexp_pct", ascending=False).head(4)

    ax_cards = fig.add_subplot(grid[0, :])
    ax_cards.axis("off")
    ax_cards.set_xlim(0, 1)
    ax_cards.set_ylim(0, 1)
    fig.suptitle("Cavendish torsion balance analysis", x=0.04, y=0.985, ha="left", fontsize=17, weight="bold", color="#172033")
    fig.text(
        0.04,
        0.925,
        "Video-derived laser tracking converted into calibrated deflection estimates and systematic-error tables.",
        ha="left",
        fontsize=10.5,
        color=GRAY,
    )

    draw_card(
        ax_cards,
        0.02,
        0.08,
        0.28,
        0.68,
        "Tracking inputs",
        "laser-spot centroids\nruler / anchor calibration\nposition tables",
        BLUE,
    )
    draw_card(
        ax_cards,
        0.36,
        0.08,
        0.28,
        0.68,
        "Method II output",
        f"main run G = {main_run['G0_SI'] * 1e10:.2f} +/- {main_run['uG0_stat_SI'] * 1e10:.2f}\n"
        f"accepted G = {accepted:.2f}\n"
        "values shown in 10^-10 SI units",
        ORANGE,
    )
    draw_card(
        ax_cards,
        0.70,
        0.08,
        0.28,
        0.68,
        "Systematics",
        f"{len(sys_df)} modeled effects\n"
        f"largest: {top_sys.iloc[0]['effect']}\n"
        "regenerated from parameters",
        GREEN,
    )

    ax_g = fig.add_subplot(grid[1, :2])
    labels = ["YouTube run", "Alt in-lab run", "Main in-lab run"]
    y = np.arange(len(labels))
    values = method_df["G0_SI"].to_numpy(dtype=float) * 1e10
    errors = method_df["uG0_stat_SI"].to_numpy(dtype=float) * 1e10
    ax_g.errorbar(values, y, xerr=errors, fmt="o", color=BLUE, ecolor="#7FA7C7", capsize=5, ms=8)
    ax_g.axvline(accepted, color=GREEN, ls="--", lw=1.5, label="accepted value")
    ax_g.set_yticks(y, labels)
    ax_g.set_xlabel("G estimate (10^-10 SI)")
    ax_g.set_title("Calibrated deflection estimates", weight="bold", loc="left")
    ax_g.set_xlim(0.55, max(values + errors) + 0.75)
    for x, yy, sigma in zip(values, y, errors):
        ax_g.text(x + sigma + 0.08, yy, f"{x:.2f} +/- {sigma:.2f}", va="center", color=GRAY, fontsize=9.5)
    ax_g.legend(loc="lower right")

    ax_sys = fig.add_subplot(grid[1, 2])
    top = top_sys.iloc[::-1].copy()
    short_labels = {
        "Source-mass spacing asymmetry (delta b approx 2 mm)": "mass-spacing asymmetry",
        "Ribbon drift (example)": "ribbon drift",
        "Base tilt 0.5 mrad": "base tilt 0.5 mrad",
        "Base tilt 0.1 mrad": "base tilt 0.1 mrad",
    }
    top["display_effect"] = top["effect"].map(lambda value: short_labels.get(value, value[:28]))
    ax_sys.barh(top["display_effect"], top["frac_of_deltaSexp_pct"], color=ORANGE)
    ax_sys.set_xlabel("% of expected deflection")
    ax_sys.set_title("Largest systematic scales", weight="bold", loc="left")
    for idx, value in enumerate(top["frac_of_deltaSexp_pct"]):
        ax_sys.text(value + 0.5, idx, f"{value:.1f}%", va="center", color=GRAY, fontsize=9)
    ax_sys.set_xlim(0, top["frac_of_deltaSexp_pct"].max() * 1.22)

    fig.tight_layout(rect=[0.03, 0.02, 0.99, 0.9])
    fig.savefig(FIG_DIR / "research_snapshot.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


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

    # --- Method II summary table (deltaS from fit summary, G0 from PASCO formula) ---
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
    method_df = pd.DataFrame(rows)
    method_df.to_csv(ROOT / "results" / "method2_summary.csv", index=False)

    # --- Expected signal scale deltaS_exp (using accepted G) ---
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

    # --- Systematics table (Table 3 in the paper) expressed as delta(deltaS) ---
    F_sig = c["G_true"] * c["m1_kg"] * c["m2_kg"] / (c["b_m"] ** 2)
    tau_sig = 2 * F_sig * c["d_m"]

    # 1) Stray gravity: 70 kg at 1 m
    r1, r2 = c["r_person_m_examples"]
    F1 = c["G_true"] * c["m2_kg"] * c["M_person_kg"] / (r1**2)
    F2 = c["G_true"] * c["m2_kg"] * c["M_person_kg"] / (r2**2)
    dS_person_cm = (F1 * c["d_m"] / tau_sig) * deltaS_exp_cm
    dS_move_cm = ((F1 - F2) * c["d_m"] / tau_sig) * deltaS_exp_cm

    # 2) Base tilt: deltaS ~= 4 L delta(theta)
    def dS_from_tilt_mrad(mrad: float) -> float:
        return 4 * c["L_m"] * (mrad * 1e-3) * 100

    dS_tilt_01 = dS_from_tilt_mrad(0.1)
    dS_tilt_05 = dS_from_tilt_mrad(0.5)

    # 3) Ribbon drift example (user-observed scale)
    dS_drift_cm = c["ribbon_drift_cm_example"]

    # 4) Source-mass spacing asymmetry (delta b approx 2 mm)
    b = c["b_m"]
    db = c["delta_b_asym_m"]
    f = 0.5 * (1 + (b / (b + db)) ** 2)  # effective torque factor / (2/b^2)
    dS_asym_cm = (1 - f) * deltaS_exp_cm

    # 5) Finite-twist geometry (small)
    theta_exp = (deltaS_exp_cm / 100.0) / (4 * c["L_m"])
    db_exp = c["d_m"] * theta_exp
    rel_force_exp = 2 * db_exp / b
    dS_hidden_cm = rel_force_exp * deltaS_exp_cm

    # 6) Scale calibration: two endpoints, each with +/-5 px uncertainty
    u_sep_px = math.sqrt(c["scale_endpoint_px_unc_each"] ** 2 + c["scale_endpoint_px_unc_each"] ** 2)
    rel_scale = u_sep_px / c["scale_pixels_example"]
    dS_scale_cm = rel_scale * deltaS_exp_cm

    table3 = [
        ("70 kg person at 1 m", r"$F=Gm_2M/r^2;\ \tau\sim Fd$", dS_person_cm),
        ("Person moving 1 m to 2 m", r"$\Delta F = F(1)-F(2)$", dS_move_cm),
        ("Base tilt 0.1 mrad", r"$\delta S\approx 4L\delta\theta$", dS_tilt_01),
        ("Base tilt 0.5 mrad", r"$\delta S\approx 4L\delta\theta$", dS_tilt_05),
        ("Ribbon drift (example)", r"slow drift over hours", dS_drift_cm),
        ("Source-mass spacing asymmetry (delta b approx 2 mm)", r"$f=(1/b^2+1/(b+\delta b)^2)/(2/b^2)$", dS_asym_cm),
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
    plot_readme_overview(method_df, sys_df, params)
    plot_research_snapshot(method_df, sys_df, params)

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
