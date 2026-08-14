# Source File Catalog

`port_strategy_execution`의 주요 소스와 문서가 담당하는 책임,
입력·출력, DB 영향과 변경 시 확인 대상을 정리한다.

이 문서는 전체 파일 Inventory가 아니라 Execution 운영과 유지보수에 중요한
파일 책임 지도다.

실제 주문 생성·제출, Connector 호출, Fill·Position Sync,
DB DDL·DML, 외부 API와 AWS 실행은 수행하지 않는다.

## 1. 문서 사용 기준

| 항목 | 값 |
|---|---|
| 대상 | `port_strategy_execution` Root와 `docs`의 주요 파일 |
| 기준 | 현재 파일 구조와 소스의 정적 확인 |
| 주요 관점 | 책임, 입력, 출력, DB 영향, 외부 영향, 변경 위험 |
| 제외 | Cache, Build 산출물, IDE 임시 파일 |
| 실행 | 문서 작업 중 Python Entry Point와 DB·Connector를 실행하지 않음 |
| 민감정보 | 실제 값과 일부 문자열도 기록하지 않음 |
| 갱신 시점 | 파일·책임·입출력·상태·DB·Wrapper 변경 시 |
| 현재 구조 | `README.md` |
| 작업 규칙 | `AGENTS.md` |
| 변경 이력 | `CHANGELOG.md` |

## 2. 서비스 책임 지도

```text
Daily BUY Signal
Daily Position SELL Decision
Backtest Trade Result
Connector Account · Balance · Position
                    │
                    ▼
       Builder · Sizing · Repository
                    │
                    ▼
        Execution Plan · Order
                    │
              승인·실행 경계
                    │
                    ▼
        MarketConnector Request
                    │
                    ▼
      Connector Request · Fill
                    │
                    ▼
          Fill · Position Sync
```

| 계층 | Execution 책임 |
|---|---|
| 입력 조회 | Signal·Decision·Backtest·Connector 상태 조회 |
| 후보 변환 | 원천 데이터를 Execution Order Payload로 변환 |
| 수량 계산 | BUY Sizing과 SELL 수량 제한 |
| Plan | 실행 후보 묶음과 Summary 관리 |
| Order | BUY·SELL 후보와 처리 상태 관리 |
| 주문 연계 | 승인된 Order를 Connector Helper에 전달 |
| Fill Sync | Connector Fill을 Execution 상태에 반영 |
| Position Sync | 체결을 전략 Position에 반영 |
| Intraday | OPEN Position 점검과 Stop Sell 후보 생성 |

## 3. Root 문서

### `AGENTS.md`

| 항목 | 값 |
|---|---|
| 책임 | Execution 전용 작업·안전·데이터 계약 정의 |
| 주요 내용 | Plan·Order·Fill·Position·중복 제출·Transaction 규칙 |
| 사용 시점 | 모든 Execution 코드·문서 작업 시작 전 |
| 변경 영향 | Kiro 작업 범위와 검증 기준 전체 |
| 주의 | README 현재 상태나 CHANGELOG 과거 이력을 대신하지 않음 |
| 갱신 조건 | 작업 범위, 계약, 위험, 문서 체계가 바뀔 때 |

### `README.md`

| 항목 | 값 |
|---|---|
| 책임 | 현재 서비스 구조와 운영 AS-IS 설명 |
| 주요 내용 | 책임 경계, Daily Step, Intraday, 데이터 계약, 설정 |
| 사용 시점 | 서비스 이해와 운영 흐름 확인 |
| 변경 영향 | 신규 작업자의 구조 이해 |
| 주의 | 과거 변경 이력을 장문으로 누적하지 않음 |
| 갱신 조건 | 현재 구조·입출력·운영 위치·사용 방법이 바뀔 때 |

### `CHANGELOG.md`

| 항목 | 값 |
|---|---|
| 책임 | 날짜별 주요 변경 사실 보존 |
| 주요 내용 | 문서·코드·DB·운영 변경과 실행 여부 |
| 사용 시점 | 변경 배경과 당시 사실 확인 |
| 변경 영향 | 추적성과 회귀 분석 |
| 주의 | 현재 상태 설명을 반복하지 않음 |
| 갱신 조건 | 의미 있는 코드·설정·문서 기준이 바뀔 때 |

### `docs/source-file-catalog.md`

| 항목 | 값 |
|---|---|
| 책임 | 파일별 책임·입출력·영향 지도 |
| 주요 내용 | Entrypoint, Builder, Repository, Sync, Wrapper |
| 사용 시점 | 수정 대상과 연관 파일 확인 |
| 변경 영향 | 영향 범위 누락 방지 |
| 주의 | 모든 사소한 파일을 무조건 나열하지 않음 |
| 갱신 조건 | 파일 추가·삭제·이름·책임·호출 관계 변경 시 |

## 4. 설정과 DB 공통 계층

### `db_config.py`

| 항목 | 값 |
|---|---|
| 책임 | PostgreSQL 연결 설정 구성 |
| 입력 | `INTEREST_DB_*` 환경변수와 관련 호환 설정 |
| 출력 | `psycopg2` 연결용 설정 |
| DB 영향 | 연결 자체는 없거나 호출 경로에 따라 연결 가능 |
| 주요 계약 | DB Name, User, Password 필수 조건, Search Path |
| 변경 위험 | 잘못된 DB·Schema 연결, Credential 노출 |
| 확인 대상 | Search Path 순서; `PORTFOLIO_DB_NAME`은 현재 코드 미사용 |
| 실행 | Import Side Effect 확인 전 실행하지 않음 |

