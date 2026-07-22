# port_strategy_execution

`port_strategy_execution`은 포트폴리오 전략의 실행 단계 Python MS다. daily decision/research 결과와 connector 계좌/잔고/포지션 정보를 읽어 `strategy_execution_order` 후보를 만들고, 승인된 실행 흐름에서는 connector 주문 요청, 체결 동기화, 전략 포지션 상태 갱신까지 이어질 수 있다.

이 README는 현재 파일 구조와 소스를 정적으로 확인해 유지하는 운영 문서다. 실제 execution/order 생성, 자동 매수/매도, 체결 조회, fill sync, position sync, intraday monitor, DB DDL/DML, 외부 API 호출, 크롤링, 주문 제출은 수행하지 않는다. AWS 운영 관점 설명은 PORT-STRATEGY-EXECUTION 책임 범위 안의 사실만 기록하고, 다른 MS 내부 구현/전체 orchestration 상세는 제외한다.

## 주요 역할

- Daily BUY signal 기반 실행 주문 후보를 만든다.
- Daily position SELL decision 기반 실행 주문 후보를 만든다.
- Backtest trade log 기반 실행 주문 후보를 만들 수 있다.
- `strategy_execution_plan`, `strategy_execution_order` 저장/상태 갱신 책임을 가진다.
- READY 상태의 BUY/SELL execution order를 connector BUY/SELL 호출로 제출할 수 있다.
- `connector_order_request`, `connector_fill` 조회 기반으로 execution order 상태 동기화 책임을 가진다.
- BUY fill을 기준으로 `strategy_position_state` OPEN 포지션을 생성할 수 있다.
- SELL fill을 기준으로 `strategy_position_state.remaining_qty` 차감과 포지션 상태 갱신을 할 수 있다.
- 장중 OPEN 포지션을 모니터링해 `strategy_intraday_position_check` 저장과 `INTRADAY_STOP_SELL` 후보를 만들 수 있다.
- AWS Paper Daily Step 8~17 및 장중 10분 intraday evaluate 흐름에서 실행 계층으로 호출될 수 있다.

## Execution 책임 경계

Execution이 직접 책임지지 않는 영역은 아래와 같다. 관련 내용을 README 및 하위 문서에서 확장하지 않는다.

- 외부 데이터 수집 (Crawler 책임)
- raw 데이터 전처리와 feature 생성 (Preprocessor 책임)
- daily BUY signal 판단 자체 (StrategyDecision 책임)
- daily position HOLD/SELL/SKIP 판단 자체 (StrategyDecision 책임)
- 백테스트와 리포트 생성 (StrategyResearch 책임)
- KIS API 내부 구현과 connector token 관리 (MarketConnector 책임)
- View 화면 렌더링과 승인 UI (port-view 책임)
- Daily Batch 전체 orchestration (Scheduler + Step Functions 책임)

## AWS 운영 구조 (Execution 관점)

AWS Paper 환경에서 Execution은 execution order 생성, 주문 실행 연계, fill sync, position sync, intraday stop 후보 생성 단계로 호출된다. 아래는 Execution이 실제로 관여하는 구간만 정리한다. Step Functions state machine 전체 step, EventBridge Scheduler 라인업, Lambda 내부 구현, MarketConnector KIS API 상세, 다른 MS의 세부 운영 로그는 이 문서에 담지 않는다.

전체 orchestration은 EventBridge Scheduler와 Step Functions가 담당한다. Execution은 orchestration 대상의 실행 계층으로만 호출된다. 실제 broker/KIS 주문 API 호출은 MarketConnector 책임이며 이 저장소에서 직접 수행하지 않는다. 다만 이 저장소의 auto buy/sell entrypoint는 connector BUY/SELL helper를 호출하는 경로를 포함할 수 있다.

### Daily Step 8~17 Execution 역할

