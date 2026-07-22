# Database

## 기본 DB

로컬 PostgreSQL 기본 DB name은 `portfolio`다. 기존 `interest_crawler` DB name은 더 이상 이 모듈 문서의 기본값으로 사용하지 않는다.

환경변수 설명은 아래 기준으로 정리한다.

- `INTEREST_DB_NAME`: default `portfolio`
- `PORTFOLIO_DB_NAME`: default `portfolio`, 로컬 환경에서 이 이름을 사용하는 경우 동일한 DB name 의미로 취급

## Schema-Per-Domain 구조

AWS Migration 준비 관점에서 단일 PostgreSQL DB `portfolio` 안에 domain별 schema를 두는 구조를 사용한다.

- `reference`
- `interest`
- `preprocessor`
- `research`
- `decision`
- `execution`
- `connector`
- `ops`
- `legacy`
- `public`

public에 있던 테이블은 domain schema로 이동되었고, public에 남은 운영 테이블은 없는 상태를 기준으로 문서화한다.

## Search Path

이 모듈의 DB connection search_path는 아래 순서를 사용한다.

```text
execution,decision,research,connector,preprocessor,interest,reference,legacy,public
```

schema-per-domain 전환 후에도 기존 SQL은 search_path 기반으로 동작한다. 예를 들어 `strategy_execution_order`, `strategy_execution_plan`, `strategy_position_state`는 `execution` schema에서, `connector_order_request`, `connector_fill`은 `connector` schema에서 해석되는 구조다.

## Execution 관점 Schema 책임

- `execution` — `strategy_execution_plan`, `strategy_execution_order`, `strategy_position_state`, `strategy_intraday_position_check` 저장 위치. 이 저장소가 직접 write 책임을 가진다.
- `decision` — `strategy_daily_position_decision`, daily BUY signal 등 Execution 후보 생성 입력 위치. Execution은 조회와 `execution_order_id` 연결 update 정도만 수행한다.
- `research` — backtest 결과(`strategy_backtest_run`, `strategy_backtest_daily`, `strategy_trade_log`) 조회 위치. `backtest_execution_run.py` 후보 생성 입력이다.
- `connector` — `connector_order_request`, `connector_fill`, `connector_balance_snapshot`, `connector_position_snapshot`, `connector_account` 조회 위치. Execution은 fill sync와 position sync 입력으로만 사용한다.
- `preprocessor` / `interest` / `reference` / `legacy` — feature 조회, 참조 데이터, 호환용 legacy 입력 위치. Execution 범위에서는 SELL evaluator, intraday monitor의 read 경로에 필요한 만큼만 접근한다.

이 문서는 Execution 관점 schema 설명만 유지한다. 다른 MS(Preprocessor, Research, Decision, Connector, View)의 schema 내부 상세는 확장하지 않는다.

## 보안

DB password, API token, 계좌번호, webhook URL 같은 민감정보는 환경변수로 관리한다. 문서에는 실제 값을 기록하지 않고 필요한 경우 `[REDACTED]`로 표기한다. DB host, port, user, connection string 원문도 기록하지 않는다.
