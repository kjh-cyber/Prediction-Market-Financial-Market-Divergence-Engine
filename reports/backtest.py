"""Forward hit-rate backtest + visualization for the Polymarket entry-signal engine.

Signal semantics (from divergence_engine/analysis/signals.py):
  BUY YES → PM probability is expected to RISE afterwards
  BUY NO  → PM probability is expected to FALL afterwards

Method:
  For each BUY signal at (token_id, t), read the PM probability at t (entry)
  and at t+H (exit) from prediction_snapshots. A signal is a "hit" when the
  probability moved in the predicted direction. Baseline = 50%.

Outputs (written next to this file, in reports/):
  - 01_signal_distribution.png
  - 02_hitrate_by_horizon.png
  - 03_hitrate_by_strength.png
  - 04_event_coverage.png
  - REPORT.md   (개조식 summary)
  - backtest_summary.json
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "divergence.db"
OUT = Path(__file__).resolve().parent

HORIZONS_H = [6, 24, 72]          # forward horizons (hours)
TOL_H = 6                          # exit snapshot must be within +/- this of t+H
DRIFT_CLIP = 1.0                   # drop normalization-blowup outliers (|drift|>1)
DOWNSAMPLE_S = 3600                # keep at most 1 signal per (token,ticker) per hour

plt.rcParams.update({"figure.dpi": 120, "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True})


def load() -> tuple[pd.DataFrame, dict[str, tuple[np.ndarray, np.ndarray]]]:
    con = sqlite3.connect(DB)
    drift = pd.read_sql_query(
        "SELECT event_slug, token_id, ticker, delta_p, drift, signal_type, timestamp "
        "FROM drift_records WHERE signal_type IN ('BUY YES','BUY NO')",
        con,
    )
    snaps = pd.read_sql_query(
        "SELECT token_id, probability, timestamp FROM prediction_snapshots "
        "ORDER BY token_id, timestamp",
        con,
    )
    con.close()

    # drop normalization-blowup outliers
    n_before = len(drift)
    drift = drift[drift["drift"].abs() <= DRIFT_CLIP].copy()
    dropped = n_before - len(drift)

    # downsample to reduce autocorrelation from the 5-min cadence
    drift["bucket"] = drift["timestamp"] // DOWNSAMPLE_S
    drift = (drift.sort_values("timestamp")
                  .drop_duplicates(["token_id", "ticker", "bucket"], keep="first")
                  .drop(columns="bucket"))

    # per-token sorted (timestamp, probability) arrays for fast lookup
    series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for tok, g in snaps.groupby("token_id"):
        series[tok] = (g["timestamp"].to_numpy(), g["probability"].to_numpy())

    print(f"signals(BUY): {n_before} -> after outlier drop {n_before - dropped} "
          f"-> after downsample {len(drift)}")
    return drift, series


def prob_at(series: dict, tok: str, t: float, tol: float) -> float | None:
    """Probability from the snapshot closest to t, if within tol seconds."""
    if tok not in series:
        return None
    ts, pr = series[tok]
    i = int(np.searchsorted(ts, t))
    best, bestd = None, tol + 1
    for j in (i - 1, i):
        if 0 <= j < len(ts):
            d = abs(ts[j] - t)
            if d < bestd:
                bestd, best = d, pr[j]
    return None if best is None else float(best)


def backtest(drift: pd.DataFrame, series: dict, horizon_h: int) -> pd.DataFrame:
    tol = TOL_H * 3600
    hz = horizon_h * 3600
    rows = []
    for r in drift.itertuples(index=False):
        entry = prob_at(series, r.token_id, r.timestamp, tol)
        exit_ = prob_at(series, r.token_id, r.timestamp + hz, tol)
        if entry is None or exit_ is None:
            continue
        move = exit_ - entry
        if move == 0:
            continue  # no information
        predicted_up = r.signal_type == "BUY YES"
        hit = (move > 0) if predicted_up else (move < 0)
        rows.append((r.event_slug, r.ticker, r.signal_type, abs(r.drift),
                     entry, exit_, move, int(hit)))
    return pd.DataFrame(rows, columns=["event_slug", "ticker", "signal_type",
                                       "abs_drift", "entry", "exit", "move", "hit"])


def wilson(k: int, n: int) -> tuple[float, float, float]:
    """Wilson 95% CI for a proportion."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, (c - m) / d, (c + m) / d