- **Step 8 DAILY_BUY_EXECUTION** — `daily_buy_execution_run.py`가 latest daily run과 daily BUY signal을 읽어 BUY execution order 후보를 생성한다. `execution_daily_signal_builder.py`, `execution_buy_sizing.py`, `execution_repository.py`를 거쳐 `strategy_execution_plan`, `strategy_execution_order`에 저장/갱신 가능성이 있다. broker/KIS 주문 제출은 이 step 범위 밖.
- **Step 9 DAILY_SELL_EXECUTION** — `daily_sell_execution_run.py`가 latest daily position decision run의 SELL decision을 읽어 SELL execution order 후보를 만든다. `execution_daily_position_sell_builder.py`가 decision row를 `strategy_execution_order` 저장용 dict로 변환하며, `strategy_daily_position_decision.execution_order_id` 연결이 발생할 수 있다.
- **Step 10 DAILY_AUTO_SELL** — `daily_auto_sell_execute_run.py --execute`가 READY 상태 SELL execution order를 조회하고, connector SELL 호출과 `strategy_position_state` SELL_ORDERED 상태 갱신으로 이어질 수 있다. broker 주문 접수 자체는 MarketConnector connector helper 경유.
- **Step 11 DAILY_AUTO_BUY** — `daily_auto_buy_execute_run.py --execute`가 READY 상태 BUY execution order를 조회하고, connector BUY 호출과 실행 결과 상태 갱신을 수행할 수 있다.
- **Step 12~13 MARKETCONNECTOR/CONNECTOR order execute · check** — 이 구간은 MarketConnector 책임이다. Execution 관점에서는 승인된 REQUESTED 주문이 MarketConnector에서 broker/KIS로 제출되고, 체결 조회 후 `connector_order_request`, `connector_fill`이 갱신되어 Step 14~16 sync 대상 데이터가 준비되는 것으로만 이해한다.
- **Step 14 SYNC_SELL_FILL** — `execution_sync_sell_fill.py`가 SELL 주문의 체결 결과를 요약해 `strategy_execution_order` 상태를 `FILLED`로 갱신하고 `strategy_position_state.remaining_qty` 차감/상태 전이를 반영할 수 있다.
- **Step 15 SYNC_BUY_FILL** — `execution_sync_buy_fill.py`가 BUY 주문의 체결 수량/평균가를 요약해 `strategy_execution_order` 상태를 `FILLED`로 갱신할 수 있다.
- **Step 16 SYNC_BUY_POSITION** — `execution_sync_buy_position.py`가 FILLED BUY execution order 중 아직 포지션이 없는 항목을 찾아 `strategy_position_state` OPEN row를 생성하거나 기존 OPEN에 추가 매수를 병합할 수 있다.
- **Step 17 BALANCE_REFRESH** — MarketConnector 책임 구간이다. Execution은 이후 잔고/포지션 snapshot을 조회 대상으로 사용할 뿐이며, 자체적으로 balance/position snapshot 생성 책임을 가지지 않는다.

### 장중 10분 Intraday Evaluate 흐름 (Execution 관점)

- 장중 OPEN 포지션 monitor와 손절 후보 판정은 `daily_intraday_position_monitor_run.py`가 담당한다.
- `execution_position_loader.py`가 OPEN `strategy_position_state`와 최신 connector position snapshot을 결합해 포지션 컨텍스트를 만든다.
- `execution_sell_evaluator.py`가 포지션 컨텍스트, 종목 feature, 시장 feature를 결합해 SELL/HOLD 평가 payload를 만든다.
- 정상/이상 여부와 관계없이 점검 결과는 `strategy_intraday_position_check`에 저장하는 정책이다 (2026-05-27 미커밋 변경으로 정합됨).
- `--create-order` 명시 시 hard stop 조건 충족 종목에 대해 `INTRADAY_STOP_SELL` execution order를 생성할 수 있다. 실제 broker 주문 제출은 별도 approval gate 경유가 원칙이며 이 저장소 범위 밖이다.
- `execution_sell_builder.py`는 OPEN 포지션 평가 결과로 `POSITION_SELL` execution order 후보를 생성할 수 있는 별도 경로이며, `strategy_position_state` 평가 결과와 `strategy_execution_order`를 갱신할 수 있다.

### ECS RunTask / 컨테이너 실행 대상

Paper Daily Step 8~11, 14~16과 장중 monitor는 ECS RunTask 또는 컨테이너 실행 대상으로 호출될 수 있다. 실제 cluster 이름, task definition ARN, image URI, subnet, security group, command id, log group 이름은 이 문서에 원문으로 기록하지 않고 아래와 같은 placeholder로만 취급한다.

- `<EXECUTION_ECS_CLUSTER>`
- `<EXECUTION_TASK_DEFINITION_ARN>`
- `<EXECUTION_ECR_IMAGE_URI>`
- `<EXECUTION_LOG_GROUP>`
- `<COMMAND_ID>`

컨테이너 실행 대상 entrypoint는 아래와 같다. broker/KIS 주문 API 호출은 어느 경로에서도 이 저장소에서 직접 수행하지 않는다.