### `execution_config.py`

| 항목 | 값 |
|---|---|
| 책임 | Execution 공통 환경 설정 제공 |
| 입력 | 계좌·Broker·환경·전략·Sizing 환경변수 |
| 출력 | Entry Point와 Builder가 사용할 설정 값 |
| DB 영향 | 직접 DB Write 없음 |
| 외부 영향 | Environment와 Account가 주문 대상에 영향 |
| 주요 계약 | Execution Mode, Strategy Name·Version, 주문 한도 |
| 변경 위험 | 실제 주문 환경·계좌·규모 변경 |
| 확인 대상 | 기본값, Required 여부, Validation 방식 |

### `execution_db.py`

| 항목 | 값 |
|---|---|
| 책임 | DB Connection과 Query Helper 제공 |
| 입력 | DB 설정, SQL, Parameter |
| 출력 | Row, Row List, Execute 결과 |
| DB 영향 | Read·Write 모두 가능 |
| 주요 함수 | `get_conn`, `fetch_one`, `fetch_all`, `execute_one` 계열 |
| 변경 위험 | Commit 경계, Cursor 반환, 예외 처리 변화 |
| 확인 대상 | Helper 내부 Commit 여부와 Dict Row 정책 |
| 실행 | 승인 없이 호출하지 않음 |

### `execution_repository.py`

| 항목 | 값 |
|---|---|
| 책임 | Execution DB Read·Write 집중 지점 |
| 입력 | Plan·Order·Position·Decision·Check Payload |
| 출력 | DB Row, ID, Summary, Update 결과 |
| Write 대상 | Plan, Order, Position, Decision 연결, Intraday Check |
| Read 대상 | Connector Request·Fill·Balance·Position Snapshot |
| 후보 조회 | Daily BUY 후보 조회 순서 제공 |
| 현금 배분 | Plan 단위 누적 현금 배분에 필요한 Position·Price·Open Order 조회 |
| Terminal 조회 | CANCELED Order와 Terminal Chain 관련 Read 책임 |
| 주요 계약 | Unique Key, Upsert, Status, Connector Request 연결 |
| 변경 위험 | 중복 주문, 부분 반영, Position 불일치 |
| 확인 대상 | 실제 수정된 함수와 SQL, Join Cardinality, Commit·Rollback 범위 |
| 실행 | 모든 호출을 DB 영향 가능 경로로 취급 |

## 5. Container와 Dependency

### `Dockerfile`

| 항목 | 값 |
|---|---|
| 책임 | Git SHA 기반 Execution Container Image 정의 |
| 입력 | Build Context, Requirements, Runtime Source |
| 출력 | ECS 또는 Local Container Image |
| Runtime 범위 | Root Runtime Source와 `requirements.txt` |
| 제외 | `.dockerignore` 기준으로 `.devops` Build Script와 Token·Secret 미포함 |
| 기본 CMD | `python daily_auto_buy_execute_run.py` (`--execute` 없음) |
| 변경 위험 | 잘못된 Source Copy, Dependency 누락, CMD 변경 |
| 확인 대상 | Base Image, Workdir, Copy 경로, 기본 CMD |
| 민감정보 | Image URI·Digest·Registry 값 기록 금지 |

### CI와 DevOps 자산

| 파일 | 책임 |
|---|---|
| `.github/workflows/execution-codebuild.yml` | main Push·`workflow_dispatch` Trigger, OIDC CodeBuild 시작·대기, main Push 시 Release control-plane 호출 |
| `.devops/codebuild/buildspec.yml` | Compile·pytest·Ruff·Docker Build·Container Source Compile·Container Import/File Smoke, Build-only 계약, 선택적 ECR Push |
| `.devops/scripts/container-smoke.py` | Runtime 파일·Import 계약, 금지 경로와 계좌 placeholder 환경변수 검증 |
| `.devops/scripts/deploy-execution.sh` | Release control-plane Promotion Script |
| `.dockerignore` | Token·`.devops`·`tests`·`docs`를 Image에서 제외 |
| `.gitignore` | `access_token.txt`와 로컬 산출물 Git 제외 |
| `pytest.ini` | `tests` 대상 테스트 설정 |
| `tests/` | 취소·다중 후보 순차 현금 배분·MARKET BUY 110% Reserve·체인·Container 계약 테스트 |

책임 분리는 아래와 같다.

- CodeBuild는 Build·Test·Container Smoke·ECR Artifact 생성 책임만 가지며 ECS·Step Functions 운영을 변경하지 않는다.
- GitHub Workflow Release control-plane은 검증된 Artifact로 ECS Task Definition 등록과 State Machine Definition 참조 변경을 수행할 수 있다.
- Release control-plane은 State Machine execution과 `ecs:RunTask`를 수행하지 않는다.
- Release control-plane은 Business 주문과 DB Write를 수행하지 않는다.

### `.devops/scripts/deploy-execution.sh`

