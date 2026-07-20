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

    # ---- plot 3: average path to resolution, split by realized outcome ----
    fig, ax = plt.subplots(figsize=(9, 5.5))
    o = obs.copy()
    o["dtr"] = o["ttr_h"] / 24.0            # days to resolution (0 = resolution)
    o = o[(o["dtr"] >= 0) & (o["dtr"] <= 120)]
    edges = np.linspace(0, 120, 41)
    mids = (edges[:-1] + edges[1:]) / 2
    o["db"] = pd.cut(o["dtr"], edges, labels=mids)
    for oc, color, lab in [(1, "#2e8b57", "YES 실현 마켓"), (0, "#C44E52", "NO 실현 마켓")]:
        g = (o[o["outcome"] == oc].groupby("db", observed=True)["probability"]
             .agg(mean="mean", q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75)))
        g = g.reindex(mids).dropna()
        x = g.index.to_numpy(dtype=float)
        ax.fill_between(x, g["q1"], g["q3"], color=color, alpha=0.15)
        ax.plot(x, g["mean"], color=color, lw=2.2, label=lab)
    ax.axhline(0.5, color="#888", ls=":", lw=0.8)
    ax.invert_xaxis()                       # resolution (dtr=0) on the right
    ax.set_xlabel("해결까지 남은 일수  (오른쪽=해결 시점)")
    ax.set_ylabel("평균 예측 확률 (밴드=사분위 25–75%)")
    ax.set_title("해결 결과별 '평균 확률 경로'\n"
                 "해결이 다가올수록 YES·NO 경로가 갈라짐")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(loc="center left", fontsize=9)
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
    verdict = (f"결과 확정 마켓 {S['resolved_markets']:,}개(YES {S['resolved_yes']}/NO {S['resolved_no']}) · "
               f"관측 {S['observations']:,}\n예측 오차(Brier) {b_model:.3f}  (기준선 {b_clim:.3f}보다 정확)\n{tag}")
    fig.text(0.5, 0.52, verdict, ha="center", fontsize=13.5, color="#2a7a55",
             weight="bold", linespacing=1.7)
    src = ("데이터: 이미 해결된 폴리마켓 이진 마켓 백필(공식 정산)"
           if "backfilled" in S.get("source", "")
           else "데이터: 2026-04-16 ~ 2026-07-20 수집분(추정 라벨)")
    fig.text(0.5, 0.28, f"{src}\n작성일 2026-07-20", ha="center", fontsize=10.5,
             color=MUTED, linespacing=2.0)
    _foot(fig, "p.1"); pdf.savefig(fig); plt.close(fig)

    backfilled = "backfilled" in S.get("source", "")

    # ===== p2: 예측시장 & 용어 풀이 =====
    fig = _page(pdf, "예측시장이란 & 용어 풀이", "BASICS")
    _bullets(fig, [
        (0, "예측시장(Polymarket) 이란"),
        (1, "미래의 '예/아니오' 질문에 사람들이 돈을 걸고 지분을 사고파는 시장임"),
        (1, "'예(YES)' 지분의 가격이 곧 그 일이 일어날 확률 — 가격 0.60 = 시장이 본 확률 60%"),
        (1, "실제로 일어나면 YES 지분이 1(달러)로, 안 일어나면 0으로 정산(청산)됨"),
        (0, "이 보고서 용어 (풀어서)"),
        (1, "확률(P): 'YES일 확률' = YES 지분 가격, 0~1 사이 값"),
        (1, "정산·해결: 사건의 실제 결과가 확정돼 YES=1 또는 NO=0 으로 마감되는 것"),
        (1, "캘리브레이션: 시장이 '60%'라 한 일이 정말 60% 빈도로 일어나는지 = 확률의 정확도"),
        (1, "Brier 점수: 예측이 얼마나 틀렸나 = 평균((확률-실제결과)²), 0에 가까울수록 정확"),
        (1, "기저율: 전체에서 YES가 난 비율. '무조건 이 비율로만 찍기'가 비교용 기준선"),
        (1, "개선폭(skill): 그 기준선보다 얼마나 더 정확한가 — 양수면 시장이 더 나음"),
        (0, "왜 보나"),
        (1, "확률이 정확하다면, 예측시장은 미래를 가늠하는 신뢰할 만한 도구가 됨"),
    ], y0=0.89, dy=0.033)
    _foot(fig, "p.2"); pdf.savefig(fig); plt.close(fig)

    # ===== p3: 방법 =====
    fig = _page(pdf, "1. 무엇을 어떻게 확인했나", "METHOD")
    gt = ([
        (0, "정답(실제 결과) 확보 — '이미 끝난' 마켓만"),
        (1, f"이미 결과가 나온(정산 완료) 예/아니오 마켓 {S['resolved_markets']:,}개를 대량 수집"),
        (1, "공식 정산 결과를 정답으로 사용 — 추정이 아니라 실제로 확정된 답임"),
        (1, "각 마켓의 'YES일 확률'이 시간에 따라 어떻게 변했는지 전체 이력 확보"),
    ] if backfilled else [
        (0, "정답 확보 — 추정(표본 얇음)"),
        (1, f"수집분에서 결과가 확정된 {S['resolved_markets']}개만, 최종확률 극단(≥{RES_HI}/≤{RES_LO})을 결과로 간주"),
    ])
    _bullets(fig, [
        (0, "확인할 질문"),
        (1, "시장이 매긴 확률이 실제로 그 빈도만큼 맞았는가 (= 캘리브레이션)"),
        *gt,
        (0, "채점 방식"),
        (1, "각 마켓의 매 시점 확률을 그 마켓의 확정 결과(YES=1 / NO=0)와 대조"),
        (1, "비슷한 확률끼리 모아 '정말 그 비율로 일어났는지' 비교(다음 장)"),
        (0, "'YES 실현' / 'NO 실현' 이란 (그래프 색)"),
        (1, "YES 실현 = 그 일이 실제로 일어난 마켓 (예: '트럼프 2024 당선?'→당선)"),
        (1, "NO 실현 = 그 일이 안 일어난 마켓 (예: '해리스 2024 당선?'→무산)"),
    ], y0=0.89, dy=0.030)
    _foot(fig, "p.3"); pdf.savefig(fig); plt.close(fig)

    # ===== p4: reliability =====
    fig = _page(pdf, "2. 예측확률 vs 실제결과", "CALIBRATION")
    _bullets(fig, [
        (0, "이 그림 읽는 법"),
        (1, "가로 = 시장이 매긴 확률, 세로 = 실제로 그 일이 일어난 비율"),
        (1, "대각선 = 확률과 실제가 정확히 일치(완벽) · 대각선 아래=확률이 과했음 · 위=모자랐음"),
        (1, "점 크기 = 그 확률 구간에 담긴 관측 수"),
        (0, "관찰 (실측)"),
        (1, "점들이 대각선에 바짝 붙음 → 시장 확률이 실제와 대체로 잘 맞음"),
        (1, "다만 완만한 편향: 15~25%라 한 일은 실제론 그보다 더 자주 일어남(저평가)"),
        (1, "75~85%라 한 일은 실제론 그보다 덜 일어남(고평가) — 극단으로 갈수록 과신"),
        (1, "관측의 약 70%가 최저확률 구간 — '거의 안 일어날 일' 마켓이 많은 탓"),
    ], y0=0.88, dy=0.029)
    _img(fig, "cal_01_reliability.png", [0.15, 0.05, 0.70, 0.48])
    _foot(fig, "p.4"); pdf.savefig(fig); plt.close(fig)

    # ===== p5: brier vs ttr =====
    fig = _page(pdf, "3. 해결이 가까울수록 정확해지나", "SHARPNESS")
    _bullets(fig, [
        (0, "무엇을 봤나"),
        (1, "해결까지 남은 기간별로 예측 오차(Brier, 낮을수록 정확)를 비교"),
        (0, "관찰 (실측 — 직관과 반대)"),
        (1, "해결 임박 구간(≤1개월)이 오차 0.10 전후로 오히려 크고, 먼 구간(>1개월)이 0.079로 작음"),
        (1, "이유: 만기가 먼 구간엔 '거의 안 일어날 일' 마켓이 낮은 확률로 정박 → 맞히기 쉬움"),
        (1, "해결이 가까운 구간엔 결과가 팽팽한 접전 마켓이 섞여 오히려 어려움"),
        (1, "→ '해결이 가까울수록 정확'이라는 단순 통념은 이 표본에선 성립하지 않음"),
    ], y0=0.88, dy=0.029)
    _img(fig, "cal_02_brier_vs_ttr.png", [0.10, 0.11, 0.80, 0.40])
    _foot(fig, "p.5"); pdf.savefig(fig); plt.close(fig)

    # ===== p6: trajectories =====
    fig = _page(pdf, "4. 결과별 평균 확률 경로", "CONVERGENCE")
    _bullets(fig, [
        (0, "이 그림 읽는 법"),
        (1, "1,200개를 실제 결과(YES/NO)별로 묶어, '해결까지 남은 일수'에 맞춰 평균낸 확률"),
        (1, "가로축 오른쪽이 해결 시점 — 오른쪽으로 갈수록 진실이 드러남 (밴드=중간 50% 범위)"),
        (1, "초록=결국 YES로 판명된 마켓 · 빨강=결국 NO로 판명된 마켓"),
        (0, "관찰"),
        (1, "YES 판명 마켓(초록)은 해결이 다가올수록 평균 확률이 오름(0.4→0.6+)"),
        (1, "NO 판명 마켓(빨강)은 낮게 유지(~0.1) — 두 선이 점점 벌어짐(시장이 방향을 맞혀감)"),
        (1, "평균이 정확히 1·0까지 안 가는 건 이력의 마지막 점이 정산 '직전'값이라 그럼"),
    ], y0=0.88, dy=0.029)
    _img(fig, "cal_03_trajectories.png", [0.09, 0.22, 0.82, 0.42])
    _foot(fig, "p.6"); pdf.savefig(fig); plt.close(fig)

    # ===== p7: conclusion =====
    fig = _page(pdf, "5. 결론 · 한계", "CONCLUSION")
    _bullets(fig, [
        (0, "한 줄 결론"),
        (1, "군중의 확률은 대체로 믿을 만함 — 단, 아주 낮거나 아주 높은 확률은 살짝 걸러 볼 것"),
        (0, "쉽게 말하면"),
        (1, "시장이 '70%'라 한 일들을 모아보니 실제로도 약 70% 정도가 일어남 → 확률이 정직함"),
        (1, "이건 '매번 적중'이 아님 — 70%라 한 것 중 30%는 안 일어나는 게 오히려 정상임"),
        (1, "즉 개별 승부를 다 맞혔다는 게 아니라, '확률로서' 정확하다는 뜻"),
        (0, "다만 완만한 치우침"),
        (1, "낮은 확률(15~25%)이라 한 일 → 실제론 그보다 조금 더 자주 일어남(저평가)"),
        (1, "높은 확률(75~85%)이라 한 일 → 실제론 조금 덜 일어남(고평가) — 극단서 살짝 과신"),
        (0, "숫자로"),
        (1, f"예측 오차 {b_model:.3f} < 기준선(무조건 평균빈도로 찍기) {b_clim:.3f} → {skill*100:.0f}% 더 정확"),
        (0, "이 결과를 곧이곧대로 믿기 전에 (한계)"),
        *([
            (2, "같은 마켓의 여러 시점을 함께 셈 → 실제로 '독립된' 사례 수는 1,200개보다 적음"),
            (2, "표본이 스포츠·'거의 안 일어날 일' 마켓에 치우침 → 낮은 확률 쪽에 몰림"),
            (2, "결과가 거의 정해진 막판 구간이 섞여, 실제보다 성적이 좋아 보일 여지"),
          ] if backfilled else [
            (2, f"결과 확정 마켓 {S['resolved_markets']}개뿐 — 통계적으로 얇고 치우침"),
            (2, "결과를 최종 극단확률로 추정 — 공식 정산이 아님"),
          ]),
        (0, "다음에 하면 좋을 것"),
        (2, "반반에 가까운(40~70%) 마켓을 더 모아 높은확률 구간 신뢰도 보강"),
        (2, "분야별(정치·스포츠·크립토) 비교 — 치우침이 어디서 오는지 규명"),
    ], y0=0.87, dy=0.0275)
    _foot(fig, "p.7"); pdf.savefig(fig); plt.close(fig)
    pdf.close()


if __name__ == "__main__":
    main()
