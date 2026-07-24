# AGENTS.md - port_strategy_execution

## 1. 최우선 문서 가독성 규칙

이 규칙은 `port_strategy_execution`의 모든 Markdown 문서 작성과 수정에 우선 적용한다.

- 새로 만드는 독립 요약 표는 기본적으로 2컬럼을 사용한다.
- 기본 컬럼은 `항목 / 값`이며, 문맥에 따라 `파일 / 역할`, `단계 / 책임`, `상태 / 의미`를 사용할 수 있다.
- 기존 표에 행을 추가할 때는 기존 컬럼 구조를 유지한다.
- 표 셀은 가능하면 2문장 이하로 작성한다.
- 한 셀에 3개 이상의 사실을 장문으로 넣지 않는다.
- 3개 이상의 사실은 여러 행으로 나누거나 상세 문서 링크로 분리한다.
- 새로 만드는 표 셀은 300자를 넘기지 않는다.
- 한 줄은 500자를 넘기지 않는다.
- 긴 파일 목록, 전체 SQL, 전체 로그와 전체 DB 결과를 문서 본문에 붙이지 않는다.
- 같은 사실을 `README.md`, `CHANGELOG.md`, `docs/source-file-catalog.md`에 장문으로 반복하지 않는다.
- 제목만 다른 중복 섹션을 만들지 않는다.
- 현재 상태와 과거 변경 이력을 한 문단에서 섞지 않는다.
- 고유 파일명, 함수명, 테이블명, 컬럼명, 상태값과 실행 옵션은 코드 표기를 유지한다.
- 한글 Markdown은 UTF-8 No BOM으로 저장한다.
- 탭 문자와 후행 공백을 만들지 않는다.

## 2. 규칙 우선순위

| 범위 | 우선 기준 |
|---|---|
| 사용자 최신 명시 요청 | 가장 높은 작업 지시 |
| Workspace 공통 안전·작업 방식 | `.kiro/AGENTS.md` 최신 규칙 |
| Execution 책임·데이터·상태 계약 | 이 `AGENTS.md` |
| 직접 충돌 | 더 제한적이고 안전한 규칙 |

- `.kiro/AGENTS.md`의 공통 규칙을 무시하지 않는다.
- 이 파일은 `port_strategy_execution` 전용 책임과 위험을 보완한다.
- 사용자가 대상 파일과 범위를 지정하면 그 범위를 넘기지 않는다.
- 규칙이 충돌하거나 구현 사실이 불명확하면 실행하지 말고 정적 확인 결과와 한계를 보고한다.

## 3. 프로젝트 역할

`port_strategy_execution`은 전략 판단 결과를 실제 실행 계층의 계획과 주문 후보로 변환하고, 주문 요청·체결·전략 포지션 상태를 연결하는 Python MS다.

주요 책임은 아래와 같다.

| 영역 | 책임 |
|---|---|
| Daily BUY Execution | Daily BUY signal을 BUY execution order 후보로 변환 |
| Daily SELL Execution | Daily position SELL decision을 SELL execution order 후보로 변환 |
| Execution Plan | `strategy_execution_plan` 생성과 요약 상태 관리 |
| Execution Order | `strategy_execution_order` 생성·조회·상태 갱신 |
| Auto Execute | 승인된 READY BUY·SELL order를 connector 호출 경로에 전달 |
| Fill Sync | `connector_order_request`, `connector_fill` 기준 체결 상태 반영 |
| Position Sync | BUY fill 기반 OPEN 포지션 생성과 SELL fill 기반 수량 차감 |
| Intraday Monitor | OPEN 포지션 점검과 stop sell 후보 생성 |
| Backtest Candidate | Backtest 결과를 별도 execution 후보로 변환할 수 있는 경로 유지 |

현재 저장소는 패키지 계층보다 루트 실행형 Python 스크립트 중심이다.

## 4. 책임 경계

Execution이 직접 책임지는 영역과 다른 MS의 책임을 섞지 않는다.