| 항목 | 값 |
|---|---|
| 책임 | main Push 후속 운영 Promotion을 수행하는 Release control-plane Script |
| 기준선 탐색 | 운영 State Machine Definition에서 Execution Task Definition 기준선 동적 확인 |
| Artifact resolve | Source SHA 기준 ECR Image Digest 확인 |
| 신규 Revision | 운영 Task Definition Clone 후 검증된 Image Digest만 교체해 등록 |
| Backup | 변경 전 State Machine Definition Backup |
| Activation Scope | 대상 State Machine과 Execution State 참조 검증 |
| Promotion | 관련 State Machine의 Execution 참조 전환 |
| Stale Guard | 기준선 변경 시 Promotion 차단 |
| Rollback | 실패 시 Backup Definition으로 자동 복구 |
| After-check | Promotion 후 참조 정합성 검증 |
| 실행 경계 | State Machine execution·`ecs:RunTask`·주문·DB Write 없음 |
| 민감정보 | ARN·Resource ID·Revision 번호는 문서에 기록하지 않음 |

### `requirements.txt`

| 항목 | 값 |
|---|---|
| 책임 | Python Runtime Dependency 선언 |
| 주요 의존성 | `psycopg2-binary` 등 |
| 출력 | Image Build 시 설치 Package |
| 변경 위험 | Runtime 호환성, 취약점, Image 크기 |
| 확인 대상 | 실제 Import와 목록 정합성 |
| 주의 | 외부 경로 Import Module이 Package 목록에 없을 수 있음 |

### `create_execution_docker_files.py`

| 항목 | 값 |
|---|---|
| 책임 | Dockerfile과 Requirements 생성 Helper |
| 입력 | 스크립트 내부 Template과 대상 경로 |
| 출력 | `Dockerfile`, `requirements.txt` 파일 Write |
| 운영 위치 | 개발 보조 |
| DB 영향 | 없음 |
| 파일 영향 | 기존 Container 파일 덮어쓰기 가능 |
| 변경 위험 | 수동 수정 손실과 오래된 Template 재생성 |
| 실행 | 승인과 Diff 확인 없이 실행하지 않음 |

## 6. Daily BUY 후보 생성

### `daily_buy_execution_run.py`

| 항목 | 값 |
|---|---|
| 책임 | Daily BUY Execution 후보 생성 Entrypoint |
| AWS 위치 | Paper Daily Step 8 후보 |
| 입력 | 최신 Daily Run, BUY Signal, Account·Balance·Position |
| 처리 | Plan 조회·생성, Signal 변환, Sizing, Order Upsert |
| 출력 | `strategy_execution_plan`, `strategy_execution_order` |
| 외부 주문 | 이 단계에서 Broker 주문 완료를 의미하지 않음 |
| 주요 위험 | 잘못된 Source Run, 중복 후보, 빈 후보 오판 |
| 확인 대상 | Latest Run 선택, Business Date, Plan Summary |
| 실행 | DB Write 가능하므로 승인 없이 실행하지 않음 |

### `execution_daily_signal_builder.py`

| 항목 | 값 |
|---|---|
| 책임 | Daily BUY Signal을 Order Payload로 변환 |
| 입력 | Signal, Current Holding, Latest Price, Sizing 결과 |
| 출력 | Order 구조와 Validation Result·Order Snapshot |
| 누적 현금 | 후보 순서를 유지하며 Plan 내 잔여 현금을 순차 배분 |
| READY 차감 | READY 후보의 Reserve 포함 필요 현금을 잔여 현금에서 차감 |
| BLOCKED · 0주 | 잔여 현금을 차감하지 않음 |
| 재사용 금지 | 후속 후보에 최초 가용현금을 그대로 재사용하지 않음 |
| DB 영향 | 직접 없음, Repository 조회 Helper 사용 |
| 주요 계약 | Source ID, Ticker, Side, Quantity, Reason |
| 변경 위험 | Signal 추적성 손실, 수량·가격·현금 배분 의미 변화 |
| 확인 대상 | 필수 Field, Validation, 후보 순서, 잔여 현금 경계 |
| 주의 | Builder 결과가 실제 주문 성공을 의미하지 않음 |

### `execution_buy_sizing.py`

| 항목 | 값 |
|---|---|
| 책임 | 단일 BUY 후보의 주문 가능 수량과 필요 현금 계산 |
| 입력 | Target Amount, Available Cash, Current Holding, Latest Price |
| 출력 | order_qty, estimated_order_amount, required_cash_amount, sizing_detail |
| MARKET Reserve | 수량·필요 현금에 110%(`MARKET_BUY_CASH_RESERVE_RATIO`) 적용 |
| 유효 가격 | 수량 계산 시 `latest_price`의 110% 사용 |
| 금액 구분 | 예상 주문금액과 Reserve 포함 필요 현금 분리 |
| DB 영향 | 직접 없음 |
| 책임 경계 | 단일 BUY 후보 계산만 담당, Broker 주문가능금액은 보장하지 않음 |
| 다중 후보 | 여러 후보 누적 현금 배분은 Signal Builder 흐름에서 확인 |
| 변경 위험 | 실제 주문 수량·현금 경계·Decimal·0주·최소 금액 처리 |
| 확인 대상 | 절사, 0 Price, Cash 부족, 기존 보유 |

## 7. Daily SELL 후보 생성

### `daily_sell_execution_run.py`

