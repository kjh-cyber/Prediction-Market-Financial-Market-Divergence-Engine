"""Directional diagnostic — is there ANY exploitable coupling, and which way does it lead?

Answers three questions using already-collected data (read-only):
  1) Contemporaneous coupling: corr(ΔPM_prob, direction·ΔAsset) per mapped pair.
     If ~0 across the board → no lead-lag possible in EITHER direction.
  2) Lead-lag: at which hourly lag k does |corr| peak?
     k<0 asset leads PM · k=0 simultaneous · k>0 PM leads asset.
  3) PM→financial forward hit-rate: after a big PM move, does the asset move
     in the mapped direction over the next H hours? (only for coupled pairs)

Outputs (reports/):
  05_contemporaneous_corr.png · 06_leadlag_and_pm_to_fin.png
  directional_diagnostic.json · DIRECTIONAL_REPORT.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from divergence_engine.mappings.definitions import get_all_mappings  # noqa: E402

DB = ROOT / "data" / "divergence.db"
MAX_GAP_H = 3        # consecutive aligned points must be within this many hours
MIN_POINTS = 40      # need at least this many change-observations to trust a corr
LAGS = range(-6, 7)  # hourly lead-lag scan
FWD_H = 24           # PM->financial forward horizon
PM_MOVE_THR = 0.03   # "big" PM move threshold for the forward test

FONT = Path.home() / ".local/share/fonts/NanumGothic.ttf"
if FONT.exists():
    fm.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams.update({"figure.dpi": 120, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.axisbelow": True})


def load_series():
    con = sqlite3.connect(DB)
    # representative YES token per event = token with most snapshots
    rep = pd.read_sql_query(
        "SELECT event_slug, token_id, COUNT(*) n FROM prediction_snapshots "
        "GROUP BY event_slug, token_id", con)
    rep = rep.sort_values("n").drop_duplicates("event_slug", keep="last")
    tokmap = dict(zip(rep["event_slug"], rep["token_id"]))

    pm = pd.read_sql_query(
        "SELECT event_slug, token_id, probability, timestamp FROM prediction_snapshots", con)
    asset = pd.read_sql_query(
        "SELECT ticker, close_price, timestamp FROM asset_snapshots", con)
    con.close()
    return tokmap, pm, asset


def hourly(df, tcol, vcol, key, keyval):
    s = df[df[key] == keyval][[tcol, vcol]].copy()
    if s.empty:
        return None
    s["hour"] = (s[tcol] // 3600) * 3600
    s = s.sort_values(tcol).groupby("hour")[vcol].last()
    return s


def aligned_changes(pm_s, as_s, direction):
    """Return DataFrame of aligned hourly changes (dP, effA) with gap filtering."""
    df = pd.DataFrame({"prob": pm_s, "price": as_s}).dropna()
    if len(df) < MIN_POINTS + 1:
        return None
    df = df.sort_index()
    hours = df.index.to_numpy()
    gap_ok = np.concatenate([[False], (np.diff(hours) <= MAX_GAP_H * 3600)])
    df["dP"] = df["prob"].diff()
    df["dA"] = df["price"].pct_change()
    df = df[gap_ok].dropna()
    if len(df) < MIN_POINTS:
        return None
    df["effA"] = -df["dA"] if direction == "inverse" else df["dA"]
    return df


def main():
    tokmap, pm, asset = load_series()
    rows = []
    leadlag = {}
    for m in get_all_mappings():
        tok = tokmap.get(m.event_slug)
        if tok is None:
            continue
        pm_s = hourly(pm, "timestamp", "probability", "token_id", tok)
        if pm_s is None:
            continue
        for tk in m.asset_tickers:
            as_s = hourly(asset, "timestamp", "close_price", "ticker", tk)
            if as_s is None:
                continue
            df = aligned_changes(pm_s, as_s, m.correlation_direction)
            if df is None:
                continue
            c0 = float(df["dP"].corr(df["effA"]))
            # lead-lag scan on the sequential aligned rows (approximate)
            best_k, best_c = 0, 0.0
            lags_c = {}
            for k in LAGS:
                cc = float(df["dP"].corr(df["effA"].shift(-k)))
                lags_c[k] = cc if cc == cc else 0.0
                if abs(lags_c[k]) > abs(best_c):
                    best_c, best_k = lags_c[k], k
            # PM->financial forward hit-rate
            big = df[df["dP"].abs() >= PM_MOVE_THR]
            fwd_hits = fwd_n = 0
            probk = pm_s  # reuse
            rows.append({
                "event": m.event_slug, "ticker": tk, "dir": m.correlation_direction,
                "n": len(df), "corr0": round(c0, 3),
                "best_lag_h": best_k, "best_corr": round(best_c, 3),
            })
            leadlag[f"{m.event_slug}|{tk}"] = lags_c

    res = pd.DataFrame(rows).sort_values("corr0", key=lambda s: s.abs(), ascending=False)

    # ---- PM->financial forward hit-rate (aggregate, coupled pairs |corr0|>=0.1) ----
    # recompute forward on aligned change series with horizon shift
    con = sqlite3.connect(DB)
    fwd_rows = []
    for m in get_all_mappings():
        tok = tokmap.get(m.event_slug)
        if tok is None:
            continue
        pm_s = hourly(pm, "timestamp", "probability", "token_id", tok)
        if pm_s is None:
            continue
        for tk in m.asset_tickers:
            as_s = hourly(asset, "timestamp", "close_price", "ticker", tk)
            if as_s is None:
                continue
            df = pd.DataFrame({"prob": pm_s, "price": as_s}).dropna().sort_index()
            if len(df) < MIN_POINTS:
                continue
            df["dP"] = df["prob"].diff()
            # forward asset return over FWD_H hours
            fut = df["price"].reindex(
                df.index.to_series().add(FWD_H * 3600).to_numpy(), method="nearest",
                tolerance=MAX_GAP_H * 3600)
            fut.index = df.index
            df["fwdA"] = (fut.to_numpy() - df["price"].to_numpy()) / df["price"].to_numpy()
            df["effFwd"] = -df["fwdA"] if m.correlation_direction == "inverse" else df["fwdA"]
            big = df[(df["dP"].abs() >= PM_MOVE_THR)].dropna(subset=["effFwd"])
            for _, r in big.iterrows():
                if r["effFwd"] == 0:
                    continue
                pred_up = r["dP"] > 0  # PM prob up -> expect effA up
                hit = (r["effFwd"] > 0) == pred_up
                fwd_rows.append(int(hit))
    con.close()
    fwd_n = len(fwd_rows)
    fwd_hit = float(np.mean(fwd_rows)) if fwd_n else float("nan")

    # ---- summary ----
    corrs = res["corr0"].to_numpy()
    summary = {
        "pairs": int(len(res)),
        "corr0_mean_abs": round(float(np.nanmean(np.abs(corrs))), 3),
        "corr0_median_abs": round(float(np.nanmedian(np.abs(corrs))), 3),
        "pairs_abs_ge_0.1": int((np.abs(corrs) >= 0.1).sum()),
        "pairs_abs_ge_0.2": int((np.abs(corrs) >= 0.2).sum()),
        "strongest": res.head(8).to_dict("records"),
        "pm_to_fin_fwd": {"n": fwd_n, "hit_rate": round(fwd_hit, 4),
                          "horizon_h": FWD_H, "pm_move_thr": PM_MOVE_THR},
    }
    (HERE / "directional_diagnostic.json").write_text(json.dumps(summary, indent=2))

    # ---- plot 5: contemporaneous corr per pair ----
    fig, ax = plt.subplots(figsize=(9, 8))
    r2 = res.copy()
    r2["label"] = r2["event"].str.slice(0, 22) + " · " + r2["ticker"]
    r2 = r2.sort_values("corr0")
    colors = ["#C44E52" if abs(v) < 0.1 else "#55A868" for v in r2["corr0"]]
    ax.barh(r2["label"], r2["corr0"], color=colors)
    ax.axvline(0, color="k", lw=0.8)
    ax.axvline(0.1, color="#888", ls="--", lw=0.8)
    ax.axvline(-0.1, color="#888", ls="--", lw=0.8)
    ax.set_xlabel("동시점 상관  corr(ΔPM확률, 방향보정 Δ자산)")
    ax.set_title(f"매핑 페어 동시점 커플링 ({len(res)}쌍)\n"
                 f"|corr|<0.1 = 사실상 무상관(빨강), 회색선=±0.1")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout(); fig.savefig(HERE / "05_contemporaneous_corr.png"); plt.close(fig)

    # ---- plot 6: lead-lag of strongest pairs + PM->fin bar ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    top = res.reindex(res["corr0"].abs().sort_values(ascending=False).index).head(5)
    for _, r in top.iterrows():
        key = f"{r['event']}|{r['ticker']}"
        lc = leadlag.get(key, {})
        xs = sorted(lc)
        ax1.plot(xs, [lc[k] for k in xs], marker="o", ms=3,
                 label=f"{r['event'][:16]}·{r['ticker']}")
    ax1.axvline(0, color="k", lw=0.8); ax1.axhline(0, color="k", lw=0.5)
    ax1.set_xlabel("lag k (시간)  ←자산선행 | PM선행→")
    ax1.set_ylabel("corr(ΔPM_t, ΔeffA_{t+k})")
    ax1.set_title("리드-랙 (상위 5쌍)")
    ax1.legend(fontsize=7)
    # PM->fin bar
    p = fwd_hit * 100 if fwd_n else 0
    ax2.bar(["PM→금융\n+%dh" % FWD_H], [p], color="#4C72B0", width=0.5)
    ax2.axhline(50, color="k", ls="--", lw=1)
    ax2.set_ylim(0, 100); ax2.set_ylabel("방향 적중률 (%)")
    ax2.text(0, p + 2, f"{p:.1f}%\nn={fwd_n}", ha="center", fontsize=10)
    ax2.set_title("PM→금융 forward 적중률")
    fig.tight_layout(); fig.savefig(HERE / "06_leadlag_and_pm_to_fin.png"); plt.close(fig)

    # ---- markdown ----
    md = f"""# 방향성 진단 — 커플링 유무 및 리드-랙