| 영역 | 담당 |
|---|---|
| 원천 데이터 수집 | Crawler |
| Raw 전처리와 Feature 생성 | Preprocessor |
| Daily BUY signal 판단 | StrategyDecision |
| Daily Position HOLD·SELL·SKIP 판단 | StrategyDecision |
| Backtest와 Research Report | StrategyResearch |
| Execution Plan·Order와 전략 Position 연결 | StrategyExecution |
| Broker·KIS API 내부 구현과 Token | MarketConnector |
| 승인 UI와 화면 표시 | port-view |
| 전체 Daily Orchestration | Scheduler와 Step Functions |

- Execution은 BUY·SELL 판단 알고리즘 자체를 소유하지 않는다.
- Execution은 MarketConnector 내부 주문 API 구현을 복제하지 않는다.
- Execution은 전체 Step Functions 정의와 Scheduler 운영을 소유하지 않는다.
- 다른 MS의 내부 구현은 Execution에 필요한 입력·출력 계약 수준으로만 문서화한다.

## 5. 작업 범위

- 기본 작업 범위는 `port_strategy_execution` 루트와 하위 파일이다.
- 루트 밖 파일은 의존성 확인을 위한 읽기 전용으로만 사용한다.
- 사용자 요청 없이 다른 MS 파일을 수정하지 않는다.
- 문서 작업 요청이면 대상 Markdown 파일만 수정한다.
- 코드 작업 요청이면 지정된 Python·설정·테스트 파일만 수정한다.
- 전체 repository 전수 스캔, sub-agent, orchestrator와 새 scanner를 만들지 않는다.
- 존재하지 않는 파일, 테스트, wrapper와 table을 문서 편의를 위해 만들거나 추정하지 않는다.
- 생성된 report, dump, token, cache와 임시 파일을 운영 소스로 단정하지 않는다.

## 6. 작업 시작 전 정적 확인

수정 전 아래 순서로 필요한 파일만 직접 읽는다.

1. 사용자 지정 대상 파일
2. 이 `AGENTS.md`
3. 대상 파일이 참조하는 entrypoint와 helper
4. 관련 DB read·write와 connector 호출 지점
5. 관련 테스트와 실행 wrapper
6. 문서 변경 영향이 있는 `README.md`, `CHANGELOG.md`, `docs/source-file-catalog.md`

정적 확인 시 아래를 구분한다.

| 구분 | 판단 기준 |
|---|---|
| 현재 구현 | 실제 코드에서 직접 확인 |
| 운영 사실 | repository 또는 사용자 제공 근거로 확인 |
| 설계 원칙 | AGENTS와 문서에 명시된 규칙 |
| 미검증 | 코드·운영 근거가 부족한 내용 |
| 추정 금지 | 이름만 보고 책임·상태·테이블을 단정하지 않음 |

## 7. 실행 금지 기본 원칙

사용자의 명시 승인과 대상 환경 확인 없이 아래 작업을 수행하지 않는다.

- execution plan 또는 execution order 생성
- 자동 BUY 주문 실행
- 자동 SELL 주문 실행
- connector·broker·KIS 주문 API 호출
- 체결 조회와 fill sync
- position sync와 position state 변경
- intraday quote 조회와 monitor 실행
- intraday stop sell order 생성
- DB DDL·DML과 commit
- 외부 API 호출과 크롤링
- AWS CLI·SDK 호출
- ECS RunTask, SSM RunCommand, Step Functions 실행
- EventBridge Scheduler 변경
- Slack 또는 webhook 호출
- Git commit, push, reset, restore와 checkout

Python import도 module import 시 DB 연결이나 실행 side effect 가능성이 있으므로 문서 점검에서는 수행하지 않는다.

## 8. 실행 금지 Entry Point

아래 파일은 DB write, 주문 호출, 체결·포지션 변경 가능성이 있으므로 명시 승인 없이 실행하지 않는다.

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

- `--execute`, `--create-order`, `--confirm-live` 같은 옵션은 이름만 보고 안전하다고 판단하지 않는다.
- dry-run처럼 보이는 경로도 execution mode 또는 검증 결과를 DB에 저장할 수 있으므로 실제 코드를 확인한다.
- `if __name__ == "__main__":`가 있는 loader·helper는 단순 import 대상이라고 단정하지 않는다.

