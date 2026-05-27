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

## 보안

DB password, API token, 계좌번호, webhook URL 같은 민감정보는 환경변수로 관리한다. 문서에는 실제 값을 기록하지 않고 필요한 경우 `[REDACTED]`로 표기한다.
