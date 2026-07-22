# Source File Catalog

이 문서는 AWS Migration 전 초기 정리를 위해 `port_strategy_execution` 루트의 주요 파일을 정적 분석 기준으로 정리한 파일 카탈로그다. 실제 주문 실행, connector 호출, 체결 조회, DB DDL/DML, 외부 API 호출은 수행하지 않았다.

## 루트 문서

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `AGENTS.md` | 작업 지침 문서 | 이 저장소의 작업 범위, 실행 금지 entrypoint, 보안 규칙을 정의한다. | Codex/작업자의 안전한 정적 분석 기준을 제공한다. | 운영 주문/DB write 가능 파일을 실행하지 않는 규칙을 우선 적용한다. |
| `README.md` | 프로젝트 개요 문서 | execution MS의 역할, 파일 구조, 실행 주의사항, 설정 항목을 설명한다. | 신규 작업자가 모듈 구조와 위험 지점을 빠르게 파악하게 한다. | 민감정보 실제 값은 기록하지 않고 환경변수/로컬 설정 주입만 설명한다. |
| `CHANGELOG.md` | 변경 이력 문서 | 날짜별 주요 변경사항과 기능 변경 여부를 기록한다. | 미커밋 변경과 문서화 작업의 추적성을 제공한다. | 실제 기능 로직 변경이 없으면 기능 변경 없음으로 명시한다. |

## 설정 및 공통 DB

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `db_config.py` | DB 접속 설정 구성 | `INTEREST_DB_*` 환경변수를 읽어 psycopg2 접속 설정을 만든다. | 공통 DB 접속 정보와 schema search_path를 제공한다. | password 값은 필수 환경변수로만 주입하며 실제 값을 출력하거나 문서화하지 않는다. |
| `execution_config.py` | execution 공통 설정 | DB, 계좌, broker, strategy, sizing 관련 환경변수를 읽는다. | 실행 스크립트와 builder가 공유하는 설정 상수를 제공한다. | 계좌/환경/전략명 정책 변경은 주문 대상과 규모에 영향을 줄 수 있다. |
| `execution_db.py` | DB helper | `get_conn`, `fetch_one`, `fetch_all`, `execute_one` helper를 제공한다. | repository와 legacy 스크립트의 DB 접근 기반이다. | 함수 호출은 실제 DB 접속/SQL 실행으로 이어진다. |
| `execution_repository.py` | execution repository | plan/order/position/daily decision/intraday check insert/update와 connector 조회 SQL을 모은다. | DB read/write와 상태 전이의 중심 모듈이다. | 테이블명, unique key, upsert 정책, 상태 전이, connector_order_request_id 연결 정책을 임의 변경하지 않는다. |

## 컨테이너 / 의존성

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `Dockerfile` | Execution 컨테이너 이미지 정의 | `python:3.13-slim` 기반으로 `port_strategy_execution` 디렉터리를 `/app`에 복사하고 requirements를 설치한다. | ECS RunTask/컨테이너 실행 대상 이미지의 base 정의를 제공한다. | build context 상위에 `port_strategy_execution` 디렉터리가 포함되도록 유지한다. 실제 image URI, tag, digest는 문서에 원문 기록하지 않고 `<EXECUTION_ECR_IMAGE_URI>` placeholder로만 표기한다. |
| `requirements.txt` | Python 런타임 의존성 목록 | `psycopg2-binary` 등 최소 런타임 의존성만 명시한다. | 컨테이너 이미지 build 시 pip install 대상이 된다. | 의존성 추가는 실행 위험/보안 영향 검토 후 반영한다. |
| `create_execution_docker_files.py` | Docker 산출물 재생성 헬퍼 | `requirements.txt`와 `Dockerfile`을 지정 경로에 재작성한다. | 로컬 개발자가 정합성 유지 목적으로 실행할 수 있는 헬퍼다. | 운영 entrypoint 아님. 실제 실행 시 파일이 덮어써지므로 diff를 확인한 뒤에만 사용한다. |

## Daily BUY Execution

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `daily_buy_execution_run.py` | Daily BUY 후보 생성 entrypoint | 최신 daily run, BUY signal, 계좌/잔고를 읽어 BUY execution order 후보를 생성한다. | daily BUY batch의 실행 후보 생성 흐름을 담당한다. AWS Paper Daily Step 8(DAILY_BUY_EXECUTION) ECS RunTask 실행 대상 후보다. | 실행 시 DB write(`strategy_execution_plan`, `strategy_execution_order`)가 가능하므로 명시 승인 없이 실행하지 않는다. |
| `execution_daily_signal_builder.py` | Daily BUY order builder | daily BUY signal을 `strategy_execution_order` 저장용 dict로 변환한다. | sizing, validation, 현재 포지션/가격 조회 결과를 주문 후보 payload에 반영한다. | 주문 수량/금액 계산 의미 변경은 실제 주문 규모에 영향을 준다. |
| `execution_buy_sizing.py` | BUY sizing helper | 목표 금액, 현금, 최소 주문 금액 기준으로 BUY 수량과 사유를 계산한다. | BUY 주문 후보의 수량 산정 정책을 분리한다. | 계산식 변경은 전략 주문 규모 변경으로 취급한다. |