## 9. 주요 파일 책임

### 9.1 Daily BUY

| 파일 | 확인할 책임 |
|---|---|
| `daily_buy_execution_run.py` | 최신 Daily Run과 BUY signal 조회, Plan·Order 생성 흐름 |
| `execution_daily_signal_builder.py` | BUY signal을 execution order payload로 변환 |
| `execution_buy_sizing.py` | 현금·보유·목표 금액 기반 주문 수량 계산 |
| `execution_repository.py` | Plan·Order upsert와 summary 갱신 |

### 9.2 Daily SELL

| 파일 | 확인할 책임 |
|---|---|
| `daily_sell_execution_run.py` | 최신 Position Decision Run과 SELL decision 조회 |
| `execution_daily_position_sell_builder.py` | SELL decision을 execution order payload로 변환 |
| `execution_repository.py` | Order 저장과 decision row 연결 |

### 9.3 Auto Execute

| 파일 | 확인할 책임 |
|---|---|
| `daily_auto_buy_execute_run.py` | READY BUY 조회와 connector BUY 호출 경로 |
| `daily_auto_sell_execute_run.py` | READY SELL 조회, 매도 가능 수량 확인과 connector SELL 호출 |
| `execution_execute_order.py` | 단일 Order 실행 모드와 live 확인 경계 |

### 9.4 Fill·Position Sync

| 파일 | 확인할 책임 |
|---|---|
| `execution_sync_buy_fill.py` | BUY fill 집계와 execution order 상태 반영 |
| `execution_sync_sell_fill.py` | SELL fill 집계와 remaining quantity·상태 반영 |
| `execution_sync_buy_position.py` | FILLED BUY 기반 OPEN position 생성 또는 병합 |

### 9.5 Intraday

| 파일 | 확인할 책임 |
|---|---|
| `execution_position_loader.py` | 전략 OPEN position과 connector snapshot 결합 |
| `execution_sell_evaluator.py` | Position·Stock Feature·Market Feature 평가 |
| `execution_sell_builder.py` | POSITION_SELL execution order 후보 생성 |
| `daily_intraday_position_monitor_run.py` | 점검 결과 저장과 hard stop order 후보 생성 |

### 9.6 공통 DB·설정

| 파일 | 확인할 책임 |
|---|---|
| `execution_repository.py` | Execution DB read·write 집중 지점 |
| `execution_db.py` | Connection과 fetch·execute helper |
| `db_config.py` | DB 환경변수와 search path 설정 |
| `execution_config.py` | 계좌·broker·environment·strategy·sizing 설정 |

## 10. Daily Execution 흐름 계약

문서와 코드에서 아래 단계를 혼동하지 않는다.

| 단계 | Execution 관점 |
|---|---|
| Step 8 | Daily BUY execution order 후보 생성 |
| Step 9 | Daily SELL execution order 후보 생성 |
| Step 10 | READY SELL auto execute 경로 |
| Step 11 | READY BUY auto execute 경로 |
| Step 12~13 | MarketConnector 주문 제출·조회 구간 |
| Step 14 | SELL fill sync |
| Step 15 | BUY fill sync |
| Step 16 | BUY position sync |
| Step 17 | MarketConnector balance refresh 구간 |

- 실제 Step 번호와 호출 파일은 orchestration 정의 또는 운영 근거로 확인한다.
- Execution 내부 파일만 보고 전체 state machine 순서를 확정하지 않는다.
- Step 12~13과 Step 17의 내부 구현을 Execution 책임으로 확장하지 않는다.
- 후보 생성 성공, 주문 제출 성공, 체결 성공, position sync 성공을 하나의 성공 상태로 합치지 않는다.

## 11. Execution Plan 계약

`strategy_execution_plan` 변경 시 아래를 확인한다.

- plan source와 source run 식별자
- business date 또는 trade date
- strategy name과 version
- plan status
- order count와 summary 집계
- 동일 source에 대한 재실행 정책
- create-or-get 또는 upsert 기준
- 빈 후보 회차 처리
- 일부 order 실패 시 plan status
- 최종 완료 판단 시점