- `python daily_buy_execution_run.py`
- `python daily_sell_execution_run.py`
- `python daily_auto_buy_execute_run.py --execute`
- `python daily_auto_sell_execute_run.py --execute`
- `python execution_sync_buy_fill.py`
- `python execution_sync_sell_fill.py`
- `python execution_sync_buy_position.py`
- `python daily_intraday_position_monitor_run.py`

`Dockerfile`은 `python:3.13-slim` 기반이며 build context 상위에 `port_strategy_execution` 디렉터리가 포함되도록 구성한다. `requirements.txt`는 최소한의 런타임 의존성(`psycopg2-binary`)만 명시한다. `create_execution_docker_files.py`는 위 두 파일을 로컬에서 재생성하는 헬퍼 스크립트로, 운영 실행 대상이 아니다.

## 실행 주의사항

아래 entrypoint는 명시 승인과 대상 환경 확인 없이 실행하지 않는다.

- `daily_buy_execution_run.py`
- `daily_sell_execution_run.py`
- `daily_auto_buy_execute_run.py`
- `daily_auto_sell_execute_run.py`
- `daily_intraday_position_monitor_run.py`
- `execution_execute_order.py`
- `execution_sync_buy_fill.py`
- `execution_sync_sell_fill.py`
- `execution_sync_buy_position.py`
- `execution_sell_builder.py`
- `execution_build_candidates.py`
- `backtest_execution_run.py`
- `execution_position_loader.py`

위 파일들은 DB 쓰기, connector 주문 호출, 체결 조회 결과 반영, 포지션 상태 변경, intraday stop order 생성으로 이어질 수 있다. 문서화/리뷰 목적에서는 실행하지 않고 정적 분석만 수행한다.

Paper 자동 BUY/SELL은 별도 승인 flow(운영자 승인 + Scheduler 상태 ENABLED)를 거친 이후에만 활성화된다. Live 환경 자동 BUY/SELL은 이 저장소 범위에서 다루지 않으며, 후보 + 수동 승인 우선 정책을 유지한다.

## 파일 구조

```text
.
├── access_token.txt
├── AGENTS.md
├── CHANGELOG.md
├── Dockerfile
├── README.md
├── backtest_execution_run.py
├── create_execution_docker_files.py
├── daily_auto_buy_execute_run.py
├── daily_auto_sell_execute_run.py
├── daily_buy_execution_run.py
├── daily_intraday_position_monitor_run.py
├── daily_sell_execution_run.py
├── db_config.py
├── execution_build_candidates.py
├── execution_builder.py
├── execution_buy_sizing.py
├── execution_config.py
├── execution_daily_position_sell_builder.py
├── execution_daily_signal_builder.py
├── execution_db.py
├── execution_execute_order.py
├── execution_position_loader.py
├── execution_repository.py
├── execution_sell_builder.py
├── execution_sell_evaluator.py
├── execution_sync_buy_fill.py
├── execution_sync_buy_position.py
├── execution_sync_sell_fill.py
├── requirements.txt
└── docs/
    ├── database.md
    ├── source-file-catalog.md
    └── worklog/
        ├── 2026-05-26.md
        ├── 2026-05-27.md
        ├── 2026-05-28.md
        └── 2026-07-01.md
```

`access_token.txt`는 민감정보 후보 파일로 취급한다. 값은 읽거나 문서에 기록하지 않는다.

## 스크립트 구분

### Daily BUY Execution

- `daily_buy_execution_run.py`
  - 최신 daily run과 daily BUY signal을 조회한다.
  - `execution_daily_signal_builder.py`로 BUY execution order 후보를 만든다.
  - `execution_repository.create_or_get_daily_signal_plan`, `upsert_daily_signal_execution_order`, `update_plan_summary`를 통해 DB에 저장/갱신할 수 있다.
- `execution_daily_signal_builder.py`
  - daily BUY signal, 계좌/잔고, 현재 보유 수량, 최신 가격을 바탕으로 `strategy_execution_order` 저장용 dict를 만든다.
- `execution_buy_sizing.py`
  - 목표 금액, 현재 평가액, 사용 가능 현금, 최소 주문 금액을 기준으로 BUY 주문 수량을 계산한다.

### Daily SELL Execution

- `daily_sell_execution_run.py`
  - 최신 daily position decision run과 SELL decision을 조회한다.
  - `execution_daily_position_sell_builder.py`로 SELL execution order 후보를 만든다.
  - `strategy_daily_position_decision.execution_order_id`를 연결할 수 있다.
- `execution_daily_position_sell_builder.py`
  - daily position SELL decision을 `strategy_execution_order` 저장용 dict로 변환한다.

### Auto BUY/SELL Execute