□ 목적
○ 방향 선택 전, 매핑 페어에 애초에 상관(커플링)이 있는지부터 확인
○ 상관이 없으면 어느 방향이든 lead-lag 차익 불가 → 프로젝트 전제 붕괴

□ 동시점 커플링 (핵심)
○ 페어 {summary['pairs']}쌍, |corr| 평균 {summary['corr0_mean_abs']} · 중앙값 {summary['corr0_median_abs']}
○ |corr|≥0.1 인 페어: {summary['pairs_abs_ge_0.1']}쌍 / |corr|≥0.2: {summary['pairs_abs_ge_0.2']}쌍
○ 대부분 0 근처면 → 예측시장·금융시장이 시간단위로 함께 움직이지 않음(무상관)

□ 리드-랙
○ 상관이 있는 소수 페어에 한해 최대 |corr| 지연(k) 확인
○ k<0 자산 선행 · k=0 동시 · k>0 PM 선행

□ PM → 금융 forward 적중률
○ PM 확률 큰 이동(|ΔP|≥{PM_MOVE_THR}) 후 +{FWD_H}h 자산 방향 적중률: {p:.1f}% (n={fwd_n})
○ 50% 근처면 → 폴리마켓도 금융을 선행하지 못함

□ 산출물
○ 05_contemporaneous_corr.png · 06_leadlag_and_pm_to_fin.png · directional_diagnostic.json
"""
    (HERE / "DIRECTIONAL_REPORT.md").write_text(md)

    print("=== 동시점 상관 상위 8쌍 ===")
    print(res.head(8).to_string(index=False))
    print(f"\n|corr| 평균 {summary['corr0_mean_abs']}, 중앙값 {summary['corr0_median_abs']}, "
          f"|corr|>=0.1 {summary['pairs_abs_ge_0.1']}/{summary['pairs']}쌍")
    print(f"PM->금융 +{FWD_H}h 적중률: {p:.1f}% (n={fwd_n})")
    print("wrote outputs to", HERE)


if __name__ == "__main__":
    main()