Plan status 문자열과 unique key는 코드에서 확인한 값만 사용한다.

## 12. Execution Order 계약

`strategy_execution_order` 변경 시 아래를 확인한다.

- side와 order type
- source type과 source row 식별자
- ticker와 order quantity
- limit·market 등 가격 정책
- execution mode
- status 전이
- connector order request 연결
- request quantity와 filled quantity
- average fill price
- error·reason payload
- idempotency 기준
- retry 가능 상태
- 최종 상태와 재처리 정책

- `READY`, `REQUESTED`, `ACCEPTED`, `FILLED`, `FAILED` 같은 상태값은 실제 코드와 DB 계약을 확인한다.
- 문서 편의를 위해 존재하지 않는 상태값을 추가하지 않는다.
- 동일 source row가 중복 order를 만들지 않도록 unique key와 upsert 기준을 유지한다.
- connector request가 이미 연결된 order를 재제출하는 경로를 임의로 만들지 않는다.

## 13. 주문 제출 안전 계약

Auto BUY·SELL과 단일 Order 실행 경로를 수정할 때 아래를 반드시 확인한다.

| 항목 | 확인 기준 |
|---|---|
| 대상 상태 | 실제 제출 가능한 execution order status |
| 실행 모드 | `DRY_RUN`, `MANUAL_TEST`, `PAPER_STRATEGY`, `LIVE_STRATEGY` |
| 승인 경계 | 사용자·운영자 승인 또는 orchestration gate |
| 중복 제출 | 기존 connector request와 broker order 존재 여부 |
| 수량 | requested quantity와 주문 가능 quantity |
| 환경 | local·paper·live 분리 |
| 실패 처리 | DB 상태, rollback, retry와 exit code |

- Live 경로의 확인 조건을 약화하지 않는다.
- `--execute` 기본값과 명시 여부를 임의로 바꾸지 않는다.
- connector helper 호출 전 DB commit 여부와 호출 후 상태 기록 순서를 확인한다.
- 외부 주문 성공 후 로컬 DB 기록 실패 가능성을 고려한다.
- 로컬 DB 상태만으로 broker 주문 미제출을 단정하지 않는다.
- timeout과 예외 발생 시 재호출이 중복 주문으로 이어지는지 확인한다.

## 14. BUY Sizing 계약

`execution_buy_sizing.py`와 BUY builder를 수정할 때 아래를 확인한다.

- 사용 가능 현금
- 현재 보유 수량과 평가액
- 목표 금액 또는 목표 비중
- 최대 주문 금액 비율
- 최소 주문 금액
- 기준 가격
- 정수 수량 반올림
- 0주와 최소 금액 미달 처리
- 여러 BUY 후보 간 현금 배분 순서
- 동일 ticker 기존 OPEN position 처리
- 계좌 snapshot 최신성

Sizing 계산은 단위, 반올림과 가격 시점을 추정하지 않는다.

## 15. SELL 수량 계약

SELL order 생성과 제출 시 아래를 확인한다.

- 전략 position remaining quantity
- connector position snapshot의 보유 수량
- 매도 가능 수량
- 기존 SELL_ORDERED 또는 미체결 주문
- partial fill 누적 수량
- 중복 SELL 방지 기준
- 전량·부분 매도 정책
- 0주와 음수 방지
- position status 전이

전략 position 수량과 broker snapshot 수량이 다를 때 임의로 한쪽을 정답으로 선택하지 않는다.

## 16. Fill Sync 계약

BUY·SELL fill sync 변경 시 아래를 확인한다.

| 항목 | 확인 기준 |
|---|---|
| 원본 요청 | `connector_order_request` 연결 기준 |
| 체결 원본 | `connector_fill` 집계 기준 |
| 중복 Fill | fill unique key와 중복 제거 |
| 부분 체결 | requested quantity와 cumulative filled quantity 비교 |
| 평균가 | weighted average 계산 기준 |
| 최종 상태 | FILLED 판정 조건 |
| 무체결 | 상태 유지 또는 별도 상태 전이 |
| 재실행 | 동일 fill 재반영 방지 |

