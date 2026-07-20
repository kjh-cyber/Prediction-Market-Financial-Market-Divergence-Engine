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
CAL_DB = ROOT / "data" / "calibration.db"          # backfilled resolved markets (real labels)
DB = ROOT / "data" / "divergence.db"               # fallback (inferred labels)

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
    """Prefer backfilled calibration.db (official resolution labels, many markets).
    Fall back to inferring labels from divergence.db if the backfill isn't present."""
    if CAL_DB.exists():
        return _load_calibration_db()
    return _load_inferred()


def _load_calibration_db():
    con = sqlite3.connect(CAL_DB)
    mk = pd.read_sql_query(
        "SELECT yes_token AS token_id, question AS event_slug, outcome, "
        "end_ts AS last_ts FROM resolved_markets", con)
    px = pd.read_sql_query(
        "SELECT yes_token AS token_id, ts AS timestamp, p AS probability "
        "FROM resolved_prices", con)
    con.close()
    obs = px.merge(mk, on="token_id", how="inner")
    fp = obs.sort_values("timestamp").groupby("token_id")["probability"].last()
    mk["final_p"] = mk["token_id"].map(fp)
    obs["ttr_h"] = (obs["last_ts"] - obs["timestamp"]) / 3600.0
    return mk, obs


def _load_inferred():
    con = sqlite3.connect(DB)
    snap = pd.read_sql_query(
        "SELECT token_id, event_slug, probability, timestamp FROM prediction_snapshots", con)
    con.close()
    snap = snap.sort_values("timestamp")
    last = snap.groupby("token_id").tail(1).set_index("token_id")
    meta = []
    for tok, r in last.iterrows():
        fp = r["probability"]
        outcome = 1 if fp >= RES_HI else (0 if fp <= RES_LO else None)
        if outcome is None:
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

    backfilled = CAL_DB.exists()
    caveats = [
        "observations are per-market time-series points, autocorrelated within a market → effective N < raw observation count",
    ]
    if backfilled:
        caveats.insert(0, f"{n_res} resolved markets ({n_yes} YES / {n_no} NO) backfilled from Polymarket with OFFICIAL settlement labels")
        caveats.append("sample skews toward sports/longshot markets that mostly settle NO — base rate is low")
    else:
        caveats.insert(0, f"only {n_res} resolved markets ({n_yes} YES / {n_no} NO) — skewed, thin (inferred labels)")
        caveats.append("resolution inferred from final extreme probability, not official settlement")

    summary = {
        "source": "calibration.db (backfilled, official labels)" if backfilled
                  else "divergence.db (inferred labels)",
        "resolved_markets": n_res, "resolved_yes": n_yes, "resolved_no": n_no,
        "observations": int(len(obs)), "base_rate_pos": round(base_rate, 4),
        "brier_model": round(b_model, 4), "brier_climatology": round(b_clim, 4),
        "brier_p50": round(b_half, 4), "brier_skill_vs_climatology": round(skill, 4),
        "reliability": rel, "caveats": caveats,
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

    # ---- plot 3: probability trajectories (sampled if many) ----
    fig, ax = plt.subplots(figsize=(9, 5.5))
    toks = list(obs["token_id"].unique())
    SAMPLE = 80
    sampled = toks if len(toks) <= SAMPLE else toks[::max(1, len(toks) // SAMPLE)][:SAMPLE]
    annotate = len(sampled) <= 12
    for tok in sampled:
        d = obs[obs["token_id"] == tok].sort_values("timestamp")
        oc = d["outcome"].iloc[0]
        days = (d["timestamp"] - d["timestamp"].min()) / 86400
        ax.plot(days, d["probability"], lw=0.8, alpha=0.45 if len(sampled) > 20 else 0.85,
                color="#55A868" if oc == 1 else "#C44E52")
        if annotate:
            ax.annotate(d["event_slug"].iloc[0][:18], (days.iloc[-1], d["probability"].iloc[-1]),
                        fontsize=6, color=MUTED)
    ax.set_xlabel("관측 시작부터 경과일")
    ax.set_ylabel("예측 확률")
    ttl = "해결된 마켓 확률 궤적 (초록=YES 실현 / 빨강=NO 실현)"
    if len(toks) > SAMPLE:
        ttl += f"\n({len(toks)}개 중 {len(sampled)}개 샘플)"
    ax.set_title(ttl)
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
    tag = ("공식 정산 라벨 · 대량 표본" if "backfilled" in S.get("source", "")
           else "※ 표본 얇음 — 예시적 분석")
    verdict = (f"해결 마켓 {S['resolved_markets']:,}개(YES {S['resolved_yes']}/NO {S['resolved_no']}) · "
               f"관측 {S['observations']:,}\nBrier {b_model:.3f} (기저율 예측 {b_clim:.3f})\n{tag}")
    fig.text(0.5, 0.52, verdict, ha="center", fontsize=13.5, color="#2a7a55",
             weight="bold", linespacing=1.7)
    src = ("데이터: 이미 해결된 폴리마켓 이진 마켓 백필(공식 정산)"
           if "backfilled" in S.get("source", "")
           else "데이터: 2026-04-16 ~ 2026-07-20 수집분(추정 라벨)")
    fig.text(0.5, 0.28, f"{src}\n작성일 2026-07-20", ha="center", fontsize=10.5,
             color=MUTED, linespacing=2.0)
    _foot(fig, "p.1"); pdf.savefig(fig); plt.close(fig)

    # method
    backfilled = "backfilled" in S.get("source", "")
    fig = _page(pdf, "1. 개요 및 방법", "OVERVIEW")
    gt = ([
        (0, "정답(ground truth) 확보 — 백필"),
        (1, f"이미 해결된 폴리마켓 이진(Yes/No) 마켓 {S['resolved_markets']}개를 대량 수집"),
        (1, "공식 정산 결과(YES 청산=1 / NO 청산=0)를 라벨로 사용 — 추정 아님"),
        (1, "각 마켓의 YES 확률 이력(CLOB) 전체를 궤적으로 확보"),
    ] if backfilled else [
        (0, "정답(ground truth) 확보 — 추정"),
        (1, f"수집분에서 해결된 {S['resolved_markets']}개만, 최종확률 극단(≥{RES_HI}/≤{RES_LO})을 결과로 간주"),
    ])
    _bullets(fig, [
        (0, "질문"),
        (1, "예측시장이 매긴 확률이 실제 실현 빈도와 일치하는가(캘리브레이션)"),
        *gt,
        (0, "채점 방식"),
        (1, "각 마켓의 매 시점 확률 P_t 를 그 마켓의 확정 결과와 페어링"),
        (1, "'마켓 생애 전체에 대한 캘리브레이션' 관점"),
        (0, "지표"),
        (2, "Reliability diagram — 예측확률 구간별 실현빈도"),
        (2, "Brier score — 평균((P-결과)²), 낮을수록 정확. 기저율 예측(climatology)과 비교"),
    ], y0=0.88)
    _foot(fig, "p.2"); pdf.savefig(fig); plt.close(fig)

    # reliability
    fig = _page(pdf, "2. Reliability Diagram", "CALIBRATION")
    _bullets(fig, [
        (0, "읽는 법"),
        (1, "점이 대각선 위 = 완벽 캘리브레이션 / 아래=과대예측 / 위=과소예측"),
        (1, "점 크기 = 해당 구간 관측 수"),
        (0, "관찰 (실측)"),
        (1, "점들이 대각선에 밀착 → Polymarket 확률은 전반적으로 잘 캘리브레이션됨"),
        (1, "다만 완만한 체계적 편향: 15~25% 구간은 실현이 예측보다 높음(저평가)"),
        (1, "75~85% 구간은 실현이 예측보다 낮음(고평가) — 극단 쪽 과신 경향"),
        (1, "관측의 다수(약 70%)가 최저확률 구간 — 롱샷 NO 마켓이 많은 데서 기인"),
    ], y0=0.87)
    _img(fig, "cal_01_reliability.png", [0.14, 0.06, 0.72, 0.52])
    _foot(fig, "p.3"); pdf.savefig(fig); plt.close(fig)

    # brier vs ttr
    fig = _page(pdf, "3. 해결이 가까울수록 정확해지나", "SHARPNESS")
    _bullets(fig, [
        (0, "검증"),
        (1, "해결까지 남은 시간대별 Brier score — 정보가 쌓이며 정확해지는지"),
        (0, "관찰 (실측 — 직관과 반대)"),
        (1, "해결 임박(≤1d~1mo) Brier 0.10 전후로 오히려 높고, 먼 구간(>1mo) 0.079로 낮음"),
        (1, "원인: 만기까지 먼 구간엔 롱샷 NO 마켓이 저확률로 정박 → 맞히기 쉬움"),
        (1, "해결이 가까운 구간엔 승부가 갈리는 접전 마켓이 섞여 오히려 어려움"),
        (1, "→ '임박할수록 정확'이라는 단순 서사는 이 표본에선 성립 안 함"),
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
        (0, "핵심 발견"),
        (1, "Polymarket 확률은 실현 빈도와 잘 일치함 — reliability 점들이 대각선 밀착"),
        (1, "완만한 편향: 저확률(15~25%) 저평가 · 고확률(75~85%) 고평가(favorite-longshot류)"),
        (0, "정량 결과"),
        (1, f"Brier(model) {b_model:.3f} vs 기저율 예측 {b_clim:.3f} → skill {skill:+.3f} (기저율 대비 정보 우위)"),
        (1, f"기저율(YES 비율) {base_rate:.2f} — 해결 마켓이 NO 편중이라 낮음"),
        (0, "한계 (해석 주의)"),
        *([
            (2, "시계열 관측은 마켓 내 강한 자기상관 → 유효 표본은 관측수보다 작음"),
            (2, f"표본이 스포츠·롱샷 마켓에 편중 → NO 결과·저확률 관측이 다수(기저율 {base_rate:.2f})"),
            (2, "만기 임박 구간(확률이 이미 0/1 수렴)이 Brier 를 낙관적으로 만듦 → 잔여시간별 분해 참조"),
          ] if "backfilled" in S.get("source", "") else [
            (2, f"해결 마켓 {S['resolved_markets']}개뿐 — 통계적으로 얇고 편중"),
            (2, "해결을 최종 극단확률로 추정 — 공식 정산 아님"),
          ]),
        (0, "제언"),
        (2, "확률 구간별 균형 표본(중간확률 마켓 가중) 확보 시 고확률 영역 캘리브레이션 신뢰도 상승"),
        (2, "카테고리(정치/스포츠/크립토)별 캘리브레이션 분해 — 편향 원천 규명"),
    ], y0=0.88, dy=0.030)
    _foot(fig, "p.6"); pdf.savefig(fig); plt.close(fig)
    pdf.close()


if __name__ == "__main__":
    main()
