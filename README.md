# KIS Stock Analyzer

한국투자 OpenAPI 기반으로 종목 데이터를 수집하고, 캔들 차트/스크리너/관심종목/단순 백테스트를 제공하는 Next.js 앱입니다.

## Features

- 한국투자 OpenAPI 실전 계정 인증 및 시세 조회 클라이언트
- 일봉/분봉 데이터 수집 API (`/api/ingest`)
- 캔들 조회 API (`/api/candles`)
- 조건 기반 스크리너 API (`/api/screener`)
- 관심종목 CRUD API (`/api/watchlist`)
- SMA 교차 단순 백테스트 API (`/api/backtest`)
- 대시보드 UI (차트, 스크리너, 워치리스트, 백테스트)

## Tech Stack

- Next.js (App Router, TypeScript)
- MongoDB Replica Set
- Mongoose
- Zod

## Setup

1. 환경변수 복사

```bash
cp .env.example .env
```

2. `.env` 값 입력 (KIS 실전 계정 키/계좌 포함)

필수/권장 키:

- `MONGODB_URI`, `MONGODB_DB_NAME`
- `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (텔레그램 알림 연동용)

3. 의존성 설치

```bash
npm install
```

4. 개발 서버 실행

```bash
npm run dev
```

브라우저에서 `http://localhost:3000`을 열면 대시보드가 보입니다.

## API Quick Start

- 기본 종목 수집 실행

```bash
curl -X POST http://localhost:3000/api/ingest
```

- 캔들 조회 (일봉)

```bash
curl "http://localhost:3000/api/candles?symbol=005930&timeframe=DAY&limit=120"
```

- 스크리너 실행

```bash
curl -X POST http://localhost:3000/api/screener \
  -H "content-type: application/json" \
  -d '{"minPrice":50000,"minVolume":1000000,"minChangeRate":0.5}'
```

## Notes

- 현재 구현은 국내주식 단일 시장 기준입니다.
- KIS API TR ID/파라미터는 계정 권한 및 API 정책에 따라 조정이 필요할 수 있습니다.
- 운영 배포 전 Node LTS(20+) 환경을 권장합니다.
- 런타임 설정은 `src/lib/config.ts`에서 중앙 관리합니다.

## Python Quant Screener

요구한 규칙 기반 퀀트 스크리너는 `src/screener` 패키지로 구성되어 있습니다.

- `auth.py`: `.env` 로드, KIS 인증/토큰 캐시
- `kis_client.py`: KIS OpenAPI 호출, 레이트리밋 대응(throttle), HTTP 캐시
- `market_data.py`: 심볼 시드 로드, 시총 필터 Universe 생성, 데이터셋 수집
- `indicators.py`: MA/거래량/거래대금 퍼센타일/지지 체크
- `screener.py`: 패턴 A(양음양), 패턴 B(200MA below), 재무 개선 판정
- `report.py`: 콘솔 표, CSV 저장, 상위 5개 요약, 텔레그램 신규 편입 알림
- `dart_migration.py`: `dart/dart_cache.sqlite(emp_cache)` -> Mongo raw/features 마이그레이션
- `jobs_collector.py`: 사람인/잡코리아 채용 공고 수집 및 종목별 채용 모멘텀 집계

### Python 실행

```bash
python3 -m pip install -r requirements-screener.txt
python3 -m src.screener --debug-symbols 005930 000660
```

주기 실행(예: 10분마다):

```bash
python3 -m src.screener --loop-minutes 10
```

하루 1회 실행(기본값):

```bash
python3 -m src.screener
```

Mongo 누적 데이터만 기반으로 분석 실행:

```bash
python3 -m src.screener --loop-minutes 0 --data-source mongo
```

DART SQLite 이관 + 채용 데이터 수집 + 결합 스코어 반영 실행:

```bash
python3 -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --migrate-dart-sqlite-path "dart/dart_cache.sqlite" \
  --collect-jobs \
  --job-sources "saramin,jobkorea" \
  --job-max-companies 120 \
  --use-composite-score
```

동작 정책:
- 매 실행 시 전체 심볼을 스캔하고 `data/universe_100b.txt`를 갱신합니다.
- 스크리닝 결과가 0건이면 `reports/screen_*.csv` 파일을 생성하지 않습니다.
- 일봉 OHLCV(`시가/고가/저가/종가/거래량/거래대금`)는 MongoDB `daily_ohlcv` 컬렉션에 누적 저장합니다.
- 이후 차트는 KIS 재조회 없이 MongoDB 저장 데이터로 그릴 수 있습니다.
- DART 원본은 `dart_emp_raw`, 정규화 지표는 `dart_emp_features`에 저장합니다.
- 채용 공고 원본은 `job_postings`, 종목별 채용 모멘텀은 `job_features`에 저장합니다.

전체 종목 파일(`data/symbols.txt`) 기준으로 돌리면서 조건 민감도 조정 예시:

```bash
python3 -m src.screener --d0-vol-multiple 1.4 --d1-drop-ratio 0.6 --batch-size 40
```

심볼 시드:
- `data/symbols.txt` 또는 `data/symbols.csv(symbol 컬럼)` 사용
- 전체 상장종목으로 갱신:

```bash
python -m src.screener.symbols_sync
```

텔레그램은 이전 결과 대비 **신규 편입 종목만** 알립니다.

참고:
- 시총 필터는 `hts_avls(억원)` 우선, 없으면 `종가*상장주식수`로 계산합니다.
- 시총 캐시는 `.cache/market_caps.json`에 저장되어 반복 실행 속도를 개선합니다.

## macOS 자동 실행 (장중/장마감/야간)

```bash
./scripts/install_launchd.sh
```

수동 1회 실행:

```bash
./scripts/run_daily_screening.sh
```

권장 운영 흐름:
- `scripts/run_ingest_1600.sh`: 장마감 수집 + DART 이관 + 채용 수집(DB 업데이트 전용)
- `scripts/run_watchlist_2000.sh`: 저장 데이터 기반 스크리닝 + 결합 스코어 + 텔레그램 full
- `scripts/run_intraday_30m.sh`: 장중 30분 간격 신규 편입 체크 + 결합 스코어 + 텔레그램 new
