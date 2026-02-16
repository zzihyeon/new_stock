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
- PostgreSQL
- Prisma ORM
- Zod

## Setup

1. 환경변수 복사

```bash
cp .env.example .env
```

2. `.env` 값 입력 (KIS 실전 계정 키/계좌 포함)

필수/권장 키:

- `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (텔레그램 알림 연동용)

3. 의존성 설치

```bash
npm install
```

4. Prisma 클라이언트 생성 및 마이그레이션

```bash
npm run prisma:generate
npm run prisma:migrate -- --name init
```

5. 개발 서버 실행

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