| 항목 | 값 |
|---|---|
| 책임 | Daily Position SELL Decision을 Order 후보로 변환 |
| AWS 위치 | Paper Daily Step 9 후보 |
| 입력 | 최신 Position Decision Run과 SELL Row |
| 처리 | Order 생성·Upsert와 Decision 연결 |
| 출력 | `strategy_execution_order`, Decision의 Order ID |
| 주요 위험 | Decision 중복 소비, 잘못된 Position 연결 |
| 확인 대상 | Run 선택, Source ID, Position State, Quantity |
| 재실행 | 기존 연결과 기존 Order를 먼저 확인 |
| 실행 | DB Write 가능하므로 승인 없이 실행하지 않음 |

### `execution_daily_position_sell_builder.py`

| 항목 | 값 |
|---|---|
| 책임 | SELL Decision을 Order Payload로 변환 |
| 입력 | Decision Row와 Position 연결 정보 |
| 출력 | Daily Position SELL Order 구조 |
| DB 영향 | 직접 없음 또는 호출 구조에 따라 확인 |
| 주요 계약 | Decision ID, Position State ID, Side, Quantity |
| 변경 위험 | 다른 Position 매도와 수량 오류 |
| 확인 대상 | 전량·부분 매도 의미와 Source Payload 보존 |

## 8. Auto Execute

### `daily_auto_sell_execute_run.py`

| 항목 | 값 |
|---|---|
| 책임 | READY SELL Order를 Connector SELL 경로에 전달 |
| AWS 위치 | Paper Daily Step 10 후보 |
| 입력 | Daily·Intraday SELL Order, 최신 Sellable Quantity |
| 처리 | 실행 대상 검증, Connector Helper 호출, 상태 갱신 |
| 출력 | Connector Request 연결과 Execution 상태 |
| Position 영향 | `SELL_ORDERED` 등 상태 갱신 가능 |
| 외부 영향 | Broker 주문 요청으로 이어질 수 있음 |
| 주요 위험 | 중복 제출, 수량 초과, 외부 성공 후 DB 실패 |
| 확인 대상 | 기존 Request, Mode, Sellable Quantity, Retry |
| 실행 | 자동 주문 경로이므로 실행 금지 |

### `daily_auto_buy_execute_run.py`

| 항목 | 값 |
|---|---|
| 책임 | READY BUY Order를 Connector BUY 경로에 전달 |
| AWS 위치 | Paper Daily Step 11 후보 |
| 입력 | Daily BUY Execution Order |
| 처리 | 실행 모드와 주문 값 확인 후 Connector Helper 호출 |
| 출력 | Connector Request 연결과 Execution 상태 |
| 외부 영향 | Broker 주문 요청으로 이어질 수 있음 |
| 주요 위험 | 중복 제출, 잘못된 계좌·환경·수량 |
| 확인 대상 | 기존 Request, Mode, Account, Retry |
| 실행 | 자동 주문 경로이므로 실행 금지 |

### `execution_execute_order.py`

| 항목 | 값 |
|---|---|
| 책임 | 단일 Execution Order 실행 Entrypoint |
| 입력 | Order ID, Execution Mode, 실행 옵션 |
| 처리 | Validation, Mode 저장, Connector BUY·SELL 호출 가능 |
| 출력 | Order 상태와 Connector Request 연결 |
| 주요 모드 | `DRY_RUN`, `MANUAL_TEST`, `PAPER_STRATEGY`, `LIVE_STRATEGY` |
| DB 영향 | `--execute` 없이도 Write 가능성 확인 필요 |
| 외부 영향 | 옵션에 따라 실제 주문 요청 |
| 주요 위험 | Live 오실행, 중복 제출, Commit 불일치 |
| 확인 대상 | `--execute`, Live Confirm, Environment 검증 |
| 실행 | 명시 승인 없이는 모든 모드 실행 금지 |

## 9. SELL Fill과 Position 반영

### `execution_sync_sell_fill.py`

| 항목 | 값 |
|---|---|
| 책임 | SELL Connector Fill을 Execution과 Position에 반영 |
| AWS 위치 | Paper Daily Step 14 후보 |
| 입력 | SELL Order, Connector Request, Fill |
| 출력 | Order 체결 상태와 Position 잔여 수량 |
| Write 대상 | `strategy_execution_order`, `strategy_position_state` |
| 주요 계약 | 누적 Fill, 부분 체결, Remaining Quantity |
| 상태 영향 | 전량 체결 시 완료·종료 후보 |
| 주요 위험 | Fill 중복 집계, Position 중복 차감 |
| 확인 대상 | Fill Key, 누적 수량, CLOSED 조건, Transaction |
| 실행 | Position 수량 변경 가능하므로 실행 금지 |

SELL Fill이 한 건 있다는 이유만으로 Order 전체를 `FILLED`로 단정하지 않는다.
실제 요청 수량과 누적 체결 수량을 비교한다.

## 10. BUY Fill과 Position 반영

### `execution_sync_buy_fill.py`

| 항목 | 값 |
|---|---|
| 책임 | BUY Connector Fill과 취소 상태를 Execution Order Terminal로 반영 |
| AWS 위치 | Paper Daily Step 15 후보 |
| 입력 | BUY Order, Connector Request, Fill |
| 출력 | FILLED·CANCELED Terminal 상태와 Summary |
| Write 대상 | `strategy_execution_order` |
| Terminal 분류 | FILLED와 CANCELED를 별도 Terminal로 처리 |
| 취소 처리 | 정상 CANCELED + 체결 0건은 정상 종료 |
| 실패 집계 | 정상 CANCELED는 실패 건수에서 제외 |
| Summary | filled·canceled·terminal·failed 분리 |
| 주요 위험 | 취소 상태 오판정, 부분 체결 조기 완료, Transaction Rollback 범위 |
| 확인 대상 | Request 최종 상태, Fill Scope, Quantity, Average Price |
| 실행 | DB Write 가능하므로 실행 금지 |