- `daily_auto_buy_execute_run.py`
  - READY 상태 daily BUY execution order를 조회한다.
  - `connector_buy.buy_stock`을 호출할 수 있다.
  - 성공/실패 결과를 `strategy_execution_order`에 반영할 수 있다.
- `daily_auto_sell_execute_run.py`
  - READY 상태 daily/intraday SELL execution order를 조회한다.
  - 최신 connector position snapshot의 매도 가능 수량을 확인한다.
  - `connector_sell.sell_stock`을 호출할 수 있다.
  - SELL 제출 후 `strategy_position_state`를 SELL_ORDERED 상태로 바꿀 수 있다.
- `execution_execute_order.py`
  - 특정 `strategy_execution_order.id`를 대상으로 수동 실행 모드 검증과 connector BUY/SELL 호출을 수행할 수 있다.
  - `--execute`가 없으면 주문 호출 없이 검증과 execution mode 저장까지만 수행하는 구조지만, 이 저장 자체도 DB write다.
  - `LIVE_STRATEGY`는 live 환경과 `--confirm-live` 확인을 요구한다.

### Fill Sync / Position Sync

- `execution_sync_buy_fill.py`
  - `connector_order_request`, `connector_fill`을 조회한다.
  - BUY 주문의 체결 수량/평균가를 요약해 `strategy_execution_order`를 `FILLED`로 갱신할 수 있다.
- `execution_sync_sell_fill.py`
  - SELL 주문의 체결을 조회한다.
  - `strategy_execution_order`를 `FILLED`로 갱신하고 `strategy_position_state.remaining_qty`를 차감할 수 있다.
- `execution_sync_buy_position.py`
  - FILLED BUY execution order 중 아직 포지션이 없는 항목을 찾는다.
  - `strategy_position_state` OPEN row를 생성하고 execution order payload에 sync 결과를 추가할 수 있다.

### Position / Intraday Monitor

- `execution_position_loader.py`
  - OPEN `strategy_position_state`와 최신 connector position snapshot을 결합해 포지션 컨텍스트를 만든다.
  - 파일 하단에 실행 가능한 `main()`이 있으므로 단순 loader로만 취급해 실행하면 안 된다.
- `execution_sell_evaluator.py`
  - 포지션 컨텍스트, 종목 feature, 시장 feature를 바탕으로 SELL/HOLD 평가 결과를 만든다.
- `execution_sell_builder.py`
  - OPEN 포지션을 평가해 POSITION_SELL execution order 후보를 만들 수 있다.
  - `strategy_position_state` 평가 결과와 `strategy_execution_order`를 갱신할 수 있다.
- `daily_intraday_position_monitor_run.py`
  - OPEN 포지션을 장중 모니터링한다.
  - market connector quote 조회, `strategy_intraday_position_check` 저장, `INTRADAY_STOP_SELL` order 생성 가능성이 있다.

### Repository / Config / DB

- `execution_repository.py`
  - DB read/write helper가 집중된 파일이다.
  - `strategy_execution_plan`, `strategy_execution_order`, `strategy_position_state`, `strategy_daily_position_decision`, `strategy_intraday_position_check`에 insert/update 가능성이 있다.
  - `connector_order_request`, `connector_fill`, `connector_balance_snapshot`, `connector_position_snapshot` 조회 경로가 있다.
- `execution_db.py`
  - `psycopg2` 연결과 `fetch_one`, `fetch_all`, `execute_one` helper를 제공한다.
- `db_config.py`
  - DB 접속 설정을 `INTEREST_DB_*` 환경변수에서 읽고 `INTEREST_DB_PASSWORD`가 비어 있으면 오류를 발생시킨다.
- `execution_config.py`
  - DB, 계좌, broker, environment, strategy, sizing 관련 환경변수 key를 읽는다.
  - 문서에는 실제 credential, 계좌번호, token 값을 기록하지 않는다.

### Backtest 기반 Execution 후보

- `backtest_execution_run.py`
  - 최신 `strategy_backtest_run`, `strategy_backtest_daily`, `strategy_trade_log`를 기준으로 execution order 후보를 생성/저장할 수 있다.
- `execution_builder.py`
  - backtest buy/sell 후보를 `strategy_execution_order` 저장용 dict로 변환한다.
- `execution_build_candidates.py`
  - legacy 또는 독립형 후보 생성 스크립트 성격으로 보인다.
  - 자체 DB helper와 upsert 로직을 포함하므로 실행 금지 대상으로 본다.

## DB 쓰기 가능성이 큰 테이블