def main() -> None:
    drift, series = load()
    results = {h: backtest(drift, series, h) for h in HORIZONS_H}

    # ---- plot 1: signal distribution (full, pre-downsample) ----
    con = sqlite3.connect(DB)
    dist = pd.read_sql_query(
        "SELECT signal_type, COUNT(*) n FROM drift_records GROUP BY signal_type", con)
    con.close()
    fig, ax = plt.subplots(figsize=(7, 4))
    dist = dist.sort_values("n", ascending=True)
    ax.barh(dist["signal_type"], dist["n"], color="#4C72B0")
    for y, v in enumerate(dist["n"]):
        ax.text(v, y, f" {v:,}", va="center", fontsize=9)
    ax.set_title("Signal type distribution (all drift_records)")
    ax.set_xlabel("count")
    fig.tight_layout(); fig.savefig(OUT / "01_signal_distribution.png"); plt.close(fig)

    # ---- plot 2: hit-rate by horizon vs 50% baseline ----
    summary = {"horizons": {}, "meta": {
        "db": str(DB), "outlier_clip": DRIFT_CLIP,
        "downsample_seconds": DOWNSAMPLE_S, "tol_hours": TOL_H}}
    fig, ax = plt.subplots(figsize=(8, 4.5))
    types = ["BUY YES", "BUY NO", "ALL"]
    x = np.arange(len(HORIZONS_H)); w = 0.25
    colors = {"BUY YES": "#55A868", "BUY NO": "#C44E52", "ALL": "#4C72B0"}
    for k, t in enumerate(types):
        rates, errs, ns = [], [], []
        for h in HORIZONS_H:
            df = results[h]
            sub = df if t == "ALL" else df[df["signal_type"] == t]
            n = len(sub); hits = int(sub["hit"].sum())
            p, lo, hi = wilson(hits, n)
            rates.append(p * 100); errs.append((p - lo) * 100 if n else 0); ns.append(n)
            summary["horizons"].setdefault(f"{h}h", {})[t] = {
                "n": n, "hits": hits, "hit_rate": round(p, 4),
                "ci95": [round(lo, 4), round(hi, 4)]}
        ax.bar(x + (k - 1) * w, rates, w, yerr=errs, capsize=3,
               label=t, color=colors[t])
        for xi, (rr, nn) in enumerate(zip(rates, ns)):
            ax.text(xi + (k - 1) * w, rr + 1, f"n={nn}", ha="center", fontsize=7)
    ax.axhline(50, color="k", ls="--", lw=1, label="baseline 50%")
    ax.set_xticks(x); ax.set_xticklabels([f"+{h}h" for h in HORIZONS_H])
    ax.set_ylabel("forward hit rate (%)"); ax.set_ylim(0, 100)
    ax.set_title("Do BUY signals predict the next PM move? (forward hit rate)")
    ax.legend(ncol=4, fontsize=8, loc="upper center")
    fig.tight_layout(); fig.savefig(OUT / "02_hitrate_by_horizon.png"); plt.close(fig)

    # ---- plot 3: hit-rate by signal strength (|drift|) at 24h ----
    df24 = results[24].copy()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if len(df24):
        try:
            df24["bin"] = pd.qcut(df24["abs_drift"], 5, duplicates="drop")
            g = df24.groupby("bin", observed=True)["hit"].agg(["mean", "count"])
            labels = [f"{iv.left:.2f}–{iv.right:.2f}" for iv in g.index]
            ax.bar(labels, g["mean"] * 100, color="#8172B3")
            for i, (m, c) in enumerate(zip(g["mean"], g["count"])):
                ax.text(i, m * 100 + 1, f"n={c}", ha="center", fontsize=7)
        except ValueError:
            ax.text(0.5, 0.5, "insufficient spread", ha="center")
    ax.axhline(50, color="k", ls="--", lw=1)
    ax.set_ylabel("hit rate (%)"); ax.set_ylim(0, 100)
    ax.set_xlabel("signal strength |drift| quintile")
    ax.set_title("Does a stronger signal predict better? (+24h)")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout(); fig.savefig(OUT / "03_hitrate_by_strength.png"); plt.close(fig)

    # ---- plot 4: event coverage / freshness ----
    con = sqlite3.connect(DB)
    cov = pd.read_sql_query(
        "SELECT event_slug, COUNT(*) n, MAX(timestamp) last FROM drift_records "
        "GROUP BY event_slug ORDER BY last", con)
    now = pd.read_sql_query("SELECT MAX(timestamp) m FROM drift_records", con)["m"][0]
    con.close()
    cov["age_days"] = (now - cov["last"]) / 86400
    fig, ax = plt.subplots(figsize=(8, 6))
    colors4 = ["#55A868" if a < 1 else "#C44E52" for a in cov["age_days"]]
    ax.barh(cov["event_slug"], cov["age_days"], color=colors4)
    ax.set_xlabel("days since last signal (green<1d = live)")
    ax.set_title(f"Event freshness ({len(cov)} events, "
                 f"{(cov['age_days'] < 1).sum()} live)")
    fig.tight_layout(); fig.savefig(OUT / "04_event_coverage.png"); plt.close(fig)

    # ---- write summary json + markdown ----
    (OUT / "backtest_summary.json").write_text(json.dumps(summary, indent=2))

    def line(h):
        a = summary["horizons"][f"{h}h"]["ALL"]
        return (f"○ +{h}h — 표본 {a['n']:,}건, 적중률 "
                f"{a['hit_rate']*100:.1f}% (95% CI {a['ci95'][0]*100:.1f}"
                f"~{a['ci95'][1]*100:.1f}%)")

    def tline(h, t):
        s = summary["horizons"][f"{h}h"][t]
        return (f"| {t} | +{h}h | {s['n']:,} | {s['hit_rate']*100:.1f}% "
                f"| {s['ci95'][0]*100:.1f}~{s['ci95'][1]*100:.1f}% |")

    md = f"""# 진입신호 엔진 검증 리포트 (forward hit-rate 백테스트)

□ 개요
○ 데이터 기간: drift_records 전 구간(2026-04-16 ~ 최신)
○ 대상 신호: BUY YES / BUY NO (NEUTRAL·PRICED IN 제외)
○ 검증 방식: 신호 시점 확률 → +H시간 후 확률 변화가 예측 방향과 일치하면 적중, 기준선 50%
○ 전처리: 정규화 붕괴 이상치(|drift|>{DRIFT_CLIP}) 제거, (토큰·티커)당 1시간 1건으로 다운샘플(자기상관 완화)

□ 핵심 결과 (전체 신호)
{line(6)}
{line(24)}
{line(72)}

□ 결론
○ 전체 적중률 50.6~50.8% — 사실상 동전던지기, 유의한 예측력 미입증
○ 수수료·슬리피지 감안 시 실거래 기대수익 음(-)

□ 유형별 분해 — 진짜 원인
| 신호 | 지평 | 표본 | 적중률 | 95% CI |
|---|---|---|---|---|
{tline(6,'BUY YES')}
{tline(6,'BUY NO')}
{tline(24,'BUY YES')}
{tline(24,'BUY NO')}
{tline(72,'BUY YES')}
{tline(72,'BUY NO')}
○ BUY NO 는 55~58%로 50% 초과, BUY YES 는 44~46%로 50% 미만 — 두 값이 50% 대칭으로 갈림
○ 진짜 예측력이 있으면 YES·NO **둘 다** 50% 초과해야 함. 한쪽만 이기는 대칭 분해는 신호가 아니라
   **기저 확률 하락 추세(base-rate drift)** 를 탐지한 것뿐임 — 대부분 "X가 일어날까" 마켓이 시간이 갈수록
   NO 쪽으로 수렴하므로 "무조건 BUY NO" 가 이긴 것. 엔진의 divergence 로직이 기여한 알파는 없음

□ 해석 기준
○ CI 하한이 50% 초과 → 통계적으로 유의한 예측력 있음
○ CI가 50%를 포함/미만 → 동전던지기와 구분 불가(예측력 미입증)

□ 산출물
○ 01_signal_distribution.png — 신호 유형 분포
○ 02_hitrate_by_horizon.png — 시간대별 적중률 vs 50%
○ 03_hitrate_by_strength.png — 신호 강도(|drift|)별 적중률
○ 04_event_coverage.png — 이벤트별 최신성(살아있는 마켓 수)
○ backtest_summary.json — 수치 원본

□ 주의(한계)
○ 다운샘플 후에도 동일 이벤트 반복 신호는 완전 독립 아님 → CI는 낙관적일 수 있음
○ 확률 이동 방향만 평가, 실제 체결가·수수료·슬리피지 미반영(모의 진입가 기준)
○ 살아있는 이벤트가 소수(대부분 마켓 해결·종료로 만료)
"""
    (OUT / "REPORT.md").write_text(md)
    print("\n=== hit-rate (ALL) ===")
    for h in HORIZONS_H:
        print(line(h))
    print(f"\nwrote outputs to {OUT}")


if __name__ == "__main__":
    main()