- 체결 row 존재만으로 전량 FILLED를 단정하지 않는다.
- 부분 체결을 전량 체결로 처리하지 않는다.
- 취소·거부·정정 상태가 있다면 실제 connector 계약을 확인한다.
- fill sync와 position sync의 transaction 경계를 임의로 합치거나 분리하지 않는다.

## 17. Position State 계약

`strategy_position_state` 변경 시 아래를 유지한다.

- BUY fill 이전에 OPEN position을 확정하지 않는다.
- 동일 ticker와 strategy의 기존 OPEN row 병합 기준을 확인한다.
- quantity, remaining quantity와 average entry price 계산을 확인한다.
- SELL 주문 제출 상태와 SELL fill 완료 상태를 구분한다.
- partial SELL은 remaining quantity만 차감한다.
- remaining quantity가 0이 되는 조건에서만 CLOSED 전이를 검토한다.
- 음수 remaining quantity를 허용하지 않는다.
- execution order와 source decision 연결을 보존한다.
- 중복 sync가 quantity를 반복 증가·차감하지 않도록 한다.

## 18. Intraday Monitor 계약

장중 monitor와 stop sell 후보 변경 시 아래를 확인한다.

- OPEN position 조회 기준
- latest connector position snapshot 선택 기준
- latest stock feature와 market feature 기준일
- quote provider와 quote timestamp
- 정상 점검 결과 저장 정책
- 이상·누락 데이터 처리
- hard stop 조건
- HOLD·SELL 결과와 reason
- `--create-order` 명시 여부
- 동일 position·점검 시각 중복 order 방지
- approval gate와 실제 주문 제출 분리

- 점검 결과 저장과 order 생성은 서로 다른 영향으로 구분한다.
- 정상 결과도 `strategy_intraday_position_check`에 저장하는 현재 정책을 임의로 되돌리지 않는다.
- intraday stop order 생성 성공을 broker 주문 성공으로 표현하지 않는다.

## 19. Backtest 기반 후보 계약

`backtest_execution_run.py`, `execution_builder.py`, `execution_build_candidates.py`는 Daily 운영 경로와 별도 계열로 취급한다.

- 실제 입력 table과 run 선택 기준을 확인한다.
- backtest BUY·SELL row를 Daily signal 또는 Daily position decision으로 표현하지 않는다.
- 운영 Daily plan과 backtest plan의 source type을 혼합하지 않는다.
- legacy 또는 독립형 후보 생성 파일은 현재 운영 entrypoint인지 확인한다.
- 단순 파일명만으로 삭제 후보로 분류하지 않는다.

## 20. DB 계약

현재 문서 기준 주요 write 대상은 아래와 같다.

- `strategy_execution_plan`
- `strategy_execution_order`
- `strategy_position_state`
- `strategy_daily_position_decision`
- `strategy_intraday_position_check`

주요 connector read 대상은 아래와 같다.

- `connector_order_request`
- `connector_fill`
- `connector_account`
- `connector_balance_snapshot`
- `connector_position_snapshot`

DB 변경 시 아래를 확인한다.

- 실제 schema와 search path
- table과 column 존재 여부
- primary key와 unique key
- foreign key 또는 논리 연결
- insert·update·upsert conflict target
- transaction과 rollback
- commit 위치
- cursor와 connection close
- rowcount 검증
- empty result 처리
- duplicate row와 join cardinality
- timezone과 business date

컬럼명을 예상하지 않는다. `information_schema` 또는 실제 코드에서 확인한 이름만 사용한다.

## 21. 환경변수와 설정

- DB 환경변수는 `db_config.py` 실제 구현을 기준으로 한다.
- `INTEREST_DB_PASSWORD` 실제 값은 읽거나 기록하지 않는다.
- `PORTFOLIO_DB_NAME` 등 호환 환경변수는 실제 코드 사용 여부를 확인한 뒤 문서화한다.
- 계좌번호, broker, environment, strategy와 sizing key는 key 이름만 문서화할 수 있다.
- default 값은 실제 코드에 있고 민감하지 않은 경우에만 기록한다.
- local·paper·live 환경 값과 계좌를 혼합하지 않는다.
- execution schema search path는 실제 connection 설정과 문서가 일치하는지 확인한다.