## Daily SELL Execution

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `daily_sell_execution_run.py` | Daily SELL 후보 생성 entrypoint | latest daily position decision의 SELL 대상을 execution order 후보로 만든다. | daily position decision과 execution order를 연결한다. AWS Paper Daily Step 9(DAILY_SELL_EXECUTION) ECS RunTask 실행 대상 후보다. | 실행 시 DB write 및 `strategy_daily_position_decision.execution_order_id` 갱신이 가능하다. |
| `execution_daily_position_sell_builder.py` | Daily SELL order builder | SELL decision row를 `DAILY_POSITION_SELL` order 저장용 dict로 변환한다. | 원본 decision payload와 포지션 연결 정보를 보존해 후속 sync 기준을 만든다. | decision id, position_state_id, 주문 수량 의미를 변경하지 않는다. |

## 자동 주문 실행

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `daily_auto_buy_execute_run.py` | 자동 BUY 실행 entrypoint | READY daily BUY order를 조회해 connector BUY를 호출할 수 있다. | PAPER_STRATEGY BUY 주문 제출과 결과 상태 갱신을 담당한다. AWS Paper Daily Step 11(DAILY_AUTO_BUY) ECS RunTask 실행 대상 후보다. | 자동 주문 제출 경로이므로 실행 금지 대상이다. broker/KIS 실제 주문 API 호출은 MarketConnector 책임이며 이 저장소에서 직접 수행하지 않는다. |
| `daily_auto_sell_execute_run.py` | 자동 SELL 실행 entrypoint | READY daily/intraday SELL order를 조회해 connector SELL을 호출할 수 있다. | 매도 가능 수량 재검증, SELL 주문 제출, position SELL_ORDERED 갱신을 담당한다. AWS Paper Daily Step 10(DAILY_AUTO_SELL) ECS RunTask 실행 대상 후보다. | 자동 매도 및 포지션 상태 변경 경로이므로 실행 금지 대상이다. |
| `execution_execute_order.py` | 수동 단일 주문 실행 entrypoint | 특정 execution order id를 execution mode에 따라 connector로 제출할 수 있다. | DRY_RUN/MANUAL_TEST/PAPER_STRATEGY/LIVE_STRATEGY 정책 검증과 주문 실행을 담당한다. | `--execute`와 live confirm 정책, connector 호출 전후 commit/rollback 흐름을 변경하지 않는다. `LIVE_STRATEGY`는 live 환경과 `--confirm-live` 확인이 필요하다. |

## Fill Sync / Position Sync

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `execution_sync_buy_fill.py` | BUY 체결 동기화 | `connector_order_request`, `connector_fill`을 조회해 execution order를 FILLED로 갱신할 수 있다. | 주문 요청과 체결 내역을 요약해 BUY fill 상태를 반영한다. AWS Paper Daily Step 15(SYNC_BUY_FILL) ECS RunTask 실행 대상 후보다. | 체결 조회와 DB update가 발생하므로 실행 금지 대상이다. broker/KIS 직접 조회는 이 저장소 책임 아님. |
| `execution_sync_sell_fill.py` | SELL 체결 동기화 | connector SELL 체결을 조회해 order FILLED와 `strategy_position_state.remaining_qty` 차감을 수행할 수 있다. | 매도 체결 후 전략 포지션 상태를 갱신한다. AWS Paper Daily Step 14(SYNC_SELL_FILL) ECS RunTask 실행 대상 후보다. | 포지션 수량/상태 전이에 직접 영향을 주므로 실행 금지 대상이다. |
| `execution_sync_buy_position.py` | BUY 포지션 동기화 | FILLED BUY order를 기준으로 OPEN position row를 생성하거나 기존 OPEN에 추가 매수를 병합할 수 있다. | 매수 체결 결과를 `strategy_position_state`에 반영한다. AWS Paper Daily Step 16(SYNC_BUY_POSITION) ECS RunTask 실행 대상 후보다. | 중복 포지션 생성 방지와 additional_buys payload append 정책을 유지한다. |

