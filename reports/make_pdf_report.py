"""Build a Korean PDF report (개조식/음슴체) explaining the backtest, with charts.

Uses matplotlib PdfPages (already installed) + NanumGothic for Korean.
Reads figures + backtest_summary.json produced by backtest.py.
Output: reports/divergence_signal_report.pdf
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = ROOT / "data" / "divergence.db"

# ---- Korean font ----
FONT = Path.home() / ".local/share/fonts/NanumGothic.ttf"
FONT_B = Path.home() / ".local/share/fonts/NanumGothicBold.ttf"
fm.fontManager.addfont(str(FONT))
if FONT_B.exists():
    fm.fontManager.addfont(str(FONT_B))
plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False

S = json.loads((HERE / "backtest_summary.json").read_text())
A4 = (8.27, 11.69)
INK = "#1a1a2e"
MUTED = "#555"


def db_stats() -> dict:
    c = sqlite3.connect(DB)
    mn, mx, n = c.execute(
        "SELECT MIN(timestamp),MAX(timestamp),COUNT(*) FROM drift_records").fetchone()
    ev = c.execute("SELECT COUNT(DISTINCT event_slug) FROM drift_records").fetchone()[0]
    tk = c.execute("SELECT COUNT(DISTINCT ticker) FROM drift_records").fetchone()[0]
    live = c.execute(
        "SELECT COUNT(*) FROM (SELECT event_slug FROM drift_records GROUP BY event_slug "
        "HAVING MAX(timestamp) > ? - 86400)", (mx,)).fetchone()[0]
    c.close()
    import datetime as dt
    f = dt.datetime.fromtimestamp(mn).strftime("%Y-%m-%d")
    l = dt.datetime.fromtimestamp(mx).strftime("%Y-%m-%d")
    return {"first": f, "last": l, "rows": n, "events": ev,
            "tickers": tk, "live": live, "days": (mx - mn) / 86400}


ST = db_stats()


def new_page(pdf, title=None, kicker=None):
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    if kicker:
        fig.text(0.08, 0.955, kicker, fontsize=9, color="#8172B3", weight="bold")
    if title:
        fig.text(0.08, 0.925, title, fontsize=19, color=INK, weight="bold")
        fig.add_artist(plt.Line2D([0.08, 0.92], [0.905, 0.905],
                       color="#8172B3", lw=2, transform=fig.transFigure))
    return fig


def bullets(fig, lines, y0=0.86, x=0.08, dy=0.032, size=11):
    """개조식 계층 불릿 렌더. lines: (level, text). level 0=□,1=○,2=-,3=•"""
    marks = {0: "□", 1: "  ○", 2: "     -", 3: "        •"}
    cols = {0: INK, 1: "#2a2a3e", 2: MUTED, 3: MUTED}
    weights = {0: "bold", 1: "normal", 2: "normal", 3: "normal"}
    y = y0
    for lvl, txt in lines:
        fig.text(x, y, f"{marks[lvl]} {txt}", fontsize=size if lvl == 0 else size - 0.5,
                 color=cols[lvl], weight=weights[lvl], va="top", wrap=True)
        y -= dy * (1.25 if lvl == 0 else 1.0)
    return y


def image_block(fig, png, rect):
    ax = fig.add_axes(rect)
    ax.imshow(mpimg.imread(str(HERE / png)))
    ax.axis("off")


def footer(fig, n):
    fig.text(0.5, 0.03, f"Polymarket 진입신호 엔진 검증 보고서  ·  {n}",
             ha="center", fontsize=8, color="#999")


def h(hz, t):
    return S["horizons"][hz][t]


def main():
    pdf = PdfPages(HERE / "divergence_signal_report.pdf")

    # ===== p1 표지 =====
    fig = plt.figure(figsize=A4); fig.patch.set_facecolor("white")
    fig.add_artist(plt.Rectangle((0, 0.72), 1, 0.28, color="#16213e",
                   transform=fig.transFigure, zorder=0))
    fig.text(0.5, 0.88, "예측시장 × 금융시장", ha="center", fontsize=17,
             color="#a9b4e0", weight="bold")
    fig.text(0.5, 0.80, "Divergence 진입신호 예측력 검증", ha="center",
             fontsize=25, color="white", weight="bold")
    fig.text(0.5, 0.755, "— Polymarket lead-lag 차익 가설의 백테스트 —",
             ha="center", fontsize=12, color="#c7cde8")
    concl = ("결론: 금융시장 → 폴리마켓 확률에 대한\n"
             "유의한 예측력 미입증 (사실상 동전던지기)")
    fig.text(0.5, 0.55, concl, ha="center", fontsize=15, color="#C44E52",
             weight="bold", linespacing=1.6)
    meta = [f"검증 기간   {ST['first']} ~ {ST['last']}  ({ST['days']:.0f}일)",
            f"표본 규모   drift_records {ST['rows']:,}행 · 이벤트 {ST['events']}개 · 티커 {ST['tickers']}개",
            f"검증 방식   신호 시점 확률 → +6/24/72h 후 방향 적중률 (기준선 50%)",
            f"작성일     2026-07-20"]
    fig.text(0.5, 0.30, "\n".join(meta), ha="center", fontsize=10.5,
             color=MUTED, linespacing=2.2)
    footer(fig, "p.1"); pdf.savefig(fig); plt.close(fig)

    # ===== p2 개요·방법론 =====
    fig = new_page(pdf, "1. 개요 및 검증 방법", "OVERVIEW")
    bullets(fig, [
        (0, "목적"),
        (1, "금융시장 움직임이 폴리마켓 확률 변화를 선행 예측하는지 정량 검증함"),
        (0, "엔진 가설 (lead-lag 차익)"),
        (1, "금융지표가 먼저 움직였으나 폴리마켓 확률이 아직 반영 안 됨 → 곧 따라올 것으로 보고 진입"),
        (1, "BUY YES = 확률 상승 예측 / BUY NO = 확률 하락 예측"),
        (0, "검증 방식 (forward hit-rate)"),
        (1, "신호 발생 시점 t 의 확률 → t+H 후 확률 변화가 예측 방향과 일치하면 적중"),
        (1, "지평 H = 6h / 24h / 72h, 기준선 = 50%(무작위)"),
        (1, "판정: 95% 신뢰구간(CI) 하한 > 50% → 유의한 예측력 / 50% 포함·미만 → 예측력 없음"),
        (0, "전처리"),
        (2, "정규화 붕괴 이상치(|drift|>1) 제거 — 변동성 0 근처에서 z-move 폭주분"),
        (2, "(토큰·티커)당 1시간 1건으로 다운샘플 — 5분 주기 반복신호 자기상관 완화"),
    ], y0=0.86)
    # flow diagram
    ax = fig.add_axes([0.08, 0.10, 0.84, 0.24]); ax.axis("off")
    ax.set_xlim(0, 10); ax.set_ylim(0, 3)
    boxes = [(1.0, "금융시장\nΔ가격 (yfinance)", "#55A868"),
             (4.0, "정규화\nz-move ×0.05", "#4C72B0"),
             (7.0, "폴리마켓\nΔ확률 (Gamma)", "#8172B3")]
    for x, t, col in boxes:
        ax.add_patch(plt.Rectangle((x, 1.0), 2.0, 1.1, fc=col, ec="none", alpha=0.9))
        ax.text(x + 1.0, 1.55, t, ha="center", va="center", color="white",
                fontsize=9, weight="bold")
    for x in (3.0, 6.0):
        ax.annotate("", (x + 1.0, 1.55), (x, 1.55),
                    arrowprops=dict(arrowstyle="->", lw=1.5, color=MUTED))
    ax.text(5.0, 0.4, "drift = ΔP - 정규화(ΔA)  →  신호 분류(BUY YES/NO)",
            ha="center", fontsize=9.5, color=INK, weight="bold")
    footer(fig, "p.2"); pdf.savefig(fig); plt.close(fig)

    # ===== p3 데이터 현황 =====
    fig = new_page(pdf, "2. 데이터 현황 및 커버리지", "DATA")
    bullets(fig, [
        (0, "수집 규모"),
        (1, f"기간 {ST['first']} ~ {ST['last']} (약 {ST['days']:.0f}일), 5분 주기 무중단 수집"),
        (1, f"drift {ST['rows']:,}행 · 이벤트 {ST['events']}개 · 티커 {ST['tickers']}개"),
        (0, "커버리지 한계 (하단 그래프)"),
        (1, f"현재 살아있는 이벤트 {ST['live']}개 — 대부분 마켓이 해결·종료되며 만료"),
        (1, "지정학·거시 이벤트 중심(휴전·연준·경기침체·대만) → 표본 편중"),
    ], y0=0.86)
    image_block(fig, "04_event_coverage.png", [0.10, 0.08, 0.80, 0.52])
    footer(fig, "p.3"); pdf.savefig(fig); plt.close(fig)

    # ===== p4 신호 분포 =====
    fig = new_page(pdf, "3. 신호 분포", "SIGNALS")
    bullets(fig, [
        (0, "관찰"),
        (1, "BUY YES/NO 가 전체의 84% — 임계값(정규화 3%)이 낮아 거의 항상 신호 발생"),
        (1, "PRICED IN·NEUTRAL 은 소수 → 신호가 '희소한 기회'가 아니라 상시 점등 상태"),
        (0, "함의"),
        (2, "신호가 흔할수록 각 신호의 정보량은 낮음 → 예측력 검증이 필수"),
    ], y0=0.86)
    image_block(fig, "01_signal_distribution.png", [0.12, 0.30, 0.76, 0.34])
    footer(fig, "p.4"); pdf.savefig(fig); plt.close(fig)

    # ===== p5 핵심결과 =====
    fig = new_page(pdf, "4. 핵심 결과 — 예측력 없음", "RESULT")
    a6, a24, a72 = h("6h", "ALL"), h("24h", "ALL"), h("72h", "ALL")
    bullets(fig, [
        (0, "전체 신호 적중률 (기준선 50%)"),
        (1, f"+6h : {a6['hit_rate']*100:.1f}%  (CI {a6['ci95'][0]*100:.1f}~{a6['ci95'][1]*100:.1f}%), 표본 {a6['n']:,}"),
        (1, f"+24h: {a24['hit_rate']*100:.1f}%  (CI {a24['ci95'][0]*100:.1f}~{a24['ci95'][1]*100:.1f}%), 표본 {a24['n']:,}"),
        (1, f"+72h: {a72['hit_rate']*100:.1f}%  (CI {a72['ci95'][0]*100:.1f}~{a72['ci95'][1]*100:.1f}%), 표본 {a72['n']:,}"),
        (0, "판정"),
        (1, "세 지평 모두 50.6~50.8% — CI 하한이 50%에 붙어 무작위와 구분 불가"),
        (1, "수수료·슬리피지 감안 시 실거래 기대수익 음(-)"),
    ], y0=0.86)
    image_block(fig, "02_hitrate_by_horizon.png", [0.10, 0.08, 0.80, 0.44])
    footer(fig, "p.5"); pdf.savefig(fig); plt.close(fig)

    # ===== p6 유형별 분해 (진짜 원인) =====
    fig = new_page(pdf, "5. 유형별 분해 — 겉보기 적중의 정체", "DIAGNOSIS")
    bullets(fig, [
        (0, "핵심 발견"),
        (1, "BUY NO 는 55~58%로 50% 초과, BUY YES 는 44~46%로 50% 미만"),
        (1, "두 값이 50% 기준으로 대칭 → 진짜 알파면 YES·NO 둘 다 초과해야 함"),
        (0, "해석"),
        (1, "신호가 아니라 기저 확률 하락 추세(base-rate drift)를 탐지한 것뿐"),
        (2, "'X가 일어날까' 류 마켓은 시간이 갈수록 NO로 수렴 → '무조건 BUY NO'가 이김"),
        (2, "divergence 로직 고유의 예측 기여는 0에 수렴"),
    ], y0=0.86)
    # table
    ax = fig.add_axes([0.10, 0.30, 0.80, 0.26]); ax.axis("off")
    rows = [["신호", "지평", "표본", "적중률", "95% CI"]]
    for hz in ("6h", "24h", "72h"):
        for t in ("BUY YES", "BUY NO"):
            s = h(hz, t)
            rows.append([t, "+" + hz, f"{s['n']:,}", f"{s['hit_rate']*100:.1f}%",
                         f"{s['ci95'][0]*100:.1f}~{s['ci95'][1]*100:.1f}%"])
    tbl = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center",
                   cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9.5); tbl.scale(1, 1.6)
    for (r, cc), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#16213e"); cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        else:
            t = rows[r][0]
            cell.set_facecolor("#eaf5ea" if t == "BUY NO" else "#fbeaea")
    fig.text(0.5, 0.25, "BUY NO(초록) 우세 · BUY YES(빨강) 열세 → 방향성 기저효과의 증거",
             ha="center", fontsize=10, color=MUTED, style="italic")
    footer(fig, "p.6"); pdf.savefig(fig); plt.close(fig)

    # ===== p7 강도 무관성 =====
    fig = new_page(pdf, "6. 신호 강도와 적중률", "ROBUSTNESS")
    bullets(fig, [
        (0, "검증"),
        (1, "신호 강도(|drift|)를 5분위로 나눠 적중률 비교 (+24h)"),
        (0, "결과"),
        (1, "강한 신호일수록 적중률이 오르는 단조 경향 없음 → 임계값 상향으로도 알파 회복 불가"),
    ], y0=0.86)
    image_block(fig, "03_hitrate_by_strength.png", [0.10, 0.30, 0.80, 0.40])
    footer(fig, "p.7"); pdf.savefig(fig); plt.close(fig)

    # ===== p8 결론·한계·운영 =====
    fig = new_page(pdf, "7. 결론 · 한계 · 후속", "CONCLUSION")
    bullets(fig, [
        (0, "결론"),
        (1, "이 엔진의 lead-lag 차익 신호 기준, 금융→폴리마켓 예측력은 미입증"),
        (1, "겉보기 적중은 전부 이벤트 확률의 NO 수렴(기저효과)로 설명됨"),
        (0, "한계 (과잉해석 금지)"),
        (2, "이벤트 19개·특정 정규화/임계값 설계에 대한 반증 — 일반적 무관계 증명 아님"),
        (2, "방향 이동만 평가(모의 진입가), 실제 체결·수수료·슬리피지 미반영"),
        (2, "표본이 지정학·거시 마켓에 편중, 다운샘플 후에도 완전 독립 아님(CI 낙관 가능)"),
        (0, "후속 제안"),
        (2, "기저 NO-drift 를 벤치마크로 차감한 초과수익(excess) 기준 재설계"),
        (2, "역방향(폴리마켓→금융) 및 특정 이벤트군(연준 등) 한정 재검증"),
        (2, "정규화 붕괴(변동성 0 근처 z-move 폭주) 코드 수정 — 하한 클리핑"),
        (0, "데이터 운영 (부록)"),
        (1, "라이브 DB 는 ext4 유지, 크기 임계값 초과 시 Windows(/mnt/c)로 자동 백업"),
        (2, "systemd timer 30분 주기 · 온라인 .backup+gzip · 최근 10개 로테이션"),
        (2, f"검증 산출물: reports/ (PNG 4종 · REPORT.md · 본 PDF)"),
    ], y0=0.88, dy=0.030)
    footer(fig, "p.8"); pdf.savefig(fig); plt.close(fig)

    pdf.close()
    print("wrote", HERE / "divergence_signal_report.pdf")


if __name__ == "__main__":
    main()