### `execution_sync_buy_position.py`

| 항목 | 값 |
|---|---|
| 책임 | FILLED BUY Fill을 전략 Position에 반영 |
| AWS 위치 | Paper Daily Step 16 후보 |
| 입력 | FILLED BUY Order와 기존 OPEN Position |
| 대상 | FILLED BUY만 대상, CANCELED는 제외 |
| 출력 | 신규 Position 또는 추가 매수 병합 |
| Write 대상 | `strategy_position_state`, Order Sync 기록 |
| 추적 | `source_buy_execution_order_id`, Connector Request·Fill 추적 |
| 성공 판정 | 대상 0건 성공과 실제 생성 성공을 분리 |
| 주요 계약 | 동일 Fill 재처리 방지와 평균 단가 계산 |
| 주요 위험 | 중복 Position, 수량 이중 반영 |
| 확인 대상 | Existing OPEN 선택, Merge 공식, 재실행 중복 방지 |
| 실행 | Position 생성·변경 가능하므로 실행 금지 |

### `execution_validate_order_chain.py`

| 항목 | 값 |
|---|---|
| 책임 | Execution Order → Connector Request → Fill → Position 체인 Validator |
| AWS 위치 | Paper Daily Step 16 이후 P0 검증 후보 |
| 입력 | Plan·Order·Connector Request·Fill·Position |
| 출력 | 대상 수·오류 수와 non-zero exit |
| 유형 | Read-only, DB Insert·Update·Delete 없음 |
| FILLED BUY | Connector Fill과 Position 추적 필수 |
| CANCELED BUY | 유효한 취소 체인이면 Fill·Position 없이 정상 Terminal |
| CLI 옵션 | `--run-date`, `--plan-id`, `--allow-no-target` |
| 주요 위험 | 상태 오판정과 False Positive |
| 확인 대상 | Request 최종 상태, Fill 합계, Position 추적 |
| 실행 | Read-only이나 DB 연결이므로 승인 없이 실행하지 않음 |

## 11. Position Context와 SELL 평가

### `execution_position_loader.py`

| 항목 | 값 |
|---|---|
| 책임 | 전략 OPEN Position Context 구성 |
| 입력 | `strategy_position_state`, Connector Position Snapshot |
| 출력 | SELL Evaluator용 Position Context |
| DB 영향 | Read |
| 주요 계약 | Strategy Quantity와 Broker Quantity를 구분 |
| 주요 위험 | 최신 Snapshot 오선택, Join 중복 |
| 확인 대상 | Latest 기준, Account·Ticker Join, Missing Snapshot |
| 실행 | 파일 하단 `main()`과 Side Effect를 확인하고 실행 금지 |

### `execution_sell_evaluator.py`

| 항목 | 값 |
|---|---|
| 책임 | Position의 SELL·HOLD 평가 Payload 생성 |
| 입력 | Position Context, Stock Feature, Market Feature |
| 출력 | Decision, Reason, Metric Payload |
| DB 영향 | 직접 없음 또는 호출 구조 확인 |
| 주요 계약 | 평가 기준일과 Feature Date |
| 변경 위험 | 실제 매도 후보 결과 변화 |
| 확인 대상 | Hard Stop, Missing Feature, Look-ahead 가능성 |
| 주의 | StrategyDecision의 Daily Position 판단과 같은 구현으로 단정하지 않음 |

### `execution_sell_builder.py`

| 항목 | 값 |
|---|---|
| 책임 | OPEN Position 평가를 POSITION_SELL Order로 변환 |
| 입력 | Position과 Sell Evaluation |
| 출력 | `strategy_execution_order`와 Position 평가 결과 |
| DB 영향 | Update·Upsert 가능 |
| 주요 계약 | Position ID, Source Type, Quantity, Reason |
| 주요 위험 | 중복 SELL 후보와 Position 상태 오염 |
| 확인 대상 | Existing Order, Evaluation Update, Transaction |
| 실행 | DB Write 가능하므로 승인 없이 실행하지 않음 |

## 12. Intraday Monitor

### `daily_intraday_position_monitor_run.py`

| 항목 | 값 |
|---|---|
| 책임 | 장중 OPEN Position 점검과 Stop Sell 후보 생성 |
| 운영 위치 | 장중 10분 Intraday Evaluate 후보 |
| 입력 | OPEN Position, Connector Position, Quote, Feature |
| 처리 | Current Price 조회, Stop 조건 평가, Check 저장 |
| 기본 출력 | `strategy_intraday_position_check` |
| 선택 출력 | `INTRADAY_STOP_SELL` Execution Order |
| 외부 영향 | Connector Quote API 호출 가능 |
| 주요 옵션 | `--create-order` 등 실제 코드에서 확인 |
| 주요 위험 | 반복 Order 생성, Quote 오류, 거래 시간 오판 |
| 확인 대상 | 정상 Check 저장, Hard Stop, Approval 경계 |
| 실행 | 외부 API와 DB Write 가능하므로 실행 금지 |

