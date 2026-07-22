# AGENTS.md - port_strategy_execution

## 프로젝트

- 이 저장소는 포트폴리오 전략의 실행 후보 생성, 주문 실행 연계, 체결 동기화, 전략 포지션 상태 갱신을 담당하는 Python execution MS 루트다.
- 주요 역할은 daily buy/sell execution order 생성, 자동 buy/sell connector 호출, buy/sell fill sync, buy position sync, intraday stop sell monitor로 구분한다.
- `strategy_execution_order`, `strategy_execution_plan`, `strategy_position_state`, `connector_order_request`, `connector_fill` 등 주문/체결/포지션 관련 테이블과 직접 연결된다.
- 현재 구조는 패키지 디렉터리보다 루트 실행형 Python 스크립트 중심이다.

## 작업 범위

- 현재 `port_strategy_execution` 루트 안에서만 작업한다.
- 현재 루트 밖 파일은 참고용으로만 읽고 수정하지 않는다.
- 소스 코드 수정 전에는 파일 구조, entrypoint, DB 쓰기, connector 호출 가능성을 먼저 정적으로 확인한다.
- 문서 작업 요청 시 문서 파일만 수정한다.
- test/debug/output dump 파일은 운영 소스로 단정하지 않고 후보 또는 로컬 산출물로만 표현한다.

## 허용 작업

- README / docs / worklog 작성 및 수정
- Python 스크립트 구조의 정적 분석
- 실행하지 않는 범위의 import, entrypoint, SQL, connector 호출 지점 확인
- daily buy/sell build, auto execute, fill sync, position sync, intraday monitor, repository/config/sizing 계열 분류
- 실행 위험, 설정 항목, 검증 한계, 후속 작업 문서화

## 금지 작업

- 실제 execution/order 생성 실행 금지
- 자동 매수 실행 금지
- 자동 매도 실행 금지
- connector/broker/KIS 주문 API 호출 금지
- 체결 조회 실행 금지
- buy/sell fill sync 실행 금지
- position state 변경 실행 금지
- intraday monitor 실행 금지
- DB DDL/DML 실행 금지
- 외부 API 호출 금지
- 크롤링 실행 금지
- 주문 제출 또는 주문 실행 금지
- 민감정보 값 출력 또는 문서 기록 금지
- 실제 로컬 운영 설정 파일 수정 금지
- 명시 요청 없는 파일 삭제, 되돌리기, commit 금지

## 실행 금지 Entry Point

아래 파일은 주문 제출, 체결 조회, DB 쓰기, 포지션 상태 변경, intraday monitor 실행 가능성이 있으므로 명시 승인 없이 실행하지 않는다.

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

## 실행 위험 파일

- `execution_repository.py`
  - `strategy_execution_plan`, `strategy_execution_order`, `strategy_position_state`, `strategy_daily_position_decision`, `strategy_intraday_position_check` insert/update 가능성이 있다.
  - `connector_order_request`, `connector_fill`, `connector_position_snapshot` 조회 경로가 있다.
- `execution_execute_order.py`
  - `connector_buy.buy_stock`, `connector_sell.sell_stock` 호출 경로가 있다.
  - `--execute` 사용 시 connector 주문 요청 생성과 broker/KIS 주문 접수로 이어질 수 있다.
- `daily_auto_buy_execute_run.py`
  - READY buy execution order를 조회하고 connector BUY를 호출할 수 있다.
- `daily_auto_sell_execute_run.py`
  - READY sell execution order를 조회하고 connector SELL을 호출할 수 있다.
- `execution_sync_buy_fill.py`, `execution_sync_sell_fill.py`
  - `connector_order_request`, `connector_fill`을 조회하고 `strategy_execution_order` 상태를 `FILLED`로 갱신할 수 있다.
- `execution_sync_buy_position.py`
  - BUY fill 기준으로 `strategy_position_state` OPEN row를 생성할 수 있다.
- `daily_intraday_position_monitor_run.py`
  - intraday quote 조회, stop sell order 생성, monitor 결과 저장 가능성이 있다.

## 보안 규칙

- 비밀번호, 토큰, API key, 계좌번호, webhook URL, DB 접속정보 등 민감정보 값을 출력하거나 문서에 기록하지 않는다.
- 민감정보가 필요하면 `[REDACTED]`로 마스킹한다.
- `access_token.txt`는 민감정보 후보 파일로 취급하고 값을 읽거나 인용하지 않는다.
- `execution_config.py`의 환경변수 key는 문서화할 수 있으나 기본값이나 실제 값은 민감정보 가능성을 고려해 노출하지 않는다.

## 유지해야 할 계약

- 기존 DB 테이블명, 컬럼명, unique key, upsert 정책을 임의로 바꾸지 않는다.
- `strategy_execution_order`의 상태 전이와 `connector_order_request_id` 연결 정책을 임의로 바꾸지 않는다.
- `strategy_position_state`의 OPEN/CLOSED 상태, 수량 차감, sell ordered 상태 정책을 임의로 바꾸지 않는다.
- connector 호출 전후의 commit/rollback 흐름을 임의로 바꾸지 않는다.
- execution mode 정책(`DRY_RUN`, `MANUAL_TEST`, `PAPER_STRATEGY`, `LIVE_STRATEGY`)을 임의로 바꾸지 않는다.

## Git 규칙

- 작업 전후 `git status --short`로 변경 범위를 확인한다.
- 작업 후 `git diff --stat`로 변경 통계를 확인한다.
- 사용자 변경을 되돌리지 않는다.
- 명시 요청 없이 commit하지 않는다.

## 검증 명령

문서만 수정한 경우:

```powershell
git status --short
git diff --stat
```

코드 수정이 필요한 경우에도 실제 주문, connector, DB write, fill sync, position sync, intraday monitor, 외부 API 호출을 포함하는 검증은 실행하지 않는다.

## 완료 보고

작업 완료 시 아래 항목만 짧게 보고한다.

- 변경 파일
- 변경 요약
- 검증 결과
- 남은 위험 또는 후속 작업

## 문서화 규칙

- README.md는 프로젝트 이해, 실행 방법, 설정 방법, 주요 기능, 폴더 구조, 외부 의존성이 바뀐 경우에만 갱신한다.
- CHANGELOG.md에는 실제 변경된 주요 내용만 짧게 기록한다.
- docs/worklog/YYYY-MM-DD.md에는 작업 내용을 계획/완료 처리 형식으로 정리한다.
- worklog 작성 시 아래 들여쓰기 형식을 유지한다.
  - ` 1) 큰 작업 명` (앞 공백 1칸)
  - `   (1) 세부 작업` (앞 공백 3칸)
  - `       - 추가 설명` (앞 공백 7칸)
- `1.` 형식은 사용하지 않는다. markdown 자동 번호 목록으로 렌더링되어 들여쓰기와 상태 표기가 깨질 수 있다.
- 탭 문자를 섞지 않는다. 공백만 사용한다.
- 완료/예정/보류/실패/확인 상태를 작업 명 끝에 `:완료`, `:예정`, `:보류`, `:실패`, `:확인`으로 명확히 표시한다.
- 상태값은 `작업 명:완료`처럼 작업 명과 콜론 사이에 공백을 두지 않는다.
- 이미 작성된 과거 날짜 worklog의 기존 형식은 유지하고, 신규 날짜 worklog부터 위 규칙을 적용한다.