- `strategy_execution_plan`
- `strategy_execution_order`
- `strategy_position_state`
- `strategy_daily_position_decision`
- `strategy_intraday_position_check`

## Connector / Fill 조회 대상

- `connector_order_request`
- `connector_fill`
- `connector_account`
- `connector_balance_snapshot`
- `connector_position_snapshot`

`connector_order_request`와 `connector_fill` 조회는 체결 상태 반영 및 포지션 변경의 입력이 될 수 있다. 조회만으로 끝나는지, 후속 update가 있는지 반드시 정적으로 확인한 뒤 다룬다.

## 데이터베이스 구조

로컬 PostgreSQL 기본 DB name은 `portfolio`다. 과거 `interest_crawler` 단일 public schema 구조에서, AWS Migration 준비를 위해 단일 DB `portfolio` 안에 domain별 schema를 두는 schema-per-domain 구조로 전환했다.

이 모듈의 DB connection search_path는 아래 순서를 사용한다.

```text
execution,decision,research,connector,preprocessor,interest,reference,legacy,public
```

public에 있던 테이블은 각 domain schema로 이동되었으며, 이 모듈의 기존 SQL은 schema-qualified table name을 강제하지 않고 위 search_path 기반으로 동작한다. 따라서 `strategy_execution_order`, `strategy_execution_plan`, `strategy_position_state`, `connector_order_request`, `connector_fill` 같은 기존 테이블명 참조는 search_path 순서에 따라 `execution` 또는 `connector` schema의 테이블을 해석한다.

세부 DB 구조와 운영 주의사항은 `docs/database.md`를 참고한다.

## 파일 카탈로그와 주석 정리

전체 소스/문서 파일별 역할과 운영 주의사항은 `docs/source-file-catalog.md`에 정리한다.

2026-05-28 기준으로 Python 파일 상단에는 한글 module docstring을 추가해 각 파일의 역할, DB 접근, connector/API 호출 가능성을 설명했다. 자동 주문, fill sync, position sync, intraday monitor처럼 운영 영향이 큰 함수에는 짧은 function docstring을 추가했다.

이번 정리는 문서화와 설명 주석 추가만 포함하며 기능 로직, SQL 결과 의미, 실행 순서, endpoint, URL은 변경하지 않는다.

## 외부 의존성

정적 확인 기준 주요 의존성:

- `psycopg2`
- `psycopg2.extras`
- `decimal`
- `connector_buy`, `connector_sell`, connector quote 관련 모듈
- `port-interest-crawler` 또는 `port_interest_crawler`의 휴장일 helper

connector 모듈은 `C:\Workspaces\port-marketconnector` 경로를 import path에 추가해 가져오는 구조가 있다. 이 경로의 파일은 현재 루트 밖이므로 참고 또는 호출 대상일 뿐, 이 작업 범위에서는 수정하지 않는다.

## 설정

`db_config.py`와 `execution_config.py`는 환경변수로 DB, 계좌, broker, environment, strategy, sizing 설정을 읽는다.

- `INTEREST_DB_HOST` (default: `localhost`)
- `INTEREST_DB_PORT` (default: `5433`)
- `INTEREST_DB_NAME` (default: `portfolio`)
- `PORTFOLIO_DB_NAME` (default: `portfolio`, supported when the local environment uses this name)
- `INTEREST_DB_USER` (default: `postgres`)
- `INTEREST_DB_PASSWORD` (required, no default; use a placeholder such as `[REDACTED]` in documents)
- `PORT_ACCOUNT_NO`
- `PORT_BROKER_NAME`
- `PORT_ENVIRONMENT`
- `PORT_STRATEGY_NAME`
- `PORT_STRATEGY_VERSION`
- `PORT_MAX_ORDER_AMOUNT_RATIO`
- `PORT_MIN_ORDER_AMOUNT`

실제 password, token, account, webhook 값은 민감정보일 수 있으므로 환경변수로 관리하고 문서에 기록하지 않는다. 필요한 경우 `[REDACTED]`로 표기한다.

## 안전한 확인 명령

문서화나 리뷰 목적에서는 정적 확인 명령만 사용한다.

```powershell
rg --files
rg -n "pattern"
git status --short
git diff --stat
```

아래 작업은 안전한 확인 명령으로 취급하지 않는다.

- Python entrypoint 실행
- connector BUY/SELL 호출
- 체결 조회 sync 실행
- position sync 실행
- intraday monitor 실행
- DB DDL/DML 또는 commit이 발생하는 코드 실행
- 외부 API 호출 또는 크롤링 실행