점검 결과 저장과 Stop Sell Order 생성은 별도 영향이다.
점검 성공을 주문 생성 성공 또는 Broker 주문 제출로 표현하지 않는다.

## 13. Backtest 기반 Execution 후보

### `backtest_execution_run.py`

| 항목 | 값 |
|---|---|
| 책임 | Backtest 결과를 Execution 후보로 변환 |
| 입력 | Backtest Run·Daily·Trade Log |
| 출력 | Execution Plan·Order 후보 |
| DB 영향 | Plan·Order Write 가능 |
| 주요 계약 | Research Source Run과 거래 결과 추적 |
| 주요 위험 | Backtest 결과를 Daily 운영 후보로 혼합 |
| 확인 대상 | Run 선택, Trade Side, Quantity, Business Date |
| 실행 | DB Write 가능하므로 승인 없이 실행하지 않음 |

### `execution_builder.py`

| 항목 | 값 |
|---|---|
| 책임 | Backtest Trade를 Order Payload로 변환 |
| 입력 | BUY·SELL Trade와 Position·Price Context |
| 출력 | Backtest Source Execution Order 구조 |
| DB 영향 | 직접 없음 또는 호출 구조 확인 |
| 주요 계약 | Research Source 추적과 Daily 경로 분리 |
| 변경 위험 | Backtest 후보 의미와 수량 변화 |
| 확인 대상 | Validation, Price, Source Type, Position Link |

### `execution_build_candidates.py`

| 항목 | 값 |
|---|---|
| 책임 | 독립형 또는 과거 후보 생성 경로 |
| 입력 | 자체 DB Query와 설정 |
| 출력 | Execution 후보 Upsert 가능 |
| DB 영향 | Read·Write |
| 현재 분류 | Legacy 가능성이 있는 보존 대상 |
| 주요 위험 | 공통 Repository와 다른 Key·Status 사용 가능 |
| 확인 대상 | Import 참조, Wrapper, 실제 운영 호출 |
| 삭제 기준 | 미사용을 정적으로 입증하기 전 삭제 금지 |
| 실행 | 독립 DB Write 가능성이 있어 실행 금지 |

파일명과 구조만으로 완전한 Legacy 또는 삭제 대상으로 단정하지 않는다.

## 14. 데이터 계약

### 14.1 주요 입력

| 입력 | 소비 파일 |
|---|---|
| Daily BUY Signal | Daily BUY Entrypoint와 Signal Builder |
| Daily Position SELL Decision | Daily SELL Entrypoint와 SELL Builder |
| Backtest Run·Trade | Backtest Entrypoint와 Builder |
| Connector Account | BUY·SELL 실행 Context |
| Connector Balance | BUY Sizing |
| Connector Position | SELL 수량과 Position Context |
| Connector Request | Fill Sync |
| Connector Fill | BUY·SELL Fill Sync |
| Stock·Market Feature | SELL Evaluator와 Intraday |

### 14.2 주요 출력

| 출력 | 생성·갱신 파일 |
|---|---|
| `strategy_execution_plan` | Daily BUY·Backtest·Repository |
| `strategy_execution_order` | Daily BUY·SELL·Intraday·Backtest·Auto Execute·Sync |
| `strategy_position_state` | SELL Fill·BUY Position·Auto SELL |
| `strategy_daily_position_decision.execution_order_id` | Daily SELL |
| `strategy_intraday_position_check` | Intraday Monitor |

실제 Table·Column·Schema는 코드에서 확인한다.

## 15. Plan 계약

| 항목 | 변경 시 확인 |
|---|---|
| Source Type | Daily Signal·Position Decision·Backtest 구분 |
| Source Run | 올바른 Run ID와 추적성 |
| Business Date | 실행 대상 거래일 |
| Environment | Paper·Live 분리 |
| Strategy | Name과 Version |
| Status | 생성 중·완료·실패 의미 |
| Summary | 후보·Skip·Error 집계 |
| No Target | 정상 빈 후보와 입력 누락 구분 |
| 재실행 | 기존 Plan 재사용 또는 신규 생성 정책 |

Plan 생성 성공을 하위 Order 전체 성공으로 해석하지 않는다.

## 16. Order 계약

| 항목 | 변경 시 확인 |
|---|---|
| Plan ID | 상위 Plan 연결 |
| Source ID | 원천 Signal·Decision·Trade 추적 |
| Ticker·Side | 주문 대상과 방향 |
| Quantity | 요청 수량과 체결 수량 구분 |
| Execution Mode | Dry Run·Manual·Paper·Live |
| Connector Request | 외부 주문 요청 연결 |
| Status | 후보·요청·체결·실패 상태 |
| Payload | Source와 Sync 근거 보존 |
| Unique Key | 중복 후보와 제출 방지 |
| Retry | 외부 성공·DB 실패 복구 |

실제 상태 문자열은 구현에서 확인한다.
개념 상태를 코드의 정확한 값으로 단정하지 않는다.

## 17. Fill 계약

| 항목 | 변경 시 확인 |
|---|---|
| Request Scope | 올바른 Connector Request 선택 |
| Fill Scope | 주문번호·Ticker·Side·거래일 |
| Duplicate | 동일 Fill 재집계 방지 |
| Quantity | 누적 체결과 요청 수량 비교 |
| Average Price | 수량 가중 평균 |
| Partial Fill | 일부 체결의 상태와 재실행 |
| Zero Fill | 정상 미체결과 연결 누락 구분 |
| Transaction | Order와 Position 반영 원자성 |