## Position / Intraday Monitor

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `execution_position_loader.py` | 포지션 context loader | OPEN position과 connector position snapshot을 결합한다. | SELL 평가와 intraday monitor가 사용할 position context를 만든다. | DB 조회를 수행하며 파일 하단에 실행 가능한 main이 있다. |
| `execution_sell_evaluator.py` | SELL/HOLD 평가 helper | 포지션, 종목 feature, 시장 feature로 SELL/HOLD 판단 payload를 만든다. | 포지션 매도 판단 정책을 계산한다. | 기준 변경은 전략 판단 결과 변경으로 취급한다. |
| `execution_sell_builder.py` | Position SELL 후보 builder | OPEN position을 평가해 POSITION_SELL order 후보를 생성/저장할 수 있다. | position evaluation update와 execution order upsert를 결합한다. | 실행 시 DB write가 가능하므로 실행 금지 대상이다. |
| `daily_intraday_position_monitor_run.py` | 장중 포지션 monitor | OPEN position의 현재가를 조회해 손절 후보와 `INTRADAY_STOP_SELL` order를 만들 수 있다. | intraday check 저장, 손절 후보 판정, stop sell order 생성 흐름을 담당한다. 장중 10분 intraday evaluate 흐름의 실행 대상 후보다. | connector quote 외부 API 조회와 DB write(`strategy_intraday_position_check`, `strategy_execution_order`) 가능성이 있다. 정상/이상 여부와 관계없이 점검 결과를 저장하는 정책(2026-05-27 미커밋 변경 정합)을 유지한다. `--create-order` 사용 여부에 따라 stop sell order 생성 가능성이 달라진다. broker 주문 제출은 별도 approval gate 경유이며 이 저장소 범위 밖. |

## Backtest / Legacy 후보

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `backtest_execution_run.py` | Backtest 기반 후보 생성 entrypoint | backtest run/daily/trade log를 기준으로 execution order 후보를 생성할 수 있다. | backtest 결과를 실행 후보 테이블 구조로 변환한다. | 실행 시 plan/order DB write가 가능하다. |
| `execution_builder.py` | Backtest order builder | backtest BUY/SELL trade log를 order 저장용 dict로 변환한다. | validation, 가격, 포지션 상태를 반영한 후보 payload를 만든다. | backtest 후보 변환 의미와 수량 계산을 임의 변경하지 않는다. |
| `execution_build_candidates.py` | legacy 후보 생성 스크립트 | 자체 DB helper와 upsert SQL을 포함한 독립형 후보 생성 흐름이다. | 과거/독립 실행 후보 생성 경로로 보인다. | 정리 후보. 삭제하지 말고 실행 금지 대상으로 유지한다. 로컬 설정 상수와 DB write 경로가 있어 민감정보 노출에 주의한다. |

## 운영 보조 파일과 문서

| 파일 경로 | 한글 제목 | 파일 내용 | 주요 역할 | 수정/운영 시 주의사항 |
|---|---|---|---|---|
| `docs/database.md` | DB 구조 문서 | 기본 DB name, schema-per-domain 구조, search_path, 보안 주의사항을 정리한다. | AWS Migration 전 DB 구조 이해를 돕는다. | 실제 credential 값은 기록하지 않는다. |
| `docs/source-file-catalog.md` | 전체 파일 카탈로그 | 루트 주요 파일의 역할, 내용, 운영 주의사항을 한글로 정리한다. | 초기 정리와 인수인계용 소스 맵을 제공한다. | 파일 추가/역할 변경 시 갱신한다. |
| `docs/worklog/2026-05-26.md` | 2026-05-26 작업 로그 | 초기 문서화와 로컬 산출물 정리 기록을 담는다. | 과거 작업 이력을 보존한다. | 기존 기록 형식을 유지한다. |
| `docs/worklog/2026-05-27.md` | 2026-05-27 작업 로그 | DB 접속정보 외부화와 schema-per-domain 문서화 기록을 담는다. | 미커밋 변경 요약의 배경 자료다. | 실제 민감정보 값은 추가하지 않는다. |
| `docs/worklog/2026-05-28.md` | 2026-05-28 작업 로그 | 미커밋 변경 확인, 파일 카탈로그 생성, 주석 정리 작업을 기록한다. | 초기 정리 작업의 추적성을 제공한다. | 들여쓰기와 상태 표기 형식을 유지한다. |
| `docs/worklog/2026-07-01.md` | 2026-07-01 작업 로그 | PORT-STRATEGY-EXECUTION 문서 최신화(AWS Step 8~17 역할, intraday, ECS RunTask 대상, 책임 경계) 작업을 기록한다. | 문서 최신화 작업의 추적성을 제공한다. | port-view/.kiro 하위 문서에서 Execution 관련 내용만 선별 반영했음을 유지한다. |
| `access_token.txt` | 민감정보 후보 파일 | 값은 읽거나 인용하지 않는다. | connector/API 인증 관련 로컬 산출물 후보로 취급한다. | 민감정보 후보이므로 문서에는 값이나 일부 문자열도 기록하지 않는다. |

## 제외 기준

- `__pycache__`, `.gradle`, `target`, `build`, IDE 임시 파일, 컴파일 산출물은 카탈로그 대상에서 제외한다.
- unused/legacy 의심 파일은 삭제하지 않고 위 표에 정리 후보로만 표시한다.