## 22. 외부 의존성

- MarketConnector 모듈은 외부 의존성으로 취급한다.
- connector 모듈 import path를 임의로 변경하지 않는다.
- crawler holiday helper 의존성은 실제 import와 호출 위치를 확인한다.
- 외부 모듈의 내부 책임을 Execution 문서에 복제하지 않는다.
- `requirements.txt`와 실제 import가 다르면 누락·불필요 의존성을 보고한다.
- 표준 라이브러리를 requirements에 추가하지 않는다.

## 23. 보안과 민감정보

- `access_token.txt`는 민감정보 후보 파일이다.
- 파일 값, token, API key, password, 계좌번호와 webhook URL을 읽거나 인용하지 않는다.
- DB host, ARN, image URI, subnet, security group, broker order number와 connector order id는 문서에 원문으로 남기지 않는다.
- 운영 식별자가 필요하면 `<EXECUTION_ECS_TASK>`, `<CONNECTOR_ORDER_ID>` 또는 `[REDACTED]`를 사용한다.
- secret 값을 명령에 직접 넣지 않는다.
- 사용자가 이미 설정한 환경변수 또는 local secret loader를 사용한다.
- password 값을 사용자에게 다시 입력하라고 요구하지 않는다.

## 24. 소스 수정 규칙

- 원본 Python 파일을 무차별 문자열 치환하지 않는다.
- 지정된 파일만 국소 수정한다.
- 함수 signature, return shape와 exception 계약을 먼저 확인한다.
- import 순환과 module side effect를 확인한다.
- DB write, connector 호출과 상태 전이 순서를 보존한다.
- status 문자열과 reason code를 임의로 바꾸지 않는다.
- 새로운 retry를 추가할 때 중복 주문 위험을 먼저 분석한다.
- log에 민감정보와 전체 payload를 출력하지 않는다.
- 주석은 구현을 그대로 설명하고 미래 계획을 현재 기능처럼 쓰지 않는다.

## 25. 테스트와 검증

코드 수정 시 실제 주문이나 DB write 없이 가능한 검증을 우선한다.

- `python -m py_compile <file>`
- side effect 없는 순수 함수 단위 테스트
- fixture와 mock 기반 테스트
- 정적 import 경로 확인
- 상태 전이와 idempotency 테스트
- partial fill과 duplicate fill 테스트
- 0주, 음수, 최소 금액과 경계값 테스트
- transaction rollback 테스트

다음 검증은 명시 승인 없이 실행하지 않는다.

- 실제 connector BUY·SELL
- 실제 broker 주문
- 실제 fill 조회와 sync
- 실제 position sync
- 실제 intraday quote와 monitor
- 실제 DB write
- 실제 AWS·SSM·ECS·Step Functions 실행

실행하지 못한 검증을 통과했다고 기록하지 않는다.

## 26. 문서 체계

| 문서 | 역할 |
|---|---|
| `AGENTS.md` | Execution 작업·상태·데이터·안전 규칙 |
| `README.md` | 현재 구조와 운영 AS-IS |
| `CHANGELOG.md` | 실제 변경 이력과 당시 사실 |
| `docs/source-file-catalog.md` | 파일 책임, 입출력과 변경 영향 |

- 날짜별 `docs/worklog/*.md`를 새로 만들지 않는다.
- 삭제된 worklog 디렉터리나 파일을 현재 구조에 다시 추가하지 않는다.
- 과거 CHANGELOG에 기록된 worklog 생성 사실은 당시 이력이므로 삭제하지 않는다.
- 새 문서는 사용자가 명시한 경우에만 만든다.

## 27. 문서 갱신 조건

### 27.1 README.md

아래가 바뀌면 관련 섹션만 갱신한다.