## 18. Position 계약

| 항목 | 변경 시 확인 |
|---|---|
| 신규 BUY | OPEN Position 생성 |
| 추가 BUY | 기존 OPEN 병합 기준 |
| 부분 SELL | 체결 수량만 차감 |
| 전량 SELL | 잔여 수량 0과 CLOSED 전이 |
| 재실행 | 동일 Fill의 중복 반영 금지 |
| Strategy Quantity | Execution 기준 잔여 수량 |
| Broker Quantity | Connector Snapshot 기준 |
| SELL_ORDERED | 주문 중 상태와 재선택 정책 |

전략 Position과 Broker Position은 서로 다른 데이터 계약이다.

## 19. DB 영향 지도

### 19.1 Write 가능성이 큰 테이블

| 테이블 | 주요 파일 |
|---|---|
| `strategy_execution_plan` | Daily BUY, Backtest, Repository |
| `strategy_execution_order` | 후보 생성, Auto Execute, Fill Sync, Intraday |
| `strategy_position_state` | Auto SELL, SELL Fill, BUY Position |
| `strategy_daily_position_decision` | Daily SELL 연결 |
| `strategy_intraday_position_check` | Intraday Monitor |

### 19.2 Connector Read 대상

| 테이블 | 주요 파일 |
|---|---|
| `connector_order_request` | Fill Sync와 Order 연결 |
| `connector_fill` | BUY·SELL Fill 집계 |
| `connector_account` | 주문 계좌 Context |
| `connector_balance_snapshot` | BUY Sizing |
| `connector_position_snapshot` | SELL 수량과 Position Context |

### 19.3 DB 변경 전 확인

| 항목 | 확인 내용 |
|---|---|
| Schema | Search Path와 동일명 Table |
| Unique Key | 실제 Constraint와 Upsert Target |
| Join | 1:N 확대와 중복 Row |
| Latest | Date·Timestamp·ID 기준 |
| Transaction | Repository 내부와 호출자 책임 |
| Commit | 외부 주문 호출 전후 위치 |
| Rollback | 부분 저장과 재시도 |
| DDL | Import·Entrypoint 중 자동 실행 여부 |

## 20. 외부 의존 관계

### MarketConnector

| 항목 | 값 |
|---|---|
| Execution 사용 | BUY·SELL Helper, Quote, Connector Table |
| 책임 경계 | Broker·KIS API와 Token은 MarketConnector 책임 |
| 주문가능금액 | Broker 실제 주문가능금액 계산은 MarketConnector 책임 |
| 수정 범위 | Execution 요청만으로 외부 저장소 수정 금지 |
| 주요 위험 | 외부 성공 후 Execution DB 연결 실패 |
| 확인 대상 | Import 경로, 함수 Signature, 반환 계약 |

### StrategyDecision

| 항목 | 값 |
|---|---|
| Execution 사용 | Daily BUY Signal과 Position SELL Decision |
| 책임 경계 | BUY·SELL 판단 알고리즘은 Decision 책임 |
| 주요 위험 | Decision Run·Row 오선택 |
| 확인 대상 | Source ID, Business Date, Status |

### StrategyResearch

| 항목 | 값 |
|---|---|
| Execution 사용 | Backtest Run·Daily·Trade 결과 |
| 책임 경계 | Backtest 계산과 Report는 Research 책임 |
| 주요 위험 | Research 결과의 Daily 운영 승격 |
| 확인 대상 | Source Type과 Run 추적 |

### Preprocessor·Crawler

| 항목 | 값 |
|---|---|
| Execution 사용 | Feature와 거래일 관련 입력 |
| 책임 경계 | Raw 수집과 Feature 생성은 외부 책임 |
| 주요 위험 | 오래된 Feature·Look-ahead·휴장일 오판 |
| 확인 대상 | Feature Date와 Business Date |

## 21. AWS와 운영 Wrapper

현재 Root에서 확인되는 Execution Entrypoint는 ECS RunTask 또는
Container Command Override 대상으로 사용될 수 있다.

| 운영 구간 | Entry Point |
|---|---|
| Daily BUY 후보 | `daily_buy_execution_run.py` |
| Daily SELL 후보 | `daily_sell_execution_run.py` |
| Auto SELL | `daily_auto_sell_execute_run.py --execute` |
| Auto BUY | `daily_auto_buy_execute_run.py --execute` |
| SELL Fill | `execution_sync_sell_fill.py` |
| BUY Fill | `execution_sync_buy_fill.py` |
| BUY Position | `execution_sync_buy_position.py` |
| Intraday | `daily_intraday_position_monitor_run.py` |

실제 Cluster, Task Definition, Image URI, Command Override와 Log Group은
외부 운영 정의에서 확인한다.

운영 식별자는 아래처럼 Placeholder만 사용한다.

```text
<EXECUTION_ECS_CLUSTER>
<EXECUTION_TASK_DEFINITION_ARN>
<EXECUTION_ECR_IMAGE_URI>
<EXECUTION_LOG_GROUP>
<COMMAND_ID>
```

