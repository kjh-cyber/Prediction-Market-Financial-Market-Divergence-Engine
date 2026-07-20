"""Stock-market efficiency study — done instantly on yfinance historical data.

Demonstrates the two-sided fact behind an efficient market:
  (A) RETURNS are (nearly) unpredictable — random walk / weak-form efficiency
      · return autocorrelation ≈ 0 at all lags
      · directional hit rate ≈ 50% (only the upward drift beats a coin flip)
      · variance ratio ≈ 1 across horizons
  (B) VOLATILITY IS predictable — volatility clustering
      · |return| autocorrelation is large and slowly decaying
      · this month's volatility strongly predicts next month's

Ties back to the Polymarket studies: the same wall (info already in the price)
that killed the divergence signal also makes stock direction unpredictable.

Outputs (study_stock_efficiency/):
  se_01_acf.png · se_02_hitrate.png · se_03_variance_ratio.png
  se_04_vol_persistence.png · se_05_return_clustering.png
  stock_efficiency_summary.json · stock_efficiency_report.pdf
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
TICKERS = ["SPY", "QQQ", "AAPL", "MSFT"]
HEAD = "SPY"                 # headline ticker for charts
START = "2005-01-01"
MAXLAG = 15

FONT = Path.home() / ".local/share/fonts/NanumGothic.ttf"
if FONT.exists():
    fm.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams.update({"figure.dpi": 120, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.axisbelow": True})
INK, MUTED = "#14243a", "#555"
NAVY, GREEN, RED = "#16213e", "#2e8b57", "#C44E52"
A4 = (8.27, 11.69)


def acf(x, maxlag):
    x = np.asarray(x); x = x - x.mean()
    n = len(x); denom = np.dot(x, x)
    return [float(np.dot(x[:n - k], x[k:]) / denom) for k in range(maxlag + 1)]


def variance_ratio(r, qs):
    r = np.asarray(r); v1 = r.var(ddof=1)
    out = {}
    for q in qs:
        rq = pd.Series(r).rolling(q).sum().dropna().to_numpy()
        out[q] = float(rq.var(ddof=1) / (q * v1))
    return out


def analyze(ret):
    n = len(ret)
    ci = 1.96 / np.sqrt(n)
    acf_r = acf(ret, MAXLAG)
    acf_abs = acf(np.abs(ret), MAXLAG)
    sign = np.sign(ret.to_numpy())
    # momentum: predict tomorrow's sign = today's sign
    mom_hit = float(np.mean(sign[:-1] == sign[1:]))
    # always-up baseline (captures drift only)
    up_rate = float(np.mean(ret.to_numpy() > 0))
    vr = variance_ratio(ret, [2, 4, 8, 16, 32])
    # volatility persistence: non-overlapping 21d realized vol, this vs next
    rv = ret.rolling(21).std().iloc[::21].dropna()
    cur, nxt = rv.iloc[:-1].to_numpy(), rv.iloc[1:].to_numpy()
    vol_corr = float(np.corrcoef(cur, nxt)[0, 1]) if len(cur) > 3 else float("nan")
    return {"n": n, "ci": ci, "acf_r": acf_r, "acf_abs": acf_abs,
            "acf_r_lag1": acf_r[1], "acf_abs_lag1": acf_abs[1],
            "mom_hit": mom_hit, "up_rate": up_rate, "vr": vr,
            "vol_persist_corr": vol_corr, "rv_cur": cur, "rv_nxt": nxt,
            "ret": ret}


def main():
    px = yf.download(TICKERS, start=START, auto_adjust=True, progress=False)["Close"]
    rets = np.log(px / px.shift(1)).dropna(how="all")
    res = {t: analyze(rets[t].dropna()) for t in TICKERS}
    H = res[HEAD]

    summary = {"start": START, "end": str(px.index.max().date()),
               "tickers": TICKERS, "headline": HEAD, "per_ticker": {}}
    for t in TICKERS:
        r = res[t]
        summary["per_ticker"][t] = {
            "n": r["n"], "ci95": round(r["ci"], 4),
            "ret_acf_lag1": round(r["acf_r_lag1"], 4),
            "absret_acf_lag1": round(r["acf_abs_lag1"], 4),
            "momentum_hit": round(r["mom_hit"], 4),
            "always_up_rate": round(r["up_rate"], 4),
            "variance_ratio_q16": round(r["vr"][16], 3),
            "vol_persistence_corr": round(r["vol_persist_corr"], 3)}
    (HERE / "stock_efficiency_summary.json").write_text(json.dumps(summary, indent=2))

    lags = np.arange(1, MAXLAG + 1)

    # se_01: ACF returns vs |returns|
    fig, ax = plt.subplots(figsize=(9, 5))
    w = 0.4
    ax.bar(lags - w / 2, H["acf_r"][1:], w, color=GREEN, label="수익률 (방향)")
    ax.bar(lags + w / 2, H["acf_abs"][1:], w, color=RED, label="|수익률| (변동성 크기)")
    ax.axhline(H["ci"], color="#888", ls="--", lw=0.8, label="±95% 유의밴드")
    ax.axhline(-H["ci"], color="#888", ls="--", lw=0.8)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("시차 (거래일)"); ax.set_ylabel("자기상관")
    ax.set_title(f"{HEAD}: 수익률 자기상관은 작음(≈0, 미세 반전)  vs  |수익률| 자기상관은 큼\n"
                 "→ 방향은 사실상 예측 불가, 변동성은 예측 가능")
    ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(HERE / "se_01_acf.png"); plt.close(fig)

    # se_02: directional hit rate
    fig, ax = plt.subplots(figsize=(8, 4.8))
    labels = ["모멘텀 규칙\n(어제와 같은 방향)", "'항상 상승'\n(추세만 이용)", "동전던지기"]
    vals = [H["mom_hit"] * 100, H["up_rate"] * 100, 50]
    colors = ["#4C72B0", "#8172B3", "#999"]
    ax.bar(labels, vals, color=colors, width=0.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.4, f"{v:.1f}%", ha="center", fontsize=10, weight="bold")
    ax.axhline(50, color="k", ls="--", lw=1)
    ax.set_ylim(40, 60); ax.set_ylabel("다음날 방향 적중률 (%)")
    ax.set_title(f"{HEAD}: 다음날 방향 맞히기 — 예측 규칙은 ~50%, '추세'만 살짝 이김")
    fig.tight_layout(); fig.savefig(HERE / "se_02_hitrate.png"); plt.close(fig)

    # se_03: variance ratio
    fig, ax = plt.subplots(figsize=(8, 4.8))
    qs = sorted(H["vr"])
    ax.plot(qs, [H["vr"][q] for q in qs], marker="o", color=NAVY, lw=2)
    ax.axhline(1.0, color=RED, ls="--", lw=1, label="랜덤워크 기준 = 1")
    ax.set_xlabel("기간 묶음 q (일)"); ax.set_ylabel("분산비율 VR(q)")
    ax.set_ylim(0.6, 1.3)
    ax.set_title(f"{HEAD}: 분산비율이 1을 다소 밑돎(VR≈0.75)\n→ 미세한 평균회귀는 있으나 큰 시계열 구조는 없음")
    ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(HERE / "se_03_variance_ratio.png"); plt.close(fig)

    # se_04: volatility persistence
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.scatter(H["rv_cur"] * 100, H["rv_nxt"] * 100, s=18, alpha=0.5, color=RED)
    lim = max((H["rv_cur"].max(), H["rv_nxt"].max())) * 100 * 1.05
    ax.plot([0, lim], [0, lim], "--", color="#888", lw=0.8)
    ax.set_xlabel("이번 달 변동성 (%)"); ax.set_ylabel("다음 달 변동성 (%)")
    ax.set_title(f"{HEAD}: 이번 달 변동성 → 다음 달 변동성 (상관 {H['vol_persist_corr']:.2f})\n"
                 "변동성은 뚜렷이 이어짐 = 예측 가능")
    fig.tight_layout(); fig.savefig(HERE / "se_04_vol_persistence.png"); plt.close(fig)

    # se_05: return clustering over time
    fig, ax = plt.subplots(figsize=(9.5, 4.5))
    r = H["ret"]
    ax.plot(r.index, r.to_numpy() * 100, lw=0.5, color=NAVY)
    ax.set_ylabel("일간 수익률 (%)"); ax.set_xlabel("연도")
    ax.set_title(f"{HEAD} 일간 수익률 — 큰 변동은 큰 변동끼리 뭉침(변동성 클러스터링)")
    fig.tight_layout(); fig.savefig(HERE / "se_05_return_clustering.png"); plt.close(fig)

    build_pdf(summary, res)
    print(f"{HEAD}: 수익률 lag1 자기상관 {H['acf_r_lag1']:+.3f}, |수익률| lag1 {H['acf_abs_lag1']:+.3f}")
    print(f"  모멘텀 적중 {H['mom_hit']*100:.1f}%, 항상상승 {H['up_rate']*100:.1f}%, VR(16) {H['vr'][16]:.2f}, 변동성지속 {H['vol_persist_corr']:.2f}")
    print("wrote outputs to", HERE)


# ---------- PDF ----------
def _page(pdf, title, kicker, accent=NAVY):
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.text(0.08, 0.955, kicker, fontsize=9, color=accent, weight="bold")
    fig.text(0.08, 0.923, title, fontsize=18, color=INK, weight="bold")
    fig.add_artist(plt.Line2D([0.08, 0.92], [0.902, 0.902], color=accent, lw=2,
                   transform=fig.transFigure))
    return fig


def _bullets(fig, lines, y0=0.86, dy=0.0285, size=11):
    marks = {0: "□", 1: "  ○", 2: "     -", 3: "        •"}
    y = y0
    for lvl, txt in lines:
        fig.text(0.08, y, f"{marks[lvl]} {txt}", va="top",
                 fontsize=size if lvl == 0 else size - 0.5,
                 color=INK if lvl == 0 else "#2a2a3e",
                 weight="bold" if lvl == 0 else "normal")
        y -= dy * (1.25 if lvl == 0 else 1.0)


def _img(fig, path, rect, caption=None):
    ax = fig.add_axes(rect); ax.imshow(mpimg.imread(str(path))); ax.axis("off")
    if caption:
        fig.text(rect[0] + rect[2] / 2, rect[1] - 0.02, caption, ha="center",
                 fontsize=8, color=MUTED, style="italic")


def _foot(fig, n):
    fig.text(0.5, 0.03, f"주식시장 효율성 실증  ·  {n}", ha="center", fontsize=8, color="#999")


def build_pdf(S, res):
    H = res[S["headline"]]
    pdf = PdfPages(HERE / "stock_efficiency_report.pdf")

    # cover
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.add_artist(plt.Rectangle((0, 0.70), 1, 0.30, color=NAVY, transform=fig.transFigure))
    fig.text(0.5, 0.85, "주식시장 효율성 실증", ha="center", fontsize=25, color="white", weight="bold")
    fig.text(0.5, 0.79, "— 방향은 못 맞혀도, 변동성은 맞힐 수 있다 —", ha="center",
             fontsize=12.5, color="#c7cde8")
    fig.text(0.5, 0.575,
             "결론\n주가 '방향'은 사실상 예측 불가(랜덤워크에 가까움)\n주가 '변동성'은 예측 가능(뭉침)",
             ha="center", fontsize=14, color=NAVY, weight="bold", linespacing=1.7)
    fig.text(0.5, 0.30,
             f"데이터: yfinance 일봉 {S['start']}~{S['end']}  ·  {', '.join(S['tickers'])}\n"
             f"과거 데이터라 수집 대기 없이 즉시 검증  ·  작성일 2026-07-20",
             ha="center", fontsize=10.5, color=MUTED, linespacing=2.0)
    _foot(fig, "p.1"); pdf.savefig(fig); plt.close(fig)

    # basics
    fig = _page(pdf, "배경 & 용어 풀이", "BASICS")
    _bullets(fig, [
        (0, "무엇을 보나"),
        (1, "'과거 정보가 이미 가격에 반영됐다면, 과거로 미래를 맞힐 수 있나'를 실제 데이터로 확인"),
        (0, "용어 풀이"),
        (1, "수익률: 하루 사이 가격 변화율(오르면 +, 내리면 -)"),
        (1, "랜덤워크: 다음 값 = 현재 값 + 예측 불가능한 잡음 → 방향 못 맞힘"),
        (1, "자기상관: 어제 값이 오늘 값을 얼마나 알려주나 (0=전혀, 1=완전). 0 근처면 예측 불가"),
        (1, "변동성: 가격이 흔들리는 정도(수익률의 표준편차)"),
        (1, "변동성 뭉침(클러스터링): 크게 흔들린 날 뒤엔 또 크게 흔들리는 경향"),
        (1, "분산비율(VR): 여러 날 묶은 변동이 하루 변동의 몇 배인가. 랜덤워크면 딱 배수(=1)"),
        (0, "앞선 예측시장 연구와 연결"),
        (1, "예측시장에서 본 '정보가 이미 반영됨→못 이김'을 주식에서 재확인하는 실험"),
    ], y0=0.865)
    _foot(fig, "p.2"); pdf.savefig(fig); plt.close(fig)

    # result A-1 acf
    fig = _page(pdf, "1. 수익률은 사실상 예측 불가 (방향)", "RANDOM WALK", accent=RED)
    _bullets(fig, [
        (0, "핵심 그림 (아래)"),
        (1, "초록=수익률 자기상관 → 매우 작음. 지수는 lag1이 살짝 음(-)으로 유의하나(미세 단기 반전) 크기가 미미"),
        (1, "빨강=|수익률| 자기상관 → 훨씬 크고(0.2~0.3) 오래 감 = 변동성은 이어짐(2장에서 활용)"),
        (1, f"{S['headline']}: 수익률 lag1 {H['acf_r_lag1']:+.3f} vs |수익률| lag1 {H['acf_abs_lag1']:+.3f} — 약 3배 차이"),
        (1, "즉 방향 신호는 있어도 미세, 변동성 신호는 뚜렷 — 크기의 격차가 핵심"),
    ], y0=0.87)
    _img(fig, HERE / "se_01_acf.png", [0.08, 0.28, 0.86, 0.40],
         "같은 데이터 — 방향엔 구조 거의 없고(초록), 변동성엔 뚜렷(빨강)")
    _foot(fig, "p.3"); pdf.savefig(fig); plt.close(fig)

    # result A-2 hitrate
    fig = _page(pdf, "1-2. 방향 맞히기 = 동전던지기", "RANDOM WALK", accent=RED)
    _bullets(fig, [
        (0, "결과"),
        (1, f"'어제와 같은 방향' 규칙 적중 {H['mom_hit']*100:.1f}% — 오히려 50% '미만'(단기 반전 탓)"),
        (1, f"'항상 상승'은 {H['up_rate']*100:.1f}% — 예측이 아니라 장기 우상향(추세)만 이용한 것"),
        (1, "미세한 반전이 있어도 수수료·호가 스프레드 감안 시 못 먹음 → 실질 예측력 0"),
        (1, "→ 예측시장 연구의 'BUY NO만 이긴 건 기저효과'와 똑같은 구조(추세만 이김)"),
    ], y0=0.87)
    _img(fig, HERE / "se_02_hitrate.png", [0.12, 0.30, 0.76, 0.36],
         "예측 규칙은 50% · '추세'만 살짝 위")
    _foot(fig, "p.4"); pdf.savefig(fig); plt.close(fig)

    # result A-3 VR
    fig = _page(pdf, "1-3. 분산비율 — 큰 구조는 없음", "RANDOM WALK", accent=RED)
    _bullets(fig, [
        (0, "검증"),
        (1, "여러 날 묶은 변동이 하루 변동의 정확히 배수인지 확인 (랜덤워크면 VR=1)"),
        (0, "결과"),
        (1, f"VR이 1을 다소 밑돎(VR(16)≈{H['vr'][16]:.2f}) → 며칠 단위 '미세한 평균회귀' 존재"),
        (1, "완벽한 랜덤워크는 아니나 이탈 폭이 작음 → 비용 넘길 만한 거래 기회는 아님"),
    ], y0=0.87)
    _img(fig, HERE / "se_03_variance_ratio.png", [0.12, 0.32, 0.76, 0.34],
         "분산비율이 1을 살짝 밑돎 — 미세 평균회귀")
    _foot(fig, "p.5"); pdf.savefig(fig); plt.close(fig)

    # result B-1 clustering
    fig = _page(pdf, "2. 변동성은 예측 가능 (뭉침)", "VOLATILITY", accent=GREEN)
    _bullets(fig, [
        (0, "관찰"),
        (1, "크게 출렁인 구간(위기)과 잔잔한 구간이 뭉쳐서 나타남 — 무작위가 아님"),
        (1, "방향은 못 맞혀도 '얼마나 흔들릴지'는 최근 흐름으로 가늠 가능"),
    ], y0=0.87)
    _img(fig, HERE / "se_05_return_clustering.png", [0.06, 0.34, 0.88, 0.32],
         "일간 수익률 — 큰 변동끼리 뭉침")
    _foot(fig, "p.6"); pdf.savefig(fig); plt.close(fig)

    # result B-2 persistence
    fig = _page(pdf, "2-2. 이번 달 변동성 → 다음 달 변동성", "VOLATILITY", accent=GREEN)
    _bullets(fig, [
        (0, "결과"),
        (1, f"이번 달 변동성과 다음 달 변동성의 상관 {H['vol_persist_corr']:.2f} — 뚜렷이 이어짐"),
        (1, "방향(예측 불가)과 정반대로, 변동성은 지속성이 강함 → GARCH 등으로 모델링"),
        (1, "실전 쓸모: 옵션 가격·리스크 관리·포지션 크기 조절"),
    ], y0=0.87)
    _img(fig, HERE / "se_04_vol_persistence.png", [0.16, 0.28, 0.68, 0.40],
         "점들이 우상향 = 변동성 이어짐")
    _foot(fig, "p.7"); pdf.savefig(fig); plt.close(fig)

    # cross-ticker + conclusion
    fig = _page(pdf, "3. 결론 — 종목 불문 같은 패턴", "CONCLUSION")
    _bullets(fig, [
        (0, "네 종목 모두 동일"),
    ], y0=0.90)
    ax = fig.add_axes([0.08, 0.60, 0.84, 0.24]); ax.axis("off")
    rows = [["종목", "수익률\n자기상관", "방향 적중", "분산비율\nVR(16)", "변동성\n지속상관"]]
    for t in S["tickers"]:
        p = S["per_ticker"][t]
        rows.append([t, f"{p['ret_acf_lag1']:+.3f}", f"{p['momentum_hit']*100:.1f}%",
                     f"{p['variance_ratio_q16']:.2f}", f"{p['vol_persistence_corr']:.2f}"])
    tbl = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9.5); tbl.scale(1, 1.9)
    for (rr, cc), cell in tbl.get_celld().items():
        if rr == 0:
            cell.set_facecolor(NAVY); cell.get_text().set_color("white"); cell.get_text().set_weight("bold")
    _bullets(fig, [
        (0, "해석"),
        (1, "수익률 자기상관 매우 작음(미세 음) · 방향 적중 ~50% 안팎 · VR 1 부근 → 방향은 사실상 예측 불가"),
        (1, "변동성 지속상관은 0.5~0.7로 뚜렷 → 변동성은 예측 가능"),
        (1, "미세한 반전·평균회귀는 실재하나 비용 넘길 크기는 아님(완벽한 랜덤워크는 아님)"),
        (0, "예측시장 연구와 합치면"),
        (1, "예측시장·주식 모두 '정보가 이미 가격에 반영됨' → 방향으로는 못 이김(효율적 시장)"),
        (1, "개인의 길: 방향 맞히기 대신 위험 프리미엄 수확 + 변동성 같은 '되는 것' 활용"),
        (0, "한계"),
        (2, "생존편향(현재 상장 종목만)·미래정보 누수 위험은 팩터 연구 시 별도 관리 필요"),
        (2, "'예측 불가'는 단순 규칙·비용 기준 — 프로의 속도·독점데이터 우위까지 부정하는 건 아님"),
    ], y0=0.55, dy=0.029)
    _foot(fig, "p.8"); pdf.savefig(fig); plt.close(fig)
    pdf.close()
    print("wrote", HERE / "stock_efficiency_report.pdf")


if __name__ == "__main__":
    main()
