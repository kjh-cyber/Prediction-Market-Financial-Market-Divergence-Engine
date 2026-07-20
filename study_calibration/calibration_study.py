"""Polymarket calibration study — do stated probabilities match realized frequencies?

Ground truth: only markets that RESOLVED within the collected window can be scored.
A token is treated as resolved when its final probability is extreme
(>=0.95 → outcome YES=1, <=0.05 → outcome NO=0); open/uncertain tokens are excluded.

Because only a handful of markets resolved (skewed toward NO), we pool the full
time-series of each resolved market: every hourly snapshot (P_t) is paired with that
market's realized outcome. This is a standard "calibration over the market's life"
view — illustrative, NOT a conclusive reliability estimate (see caveats in the doc).

Outputs (study_calibration/):
  cal_01_reliability.png · cal_02_brier_vs_ttr.png · cal_03_trajectories.png
  calibration_summary.json · calibration_report.pdf
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = ROOT / "data" / "divergence.db"

RES_HI, RES_LO = 0.95, 0.05          # resolution thresholds
BINS = np.linspace(0, 1, 11)          # reliability bins (deciles)
HOURLY = True

FONT = Path.home() / ".local/share/fonts/NanumGothic.ttf"
if FONT.exists():
    fm.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams.update({"figure.dpi": 120, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.axisbelow": True})
INK, MUTED = "#1a1a2e", "#555"
A4 = (8.27, 11.69)


def load_resolved():
    con = sqlite3.connect(DB)
    snap = pd.read_sql_query(
        "SELECT token_id, event_slug, probability, timestamp FROM prediction_snapshots", con)
    con.close()
    # per-token final prob + last ts
    snap = snap.sort_values("timestamp")
    last = snap.groupby("token_id").tail(1).set_index("token_id")
    meta = []
    for tok, r in last.iterrows():
        fp = r["probability"]
        if fp >= RES_HI:
            outcome = 1
        elif fp <= RES_LO:
            outcome = 0
        else:
            continue
        meta.append({"token_id": tok, "event_slug": r["event_slug"],
                     "outcome": outcome, "final_p": fp, "last_ts": r["timestamp"]})
    mdf = pd.DataFrame(meta)
    obs = snap.merge(mdf[["token_id", "event_slug", "outcome", "last_ts"]],
                     on=["token_id", "event_slug"], how="inner")
    if HOURLY:
        obs["hour"] = (obs["timestamp"] // 3600) * 3600
        obs = obs.sort_values("timestamp").groupby(["token_id", "hour"]).tail(1)
    obs["ttr_h"] = (obs["last_ts"] - obs["timestamp"]) / 3600.0
    return mdf, obs


def brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def main():
    mdf, obs = load_resolved()
    n_res = len(mdf)
    n_yes = int((mdf["outcome"] == 1).sum())
    n_no = int((mdf["outcome"] == 0).sum())

    p = obs["probability"].to_numpy()
    y = obs["outcome"].to_numpy()
    base_rate = float(np.mean(y))

    # ---- reliability bins ----
    idx = np.clip(np.digitize(p, BINS) - 1, 0, len(BINS) - 2)
    rel = []
    for b in range(len(BINS) - 1):
        m = idx == b
        if m.sum() == 0:
            continue
        rel.append({"bin_lo": float(BINS[b]), "bin_hi": float(BINS[b + 1]),
                    "n": int(m.sum()), "mean_pred": float(p[m].mean()),
                    "frac_pos": float(y[m].mean())})
    rel_df = pd.DataFrame(rel)

    b_model = brier(p, y)
    b_clim = brier(np.full_like(p, base_rate), y)   # always predict base rate
    b_half = brier(np.full_like(p, 0.5), y)
    skill = 1 - b_model / b_clim if b_clim > 0 else float("nan")

    summary = {
        "resolved_markets": n_res, "resolved_yes": n_yes, "resolved_no": n_no,
        "observations": int(len(obs)), "base_rate_pos": round(base_rate, 4),
        "brier_model": round(b_model, 4), "brier_climatology": round(b_clim, 4),
        "brier_p50": round(b_half, 4), "brier_skill_vs_climatology": round(skill, 4),
        "reliability": rel,
        "per_market": mdf.assign(
            n_obs=mdf["token_id"].map(obs.groupby("token_id").size())).to_dict("records"),
        "caveats": [
            f"only {n_res} resolved markets ({n_yes} YES / {n_no} NO) — skewed, thin",
            "observations are hourly time-series points, heavily autocorrelated within a market",
            "resolution inferred from final extreme probability, not official settlement",
        ],
    }
    (HERE / "calibration_summary.json").write_text(json.dumps(summary, indent=2, default=float))

    # ---- plot 1: reliability diagram ----
    fig, ax = plt.subplots(figsize=(7, 6.5))
    ax.plot([0, 1], [0, 1], "--", color="#888", label="완벽 캘리브레이션")
    sizes = 20 + 380 * (rel_df["n"] / rel_df["n"].max())
    sc = ax.scatter(rel_df["mean_pred"], rel_df["frac_pos"], s=sizes,
                    c=rel_df["frac_pos"], cmap="RdYlGn", edgecolor="k",
                    vmin=0, vmax=1, zorder=3)
    for _, r in rel_df.iterrows():
        ax.annotate(f"n={int(r['n']):,}", (r["mean_pred"], r["frac_pos"]),
                    textcoords="offset points", xytext=(6, 6), fontsize=7)
    ax.axhline(base_rate, color="#C44E52", lw=0.8, ls=":", label=f"기저율 {base_rate:.2f}")
    ax.set_xlabel("예측 확률 (Polymarket)")
    ax.set_ylabel("실제 실현 빈도")
    ax.set_title("Reliability Diagram — 예측 확률 vs 실현 빈도\n"
                 "(점 크기=관측수, 대각선 위=완벽)")
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout(); fig.savefig(HERE / "cal_01_reliability.png"); plt.close(fig)

    # ---- plot 2: Brier vs time-to-resolution ----
    ttr_bins = [0, 24, 72, 168, 336, 720, 1e9]
    ttr_lab = ["≤1d", "1–3d", "3–7d", "1–2wk", "2wk–1mo", ">1mo"]
    obs2 = obs.copy()
    obs2["tb"] = pd.cut(obs2["ttr_h"], ttr_bins, labels=ttr_lab, right=False)
    g = obs2.groupby("tb", observed=True).apply(
        lambda d: pd.Series({"brier": brier(d["probability"], d["outcome"]),
                             "n": len(d)}), include_groups=False)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(g.index.astype(str), g["brier"], color="#4C72B0")
    for i, (br, nn) in enumerate(zip(g["brier"], g["n"])):
        ax.text(i, br + 0.003, f"{br:.3f}\nn={int(nn)}", ha="center", fontsize=7.5)
    ax.axhline(b_clim, color="#C44E52", ls="--", lw=1, label=f"기저율 예측 Brier {b_clim:.3f}")
    ax.set_ylabel("Brier score (낮을수록 정확)")
    ax.set_xlabel("해결까지 남은 시간 (time-to-resolution)")
    ax.set_title("해결이 가까울수록 정확해지나?  Brier vs 잔여시간")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(HERE / "cal_02_brier_vs_ttr.png"); plt.close(fig)

    # ---- plot 3: probability trajectories ----
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for tok, d in obs.groupby("token_id"):
        d = d.sort_values("timestamp")
        ev = d["event_slug"].iloc[0]
        oc = d["outcome"].iloc[0]
        days = (d["timestamp"] - d["timestamp"].min()) / 86400
        ax.plot(days, d["probability"], lw=1.0, alpha=0.8,
                color="#55A868" if oc == 1 else "#C44E52")
        ax.annotate(ev[:18], (days.iloc[-1], d["probability"].iloc[-1]),
                    fontsize=6, color=MUTED)
    ax.set_xlabel("관측 시작부터 경과일")
    ax.set_ylabel("예측 확률")
    ax.set_title("해결된 마켓 확률 궤적 (초록=YES 실현 / 빨강=NO 실현)")
    ax.set_ylim(-0.02, 1.02)
    fig.tight_layout(); fig.savefig(HERE / "cal_03_trajectories.png"); plt.close(fig)

    build_pdf(summary, rel_df, base_rate, b_model, b_clim, skill)
    print(f"resolved markets: {n_res} ({n_yes} YES / {n_no} NO), obs {len(obs):,}")
    print(f"Brier model {b_model:.4f} vs climatology {b_clim:.4f} (skill {skill:+.3f})")
    print("wrote outputs to", HERE)


# ---------- PDF ----------
def _page(pdf, title, kicker):
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.text(0.08, 0.955, kicker, fontsize=9, color="#3a7", weight="bold")
    fig.text(0.08, 0.925, title, fontsize=18, color=INK, weight="bold")
    fig.add_artist(plt.Line2D([0.08, 0.92], [0.905, 0.905], color="#3a7", lw=2,
                   transform=fig.transFigure))
    return fig


def _bullets(fig, lines, y0=0.86, dy=0.030, size=11):
    marks = {0: "□", 1: "  ○", 2: "     -", 3: "        •"}
    y = y0
    for lvl, txt in lines:
        fig.text(0.08, y, f"{marks[lvl]} {txt}", va="top",
                 fontsize=size if lvl == 0 else size - 0.5,
                 color=INK if lvl == 0 else "#2a2a3e",
                 weight="bold" if lvl == 0 else "normal")
        y -= dy * (1.25 if lvl == 0 else 1.0)


def _img(fig, png, rect):
    ax = fig.add_axes(rect); ax.imshow(mpimg.imread(str(HERE / png))); ax.axis("off")


def _foot(fig, n):
    fig.text(0.5, 0.03, f"Polymarket 캘리브레이션 연구  ·  {n}", ha="center",
             fontsize=8, color="#999")


def build_pdf(S, rel_df, base_rate, b_model, b_clim, skill):
    pdf = PdfPages(HERE / "calibration_report.pdf")

    # cover
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.add_artist(plt.Rectangle((0, 0.72), 1, 0.28, color="#143a2e",
                   transform=fig.transFigure))
    fig.text(0.5, 0.855, "Polymarket 예측시장", ha="center", fontsize=16,
             color="#9fe0c0", weight="bold")
    fig.text(0.5, 0.79, "확률 캘리브레이션 연구", ha="center", fontsize=26,
             color="white", weight="bold")
    fig.text(0.5, 0.745, "— 60%라고 한 사건은 실제로 60% 일어나는가 —", ha="center",
             fontsize=12, color="#c7e8d8")
    verdict = (f"해결 마켓 {S['resolved_markets']}개(YES {S['resolved_yes']}/NO {S['resolved_no']}) · "
               f"관측 {S['observations']:,}\nBrier {b_model:.3f} (기저율 예측 {b_clim:.3f})\n"
               f"※ 표본 얇음 — 예시적 분석")
    fig.text(0.5, 0.52, verdict, ha="center", fontsize=13.5, color="#2a7a55",
             weight="bold", linespacing=1.7)
    fig.text(0.5, 0.28, "데이터: 2026-04-16 ~ 2026-07-20 · 5분 주기 수집분\n작성일 2026-07-20",
             ha="center", fontsize=10.5, color=MUTED, linespacing=2.0)
    _foot(fig, "p.1"); pdf.savefig(fig); plt.close(fig)

    # method
    fig = _page(pdf, "1. 개요 및 방법", "OVERVIEW")
    _bullets(fig, [
        (0, "질문"),
        (1, "예측시장이 매긴 확률이 실제 실현 빈도와 일치하는가(캘리브레이션)"),
        (0, "정답(ground truth) 확보"),
        (1, f"수집 기간 내 해결된 마켓만 채점 가능 — 최종확률 극단(≥{RES_HI}=YES, ≤{RES_LO}=NO)을 결과로 간주"),
        (1, f"미해결(중간확률) 마켓 {19 - S['resolved_markets']}개는 제외"),
        (0, "표본이 얇아 시계열 풀링"),
        (1, "해결 마켓의 매 시점 확률 P_t 를 그 마켓의 확정 결과와 페어링 → 관측 다수 확보"),
        (1, "'마켓 생애 전체에 대한 캘리브레이션' 관점 — 표준적이나 결정적 추정 아님"),
        (0, "지표"),
        (2, "Reliability diagram — 예측확률 구간별 실현빈도"),
        (2, "Brier score — 평균((P-결과)²), 낮을수록 정확. 기저율 예측(climatology)과 비교"),
    ], y0=0.86)
    _foot(fig, "p.2"); pdf.savefig(fig); plt.close(fig)

    # reliability
    fig = _page(pdf, "2. Reliability Diagram", "CALIBRATION")
    _bullets(fig, [
        (0, "읽는 법"),
        (1, "점이 대각선 위 = 완벽 캘리브레이션 / 아래=과대예측 / 위=과소예측"),
        (1, "점 크기 = 해당 구간 관측 수"),
        (0, "관찰"),
        (1, "관측 대부분이 저확률 구간에 몰림 (해결 마켓 다수가 NO로 수렴)"),
        (1, "고확률 구간은 관측 희소 → 그 영역 캘리브레이션은 신뢰 낮음"),
    ], y0=0.87)
    _img(fig, "cal_01_reliability.png", [0.14, 0.06, 0.72, 0.52])
    _foot(fig, "p.3"); pdf.savefig(fig); plt.close(fig)

    # brier vs ttr
    fig = _page(pdf, "3. 해결이 가까울수록 정확해지나", "SHARPNESS")
    _bullets(fig, [
        (0, "검증"),
        (1, "해결까지 남은 시간대별 Brier score — 정보가 쌓이며 정확해지는지"),
        (0, "기대"),
        (1, "잔여시간이 짧을수록(해결 임박) Brier 가 낮아지면 시장이 정보를 반영한다는 신호"),
    ], y0=0.87)
    _img(fig, "cal_02_brier_vs_ttr.png", [0.10, 0.30, 0.80, 0.42])
    _foot(fig, "p.4"); pdf.savefig(fig); plt.close(fig)

    # trajectories
    fig = _page(pdf, "4. 해결 마켓 확률 궤적", "TRAJECTORIES")
    _bullets(fig, [
        (0, "궤적"),
        (1, "초록=YES 실현 / 빨강=NO 실현. 대부분 시간이 갈수록 0 또는 1로 수렴"),
        (1, "NO 수렴이 압도적 — 앞선 예측력 분석의 'base-rate NO drift'와 동일 현상"),
    ], y0=0.87)
    _img(fig, "cal_03_trajectories.png", [0.07, 0.28, 0.86, 0.44])
    _foot(fig, "p.5"); pdf.savefig(fig); plt.close(fig)

    # conclusion
    fig = _page(pdf, "5. 결론 · 한계", "CONCLUSION")
    _bullets(fig, [
        (0, "정량 결과"),
        (1, f"Brier(model) {b_model:.3f} vs 기저율 예측 {b_clim:.3f} → skill {skill:+.3f}"),
        (1, "skill>0 이면 시장이 기저율 대비 정보 우위, ≤0 이면 우위 없음"),
        (1, f"기저율(YES 비율) {base_rate:.2f} — 해결 마켓이 NO 편중이라 낮음"),
        (0, "한계 (해석 주의)"),
        (2, f"해결 마켓 {S['resolved_markets']}개뿐(YES {S['resolved_yes']}/NO {S['resolved_no']}) — 통계적으로 얇고 편중"),
        (2, "시계열 관측은 마켓 내 강한 자기상관 → 유효 표본은 관측수보다 훨씬 작음"),
        (2, "해결을 최종 극단확률로 추정 — 공식 정산 아님(수집 중단 시점 확률일 수 있음)"),
        (0, "제언"),
        (2, "제대로 하려면 해결 마켓 수를 늘려야 함 — 만기 임박·이미 해결된 마켓 다수 재수집"),
        (2, "엔진을 캘리브레이션 수집 모드(해결 결과 라벨 저장)로 소규모 재가동하는 방안"),
    ], y0=0.88, dy=0.030)
    _foot(fig, "p.6"); pdf.savefig(fig); plt.close(fig)
    pdf.close()


if __name__ == "__main__":
    main()
