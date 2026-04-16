# Prediction Market × Financial Market Divergence Engine

예측시장(Polymarket)과 금융시장(yfinance) 간의 괴리(drift)를 탐지하고, 선행 신호 및 서사 변화를 분석하는 엔진.

## 핵심 개념

- **Drift**: 예측시장 확률 변화(ΔP)와 자산 가격 변화(ΔA)의 차이
- **Signal Types**:
  - `lead`: 예측시장이 먼저 움직임 (자산 미반영)
  - `lag`: 자산이 먼저 움직임 (예측시장 미조정)
  - `divergence`: 방향 불일치
  - `convergence`: 정상적 동조

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 대시보드 포함
pip install -e ".[dashboard]"
```

## 사용법

```bash
# DB 초기화
divergence-engine init-db

# 매핑 확인
divergence-engine mappings

# 매핑 resolve (Polymarket 마켓 연결)
divergence-engine resolve

# 데이터 수집만
divergence-engine collect

# 분석만
divergence-engine analyze

# 전체 파이프라인 (수집 → 분석 → 결과 표시)
divergence-engine run

# 연속 실행 모드 (5분 간격)
divergence-engine run --watch --interval 300

# Top divergence 조회
divergence-engine top --limit 20

# 웹 대시보드
divergence-engine dashboard
```

## 아키텍처

```
[Polymarket API] ─┐
                  ├── Collectors ── Mapping Registry ── Drift Engine ── Output
[yfinance] ───────┘

divergence_engine/
├── collectors/    # Polymarket + yfinance 데이터 수집
├── mappings/      # 이벤트-자산 매핑 정의 및 resolve
├── analysis/      # Drift 계산, Z-score 이상치 탐지, Signal 분류
├── storage/       # SQLite 기반 데이터 저장
├── output/        # CLI 테이블 + Streamlit 대시보드
├── pipeline.py    # 파이프라인 오케스트레이션
└── cli.py         # Typer CLI 인터페이스
```

## 설정

`.env` 파일로 설정 가능 (`.env.example` 참고):

```env
ZSCORE_THRESHOLD=2.0
DRIFT_MIN_THRESHOLD=0.05
DEFAULT_WINDOW_HOURS=24
COLLECT_INTERVAL=300
```

## 매핑 커스터마이징

`divergence_engine/mappings/definitions.py`에서 이벤트-자산 매핑을 수정:

```python
EventAssetMapping(
    event_slug="my-event",
    search_keywords=["keyword1", "keyword2"],  # 모두 매칭되어야 함
    description="My custom event",
    asset_tickers=["SPY", "QQQ"],
    correlation_direction="positive",  # or "inverse"
    weight=0.8,
    category="custom",
)
```