- 프로젝트 책임 경계
- Daily Step의 Execution 역할
- entrypoint와 실행 흐름
- Plan·Order·Fill·Position 계약
- 설정과 외부 의존성
- 현재 파일 구조
- 운영 안전 기준

### 27.2 CHANGELOG.md

- 실제 변경된 파일과 내용을 기록한다.
- 문서 변경과 기능 변경을 구분한다.
- 실제 실행 여부를 구분한다.
- 과거 이력을 현재 상태에 맞추기 위해 왜곡하지 않는다.
- 일회성 로그, command id와 전체 DB 결과를 넣지 않는다.

### 27.3 docs/source-file-catalog.md

아래가 바뀌면 같은 작업에서 반드시 갱신 여부를 확인한다.

- 파일 추가·삭제·이름 변경
- entrypoint 책임 변경
- builder·sizing·repository 역할 변경
- DB read·write 대상 변경
- connector 호출 경로 변경
- status 전이 변경
- fill·position sync 책임 변경
- intraday monitor 책임 변경
- Dockerfile, requirements와 wrapper 변경
- 문서 파일 구조 변경

변경 영향이 없으면 불필요하게 수정하지 않고 완료 보고에 `갱신 불필요`로 기록한다.

## 28. 파일 삭제와 정리

파일을 삭제하거나 legacy로 분류하기 전에 아래를 확인한다.

- import 또는 dynamic import
- root entrypoint 호출
- Docker CMD 또는 command override
- ECS·Batch·Step Functions·Scheduler 호출
- PowerShell·BAT·CMD·Shell wrapper
- 테스트와 fixture 참조
- DB output과 report 소비
- 문서 링크
- 외부 MS 호출

근거가 부족하면 `정리 후보`로만 기록하고 삭제하지 않는다.

## 29. Git 규칙

- 작업 전후 `git status --short`로 변경 범위를 확인한다.
- 작업 후 `git diff --stat`와 `git diff --check`를 확인한다.
- 사용자 변경을 되돌리지 않는다.
- 명시 요청 없이 `git add`, `commit`, `push`하지 않는다.
- 명시 요청 없이 `reset`, `restore`, `checkout`하지 않는다.
- repository가 제공되지 않은 첨부 파일 작업에서는 Git 검증을 수행한 것처럼 기록하지 않는다.

## 30. 완료 전 정합성 점검

문서 또는 코드 수정 후 관련 범위에서 아래를 확인한다.

- Execution 책임 경계
- Daily Step 8~17 표현
- BUY·SELL 후보 생성 입력
- Plan과 Order 상태
- 중복 Order 방지
- connector request 연결
- Auto Execute 승인·환경 경계
- partial fill과 FILLED 판정
- BUY position 생성과 병합
- SELL remaining quantity 차감
- intraday check 저장과 order 생성 분리
- backtest 후보와 Daily 후보 분리
- DB schema·search path
- 환경변수 실제 사용 여부
- requirements와 import
- 파일 구조와 문서 링크
- source-file-catalog 갱신 여부
- worklog 신규 생성 지시 유무
- 과거 CHANGELOG 역사 보존
- 민감정보 원문 신규 기록 여부
- 300자 초과 신규 셀
- 500자 초과 신규 라인
- UTF-8 No BOM
- 탭과 후행 공백

## 31. 완료 보고

완료 보고는 2컬럼 표 중심으로 짧게 작성한다.

| 항목 | 보고 내용 |
|---|---|
| 변경 파일 | 실제 수정 파일 |
| 변경 요약 | 책임·계약·구조 변경 |
| 정적 검증 | 수행한 검증과 결과 |
| 실행 검증 | 수행 여부와 미수행 이유 |
| 문서 정합 | README·CHANGELOG·Catalog 갱신 여부 |
| 민감정보 | 원문 기록 여부 |
| 남은 위험 | 실제 코드·운영 대조 필요 항목 |

- 문서 작업만 수행했다면 실제 주문·DB·AWS 실행은 0건이어야 한다.
- 미수행 검증을 성공으로 기록하지 않는다.
- 불명확한 구현 사실은 `미검증`으로 남긴다.
