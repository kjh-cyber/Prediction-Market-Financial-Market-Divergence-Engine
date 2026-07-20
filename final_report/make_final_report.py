"""Final synthesis report — combines the predictability study and the calibration
study into one plain-language PDF, reusing every chart from both and adding a
synthesis diagram + key-numbers summary.

Reads numbers from the two studies' JSON summaries (so text stays accurate) and
embeds their PNGs. Output: final_report/polymarket_final_report.pdf
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.backends.backend_pdf import PdfPages

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PRED = ROOT / "study_predictability"
CAL = ROOT / "study_calibration"

FONT = Path.home() / ".local/share/fonts/NanumGothic.ttf"
if FONT.exists():
    fm.fontManager.addfont(str(FONT))
    plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams.update({"figure.dpi": 120})

INK, MUTED = "#14243a", "#555"
NAVY, GREEN, RED = "#16213e", "#2e8b57", "#C44E52"
A4 = (8.27, 11.69)

BT = json.loads((PRED / "backtest_summary.json").read_text())
DD = json.loads((PRED / "directional_diagnostic.json").read_text())
CS = json.loads((CAL / "calibration_summary.json").read_text())


# ---------- helpers ----------
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
    return y


def _img(fig, path, rect, caption=None):
    ax = fig.add_axes(rect); ax.imshow(mpimg.imread(str(path))); ax.axis("off")
    if caption:
        fig.text(rect[0] + rect[2] / 2, rect[1] - 0.018, caption, ha="center",
                 fontsize=8, color=MUTED, style="italic")


def _foot(fig, n):
    fig.text(0.5, 0.03, f"예측시장 종합 분석 보고서  ·  {n}", ha="center",
             fontsize=8, color="#999")


def _box(ax, x, y, w, h, text, fc, tc="white", fs=10):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.03",
                 fc=fc, ec="none"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tc,
            fontsize=fs, weight="bold")


# ---------- synthesis diagram (new asset) ----------
def make_synthesis_png():
    fig, ax = plt.subplots(figsize=(9, 4.6)); ax.axis("off")
    ax.set_xlim(0, 10); ax.set_ylim(0, 5)
    _box(ax, 0.3, 2.9, 3.1, 1.5,
         "① 확률이 정직함\n(캘리브레이션 좋음)\n\"70%\" → 실제 ~70%", GREEN, fs=10.5)
    _box(ax, 0.3, 0.5, 3.1, 1.5,
         "② 밖에서 못 이김\n(예측력 없음)\n어느 방향도 ~50%", RED, fs=10.5)
    _box(ax, 5.6, 1.7, 3.8, 1.6,
         "효율적 시장\n= 정보가 이미\n가격(확률)에 반영됨", NAVY, fs=11.5)
    for y0 in (3.65, 1.25):
        ax.annotate("", (5.6, 2.5), (3.4, y0),
                    arrowprops=dict(arrowstyle="-|>", lw=1.8, color=MUTED))
    ax.text(5.0, 4.6, "두 발견은 한 몸", ha="center", fontsize=11, color=INK, weight="bold")
    ax.text(5.0, 0.15,
            "잘 캘리브레이션된 시장은 원래 예측하기 어렵다 — 맞힐 수 있었다면 가격이 틀렸다는 뜻",
            ha="center", fontsize=9, color=MUTED, style="italic")
    fig.tight_layout(); fig.savefig(HERE / "syn_01_efficiency.png"); plt.close(fig)


def h(hz, t):
    return BT["horizons"][hz][t]


# ---------- build ----------
def main():
    make_synthesis_png()
    pdf = PdfPages(HERE / "polymarket_final_report.pdf")

    # ===== p1 cover =====
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.add_artist(plt.Rectangle((0, 0.70), 1, 0.30, color=NAVY, transform=fig.transFigure))
    fig.text(0.5, 0.855, "예측시장(Polymarket) 종합 분석", ha="center", fontsize=17,
             color="#a9b4e0", weight="bold")
    fig.text(0.5, 0.785, "군중의 예측은 믿을 만한가,\n그리고 이길 수 있는가", ha="center",
             fontsize=23, color="white", weight="bold", linespacing=1.3)
    fig.text(0.5, 0.60,
             "결론\n확률은 정직하다(믿을 만함).\n그러나 쉽게 이길 수는 없다(효율적 시장).",
             ha="center", fontsize=15, color=NAVY, weight="bold", linespacing=1.7)
    box = [f"1부 · 예측력   금융↔예측시장 어느 방향도 예측 불가 (~50%)",
           f"2부 · 캘리브레이션   확률 정직 — 오차 {CS['brier_model']:.3f} (기준선보다 {CS['brier_skill_vs_climatology']*100:.0f}% 정확)",
           f"3부 · 종합   두 결과는 '효율적 시장'의 두 얼굴"]
    fig.text(0.5, 0.34, "\n".join(box), ha="center", fontsize=11, color=INK, linespacing=2.4)
    fig.text(0.5, 0.16, "데이터: 예측력=손매핑 19개(vs 금융) · 캘리브레이션=해결된 1,200개\n작성일 2026-07-20",
             ha="center", fontsize=10, color=MUTED, linespacing=2.0)
    _foot(fig, "p.1"); pdf.savefig(fig); plt.close(fig)

    # ===== p2 executive summary =====
    fig = _page(pdf, "요약 (한 장으로)", "SUMMARY")
    a24 = h("24h", "ALL")
    _bullets(fig, [
        (0, "출발점"),
        (1, "'예측시장이 금융시장보다 늦게 반응한다면, 그 시차로 돈을 벌 수 있지 않을까'"),
        (0, "1부 · 예측력 — 아니오"),
        (1, f"금융→예측시장 적중률 {a24['hit_rate']*100:.1f}%, 예측시장→금융 {DD['pm_to_fin_fwd']['hit_rate']*100:.1f}% (둘 다 ~50%=동전던지기)"),
        (1, f"원인: 두 시장이 애초에 함께 움직이지 않음(상관 평균 {DD['corr0_mean_abs']}, 사실상 0)"),
        (0, "2부 · 캘리브레이션 — 확률은 정직"),
        (1, f"'70%'라 한 일이 실제 ~70% 일어남. 예측 오차 {CS['brier_model']:.3f} < 기준선 {CS['brier_climatology']:.3f}"),
        (1, "단, 낮은 확률은 살짝 저평가·높은 확률은 살짝 고평가(완만한 치우침)"),
        (0, "3부 · 종합 — 효율적 시장"),
        (1, "확률이 정직하고(=정보 반영됨) 그래서 밖에서 앞지를 수 없음 — 두 발견은 한 몸"),
        (1, "실전: 확률은 예보로 그대로 신뢰 · 순진한 차익거래는 통하지 않음"),
    ], y0=0.865)
    _foot(fig, "p.2"); pdf.savefig(fig); plt.close(fig)

    # ===== p3 배경 & 용어 =====
    fig = _page(pdf, "배경 & 용어 풀이", "BASICS")
    _bullets(fig, [
        (0, "예측시장(Polymarket) 이란"),
        (1, "미래의 '예/아니오' 질문에 사람들이 돈을 걸고 지분을 사고파는 시장임"),
        (1, "'예(YES)' 지분 가격이 곧 그 일이 일어날 확률 (가격 0.60 = 확률 60%)"),
        (1, "실제로 일어나면 YES 지분이 1로, 안 일어나면 0으로 정산됨"),
        (0, "핵심 용어"),
        (1, "캘리브레이션: '60%'라 한 일이 정말 60% 일어나는지 = 확률의 정확도"),
        (1, "예측 오차(Brier): 평균((확률-실제결과)²), 0에 가까울수록 정확"),
        (1, "기저율: 전체에서 YES 난 비율. '무조건 이 비율로 찍기'가 비교 기준선"),
        (1, "적중률: 다음 움직임의 방향을 맞힌 비율. 50%=동전던지기(정보 없음)"),
        (1, "상관(correlation): 두 값이 함께 움직이는 정도. 0=무관, 1=완전 동행"),
        (0, "두 연구 한눈에"),
        (1, "1부(예측력): 한 시장으로 다른 시장을 앞질러 맞힐 수 있나 → 이길 수 있나?"),
        (1, "2부(캘리브레이션): 그 확률 자체가 정확한가 → 믿을 만한가?"),
    ], y0=0.865)
    _foot(fig, "p.3"); pdf.savefig(fig); plt.close(fig)

    # ================= PART 1 =================
    fig = _page(pdf, "1부 · 예측력 — 이길 수 있는가", "PART 1", accent=RED)
    _bullets(fig, [
        (0, "가설"),
        (1, "금융시장이 먼저 움직이고 예측시장이 늦게 따라오면, 그 사이 진입해 차익"),
        (1, "3개월간 5분 주기로 예측시장 확률 + 금융 가격을 손매핑 19개 쌍에서 수집"),
        (0, "신호"),
        (1, "금융이 움직였는데 예측시장 확률이 아직이면 → BUY YES/NO 신호 발생"),
        (1, "그 신호대로 확률이 실제로 움직였는지(적중) 6/24/72시간 뒤 확인"),
        (0, "확인 순서 (다음 장들)"),
        (2, "신호가 얼마나 자주 뜨나 → 실제 적중하나 → 신호가 강하면 더 맞나"),
        (2, "→ 애초에 두 시장이 상관은 있나 → 반대방향(예측시장→금융)은?"),
    ], y0=0.86)
    _foot(fig, "p.4"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "1-1. 신호는 늘 켜져 있었다", "PART 1", accent=RED)
    _bullets(fig, [
        (0, "관찰"),
        (1, "BUY YES/NO 신호가 전체의 84% — 임계값이 낮아 거의 항상 신호가 뜸"),
        (1, "신호가 흔할수록 각 신호의 정보량은 낮음 → 실제 적중 검증이 필수"),
    ], y0=0.86)
    _img(fig, PRED / "01_signal_distribution.png", [0.13, 0.30, 0.74, 0.34],
         "신호 유형 분포 — 대부분 '사라' 신호")
    _foot(fig, "p.5"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "1-2. 적중률은 동전던지기 = 예측력 없음", "PART 1", accent=RED)
    _bullets(fig, [
        (0, "결과"),
        (1, f"+6/24/72시간 모두 적중률 50.6~50.8% — 기준선 50%와 사실상 차이 없음"),
        (1, "BUY NO만 50% 넘고 BUY YES는 50% 미만 → 대칭 = 신호가 아니라 '확률이 시간이 갈수록 NO로 기우는' 기저효과일 뿐"),
        (1, "수수료·슬리피지 감안 시 실거래 기대수익은 음(-)"),
    ], y0=0.86)
    _img(fig, PRED / "02_hitrate_by_horizon.png", [0.10, 0.10, 0.80, 0.42],
         "시간대별 적중률 vs 50% 기준선")
    _foot(fig, "p.6"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "1-3. 신호를 강하게 걸러도 안 됨", "PART 1", accent=RED)
    _bullets(fig, [
        (0, "검증"),
        (1, "신호 강도를 5단계로 나눠 적중률 비교 (+24시간)"),
        (0, "결과"),
        (1, "강한 신호일수록 더 맞는 단조 경향 없음 → 임계값을 높여도 알파 회복 불가"),
    ], y0=0.86)
    _img(fig, PRED / "03_hitrate_by_strength.png", [0.10, 0.30, 0.80, 0.36],
         "신호 강도별 적중률 — 강해도 안 오름")
    _foot(fig, "p.7"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "1-4. 진짜 원인 — 두 시장이 안 묶임", "PART 1", accent=RED)
    _bullets(fig, [
        (0, "방향을 고르기 전에"),
        (1, "'금융→예측'이 안 되면 반대로? → 그 전에 두 시장이 함께 움직이긴 하나 확인"),
        (0, "동시점 상관 (핵심)"),
        (1, f"매핑 {DD['pairs']}쌍 전부 |상관|<0.15, 평균 {DD['corr0_mean_abs']} — 사실상 무관"),
        (1, "상관이 0 근처면 어느 방향이든 시차 차익은 성립 불가"),
    ], y0=0.86)
    _img(fig, PRED / "05_contemporaneous_corr.png", [0.16, 0.05, 0.68, 0.48],
         "매핑 쌍별 동시점 상관 — 전부 0 근처")
    _foot(fig, "p.8"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "1-5. 반대방향도 사망 확인", "PART 1", accent=RED)
    _bullets(fig, [
        (0, "리드-랙"),
        (1, "누가 먼저 움직이나 — 일관된 선행 구조 없음(시차 정보 아님)"),
        (0, "예측시장 → 금융 (반대방향 직접 검증)"),
        (1, f"예측시장 확률이 크게 움직인 뒤 +24h 금융 방향 적중 {DD['pm_to_fin_fwd']['hit_rate']*100:.1f}% (n={DD['pm_to_fin_fwd']['n']})"),
        (1, "50% 미만 → 예측시장도 금융을 앞지르지 못함 → 양방향 모두 예측력 없음"),
    ], y0=0.86)
    _img(fig, PRED / "06_leadlag_and_pm_to_fin.png", [0.07, 0.28, 0.86, 0.34],
         "리드-랙(좌) · 예측시장→금융 적중률(우)")
    _foot(fig, "p.9"); pdf.savefig(fig); plt.close(fig)

    # ================= PART 2 =================
    fig = _page(pdf, "2부 · 캘리브레이션 — 믿을 만한가", "PART 2", accent=GREEN)
    _bullets(fig, [
        (0, "질문"),
        (1, "시장이 매긴 확률이 실제로 그 빈도만큼 맞았는가"),
        (0, "정답 확보 — '이미 끝난' 마켓만"),
        (1, f"이미 정산된 예/아니오 마켓 {CS['resolved_markets']:,}개(YES {CS['resolved_yes']}/NO {CS['resolved_no']}) 대량 수집"),
        (1, "공식 정산 결과를 정답으로 사용 — 각 마켓의 확률 이력 전체 확보"),
        (0, "'YES 실현 / NO 실현'"),
        (1, "YES 실현 = 실제로 일어난 마켓(예: 트럼프 2024 당선?→당선)"),
        (1, "NO 실현 = 안 일어난 마켓(예: 해리스 2024 당선?→무산)"),
    ], y0=0.86)
    _foot(fig, "p.10"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "2-1. 확률은 실제와 잘 맞았다", "PART 2", accent=GREEN)
    _bullets(fig, [
        (0, "읽는 법"),
        (1, "가로=시장이 매긴 확률, 세로=실제로 일어난 비율, 대각선=완벽 일치"),
        (0, "관찰"),
        (1, "점들이 대각선에 바짝 붙음 → 시장 확률이 실제와 대체로 잘 맞음"),
        (1, "낮은 확률(15~25%)은 실제론 더 자주 일어남(저평가), 높은 확률(75~85%)은 덜(고평가)"),
    ], y0=0.86)
    _img(fig, CAL / "cal_01_reliability.png", [0.16, 0.06, 0.68, 0.44],
         "예측확률 vs 실제 실현 빈도")
    _foot(fig, "p.11"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "2-2. 해결이 가까울수록 정확해지나", "PART 2", accent=GREEN)
    _bullets(fig, [
        (0, "관찰 (직관과 반대)"),
        (1, "해결 임박 구간이 오차가 오히려 크고, 먼 구간이 작음"),
        (1, "먼 구간엔 '거의 안 일어날 일'이 낮은 확률로 정박해 맞히기 쉬움"),
        (1, "가까운 구간엔 결과가 팽팽한 접전 마켓이 섞여 오히려 어려움"),
    ], y0=0.86)
    _img(fig, CAL / "cal_02_brier_vs_ttr.png", [0.10, 0.16, 0.80, 0.38],
         "남은 기간별 예측 오차")
    _foot(fig, "p.12"); pdf.savefig(fig); plt.close(fig)

    fig = _page(pdf, "2-3. 결과별 평균 확률 경로", "PART 2", accent=GREEN)
    _bullets(fig, [
        (0, "읽는 법"),
        (1, "결과(YES/NO)별로 묶어 '해결까지 남은 일수'에 맞춰 평균낸 확률 (오른쪽=해결)"),
        (0, "관찰"),
        (1, "YES 판명(초록)은 다가올수록 확률 상승, NO 판명(빨강)은 낮게 유지 — 두 선이 갈라짐"),
        (1, "시장이 시간이 지나며 정답 방향으로 확률을 옮겨감"),
    ], y0=0.86)
    _img(fig, CAL / "cal_03_trajectories.png", [0.09, 0.20, 0.82, 0.40],
         "결과별 평균 확률 경로")
    _foot(fig, "p.13"); pdf.savefig(fig); plt.close(fig)

    # ================= PART 3 =================
    fig = _page(pdf, "3부 · 종합 — 효율적 시장", "PART 3")
    _bullets(fig, [
        (0, "두 발견은 한 몸"),
        (1, "확률이 정직함(2부) = 현재 가격에 정보가 이미 다 반영돼 있음"),
        (1, "밖에서 못 이김(1부) = 남은 정보가 없어 앞질러 먹을 여지가 없음"),
        (1, "→ 잘 캘리브레이션된 시장은 원래 예측하기 어려움 (서로 강화)"),
    ], y0=0.87)
    _img(fig, HERE / "syn_01_efficiency.png", [0.08, 0.40, 0.84, 0.34])
    _bullets(fig, [
        (0, "실전 함의"),
        (1, "확률은 미래 예보로 그대로 신뢰할 만함"),
        (1, "순진한 차익거래(시차 노리기)는 통하지 않음"),
        (1, "유일한 미세한 틈은 극단 확률의 치우침 — 수수료·유동성 탓에 먹기 어려움"),
    ], y0=0.33)
    _foot(fig, "p.14"); pdf.savefig(fig); plt.close(fig)

    # conclusion / limits
    fig = _page(pdf, "결론 · 한계 · 다음", "CONCLUSION")
    _bullets(fig, [
        (0, "한 줄 결론"),
        (1, "'군중의 지혜'는 실제로 작동함 — 정직한 확률을 내놓고, 그래서 쉽게 못 이김"),
        (0, "핵심 숫자"),
        (1, f"예측력: 양방향 ~50%(동전던지기) · 시장 간 상관 평균 {DD['corr0_mean_abs']}(무관)"),
        (1, f"캘리브레이션: 오차 {CS['brier_model']:.3f} vs 기준선 {CS['brier_climatology']:.3f} → {CS['brier_skill_vs_climatology']*100:.0f}% 더 정확"),
        (0, "한계 (과잉해석 금지)"),
        (2, "두 연구는 표본이 다름(예측력 19개 vs 캘리브레이션 1,200개) → 정합적 큰 그림이지 동일표본 증명 아님"),
        (2, "'예측 불가'는 이 특정 전략에 대한 반증 — 모든 전략 실패 증명은 아님"),
        (2, "캘리브레이션 표본은 스포츠·낮은확률 편중·자기상관 한계"),
        (0, "다음에 하면 좋을 것"),
        (2, "반반에 가까운(40~70%) 마켓을 더 모아 높은확률 구간 신뢰도 보강"),
        (2, "분야별(정치·스포츠·크립토) 캘리브레이션 비교 — 치우침 원천 규명"),
    ], y0=0.88, dy=0.028)
    _foot(fig, "p.15"); pdf.savefig(fig); plt.close(fig)

    pdf.close()
    print("wrote", HERE / "polymarket_final_report.pdf")


if __name__ == "__main__":
    main()