State Machine Definition 자체는 이 Repository의 Source 파일이 아니다.
Catalog는 이를 파일 항목으로 만들지 않고 운영 참조로만 설명한다.
현재 Execution 관련 State의 Task Definition 참조 변경과 Rollback은
`.devops/scripts/deploy-execution.sh` Release control-plane이 main Push에서 자동 수행한다.
이 자동 Promotion은 Definition 참조만 변경하며 State Machine 실행·주문·DB Write를 수행하지 않는다.

## 22. 민감정보 후보

### `access_token.txt`

| 항목 | 값 |
|---|---|
| 분류 | 민감정보 후보 로컬 파일 |
| 가능 내용 | Connector·API 인증 관련 값 |
| 읽기 | 작업 목적이라도 원문을 읽거나 인용하지 않음 |
| 문서화 | 파일 존재와 위험만 기록 |
| Git | 추적 여부와 Ignore 정책을 별도 확인 |
| 처리 | 삭제·이동·수정은 사용자 승인 필요 |

아래 값도 문서에 원문으로 기록하지 않는다.

- Password
- Token과 API Key
- Account Number
- Webhook URL
- DB Host와 Credential
- Broker Order Number
- Connector Request ID
- ARN·Image URI·Subnet·Security Group
- 일회성 Command ID와 실행 로그

## 23. 현재 문서에서 제외한 항목

날짜별 `docs/worklog/*.md`는 현재 파일 구조와 Catalog 목록에서 제외한다.

과거 Worklog 생성 사실은 `CHANGELOG.md`에만 보존한다.
새 Worklog 파일을 만들지 않는다.

아래 산출물도 Catalog 대상에서 제외한다.

- `__pycache__/`
- `.pytest_cache/`
- `.gradle/`
- `target/`
- `build/`
- IDE 임시 파일
- Coverage와 Compile 산출물
- 일회성 SQL·JSON·Log Dump
- Secret 또는 Token 원문 파일 내용

## 24. 정리 후보 판단 기준

파일을 정리하거나 삭제하기 전 아래 항목을 확인한다.

| 항목 | 확인 내용 |
|---|---|
| Import | 다른 Python 파일의 직접·동적 Import |
| Entrypoint | `__main__`과 CLI 실행 가능성 |
| Wrapper | PowerShell·Shell·Batch·Lambda 호출 |
| Container | Docker CMD와 Command Override |
| AWS | ECS·Step Functions·SSM 참조 |
| 외부 MS | 다른 저장소에서 Path·Module 참조 |
| DB | 독립 Table·Status·Output 사용 |
| 문서 | 운영 절차와 Runbook 참조 |
| Git | 최근 변경과 사용자 미커밋 작업 |

미사용 근거가 충분하지 않으면 삭제하지 않고 보존 또는 정리 후보로만 표시한다.

## 25. 파일 변경 영향 지도

| 변경 대상 | 함께 확인할 파일 |
|---|---|
| BUY Signal 입력 | Daily BUY Entrypoint, Signal Builder, Repository |
| BUY Sizing | Signal Builder, Repository, Config, Tests, README |
| BUY Fill CANCELED 처리 | BUY Fill Sync, Order Chain Validator, BUY Position Sync |
| Order Chain Validator | Repository, Connector Request·Fill, Position State |
| SELL Decision 입력 | Daily SELL Entrypoint, SELL Builder, Repository |
| Auto Execute | Auto BUY·SELL, Execute Order, Connector 계약 |
| Order Status | Repository, Auto Execute, Fill Sync |
| Connector Request 연결 | Execute Order, Auto Execute, Fill Sync |
| BUY Fill | BUY Fill Sync, BUY Position Sync |
| SELL Fill | SELL Fill Sync, Position State |
| Position State | Loader, SELL Builder, Intraday, Sync |
| Intraday | Loader, Evaluator, Builder, Monitor |
| Backtest 후보 | Backtest Entrypoint, Builder, Research 계약 |
| DB Config | DB Helper, Repository, Container 설정 |
| Docker·CI | Workflow, Buildspec, Dockerfile, Ignore 파일, Tests |
| State Machine Revision 변경 | Execution Task Definition 참조와 Rollback Definition |
| 파일 추가·삭제 | README 구조와 Source Catalog |
| 주요 계약 변경 | AGENTS, README, CHANGELOG |

## 26. Catalog 갱신 조건

아래 변경이 있으면 이 문서를 같은 작업에서 확인한다.

- 파일 추가·삭제·이름 변경
- Entrypoint와 CLI 옵션 변경
- 파일 책임 또는 호출 순서 변경
- 입력·출력 Payload 변경
- Plan·Order·Fill·Position 상태 변경
- Table·Column·Schema·Unique Key 변경
- Upsert와 Transaction 정책 변경
- Connector Helper와 반환 계약 변경
- BUY Sizing과 SELL 수량 정책 변경
- Partial Fill과 Retry 처리 변경
- Intraday Check 또는 Stop Order 정책 변경
- Backtest 후보의 운영 사용 여부 변경
- Docker·Requirements·ECS Command 변경
- 민감정보 파일과 설정 방식 변경
- 문서 구조와 Worklog 정책 변경

단순 오탈자 수정이나 설명 문장 정리만으로
관련 없는 모든 파일을 기계적으로 갱신하지 않는다.

## 27. 관련 문서

- [AGENTS.md](../AGENTS.md)
- [README.md](../README.md)
- [CHANGELOG.md](../CHANGELOG.md)
