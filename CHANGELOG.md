# CHANGELOG

`port_strategy_execution`의 주요 변경 이력을 기록한다.

현재 구조와 사용 방법은 `README.md`, 작업 규칙은 `AGENTS.md`,
파일별 책임과 영향은 `docs/source-file-catalog.md`를 기준으로 확인한다.

## 2026-08-03

### Execution 오류 개선

| 항목 | 변경 내용 |
|---|---|
| CANCELED BUY | 정상 취소를 별도 Terminal 상태로 처리 |
| Step 15 집계 | 취소 주문을 실패 집계에서 제외 |
| Step 15 Summary | filled·canceled·terminal·failed 분리 |
| P0 Validator | 정상 취소 체인을 오류로 판정하지 않음 |
| FILLED BUY | Position 추적 필수 기준 유지 |

### BUY 금액 계산 개선

| 항목 | 변경 내용 |
|---|---|
| 누적 배분 | 여러 BUY 후보를 Plan 내 누적 가용현금 기준으로 계산 |
| 처리 순서 | 확정된 후보 순서 유지 |
| READY 차감 | READY 주문 예상 금액만 잔여 현금에서 차감 |
| BLOCKED | 현금을 차감하지 않음 |
| 초과 방지 | 후속 BUY의 잔여 현금 초과를 축소 또는 차단 |
| 책임 분리 | 단일 종목 Sizing과 Plan 단위 배분 책임 구분 |

### 테스트와 Source 검증

| 항목 | 결과 |
|---|---|
| 단위 테스트 | 20건 성공 |
| Ruff | 성공 |
| Python Compile | 성공 |
| Runtime Token | Git·Docker Image 제외 확인 |
| Source SHA | 변경 Source와 Remote SHA 일치 |
| Working Tree | Clean |

### CI와 Artifact

| 항목 | 결과 |
|---|---|
| Repository | Execution GitHub Repository와 main Branch 구성 |
| 인증 | GitHub Actions와 OIDC Role 구성 |
| CodeBuild | 연계 시작·대기 성공 |
| Image | Git SHA 기반 Docker Image 생성 |
| ECR | Tag와 Digest 확인 |
| 실행 경계 | Build-only에서 ECS·DB·주문 미실행 |

### Candidate 검증

| 항목 | 결과 |
|---|---|
| Task Definition | Candidate Revision 등록 |
| Compile-only | 성공 |
| Source·Image | 핵심 Source SHA-256 일치 |
| Runtime Import | 성공 |
| Auto BUY Dry-run | 성공, READY 대상 0건 |
| 중복 주문 | 활성 중복 0건 |
| Connector 체인 | 체결 BUY 1건·취소 BUY 1건 정상 Terminal |
| Candidate Step 15 | 성공 |
| Candidate Step 16 | Position 생성 성공 |
| Candidate P0 Validator | 대상 2건·오류 0건 성공 |
| 주문 영향 | 신규 Connector Request와 주문 제출 없음 |

### 운영 승격과 복구

| 항목 | 결과 |
|---|---|
| 승격 | Execution 관련 State 참조 5개를 새 Revision으로 승격 |
| 백업 | 원본 State Machine Definition 백업 |
| Rollback | 이전 Revision으로 복원 성공 |
| 재승격 | 새 Revision 재승격 성공 |
| 최종 상태 | State Machine ACTIVE, Execution은 새 Revision 참조 |
| 실행 영향 | 승격·Rollback 과정 Workflow·ECS·DB·주문 미실행 |

### 변경 파일

| 항목 | 값 |
|---|---|
| Python | `execution_sync_buy_fill.py`, `execution_sync_buy_position.py` |
| Python | `execution_validate_order_chain.py`, `execution_daily_signal_builder.py` |
| Python | `execution_buy_sizing.py`, `execution_repository.py` |
| 테스트 | `tests/`의 취소·현금 배분·체인 검증 테스트 |
| CI | `.github/workflows/execution-codebuild.yml`, `.devops/codebuild/buildspec.yml` |
| CI | `.devops/scripts/container-smoke.py` |
| Container | `Dockerfile`, `.dockerignore`, `.gitignore`, `pytest.ini`, `requirements-dev.txt` |
| 문서 | `README.md`, `AGENTS.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` |

실제 반영 파일은 Git Diff 기준이며, 추정 파일명은 기록하지 않는다.

### 작업 경계

| 항목 | 결과 |
|---|---|
| 신규 운영 주문 | 제출하지 않음 |
| Candidate 검증 | 기존 주문 데이터 기준 Step 15·Step 16·Validator 수행 |
| Position row | Candidate Step 16 검증 과정에서 1건 생성 |
| State Machine | 승격·Rollback·재승격으로 참조 변경 |
| DB DDL | 수행하지 않음 |
| Secret·Token 원문 | 조회·기록하지 않음 |

## 2026-07-23

### Execution 문서 기준 재정비

| 항목 | 변경 내용 |
|---|---|
| 변경 범위 | `AGENTS.md`, `README.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` 문서 기준 재정비 |
| 작업 성격 | 현재 코드와 운영 구조를 정적으로 대조한 문서 개선 |
| 문서 구조 | `docs/database.md`와 `docs/worklog/*.md` 삭제 반영 |
| 기능 변경 | 없음 |
| 코드 변경 | 없음 |
| DB 변경 | 없음 |
| 주문 실행 | 없음 |
| AWS 실행 | 없음 |
| 외부 API 호출 | 없음 |

### AGENTS.md

| 항목 | 변경 내용 |
|---|---|
| 문서 가독성 | 최우선 규칙으로 짧은 문장, 2열 표와 긴 셀 분리 기준 추가 |
| 규칙 우선순위 | 사용자 최신 지시, Workspace 공통 규칙과 Execution 전용 규칙 관계 정리 |
| 책임 경계 | Decision·Research·MarketConnector·View·Scheduler와 역할 분리 |
| 작업 범위 | `port_strategy_execution` 내부 직접 수정 원칙 명확화 |
| 실행 제한 | 주문·DB·Connector·Fill·Position·Intraday 실행 금지 기준 강화 |
| Plan 계약 | Source, Business Date, Run ID, Summary, 재실행과 빈 후보 기준 추가 |
| Order 계약 | Source 추적, 상태 전이, Connector Request 연결 기준 추가 |
| 중복 방지 | 후보·주문 제출·Fill·Position 중복 위험과 Idempotency 확인 기준 추가 |
| BUY Sizing | 현금·현재 보유·가격·최소 주문·반올림 변경 위험 정리 |
| SELL 수량 | 전략 잔여 수량과 Broker 매도 가능 수량의 차이 처리 기준 추가 |
| Fill Sync | 부분 체결·누적 체결·평균가·중복 체결·재시도 기준 추가 |
| Position Sync | 신규 Position·추가 매수·부분 매도·CLOSED 전이 기준 추가 |
| Transaction | Order·Fill·Position 변경의 Commit·Rollback 경계 확인 기준 추가 |
| Intraday | 점검 결과 저장과 Stop Sell Order 생성 영향을 분리 |
| Backtest 후보 | Daily 운영 후보와 별도 경로로 취급하도록 정리 |
| 삭제 안전 | Import·Entrypoint·Wrapper·ECS·다른 MS 참조 확인 전 삭제 금지 |
| 문서 체계 | README·CHANGELOG·Catalog 문서 역할 분리 |
| Worklog | 날짜별 Worklog 신규 생성 금지 |
| Catalog 갱신 | 파일 책임·데이터 흐름·DB·Connector·상태 전이 변경 시 갱신 기준 추가 |
| 완료 보고 | 수행 검증과 미수행 검증을 구분하도록 정리 |

### README.md

| 항목 | 변경 내용 |
|---|---|
| 서비스 요약 | 주요 입력·출력·운영 위치·실행 형태를 첫 섹션에 정리 |
| 책임 경계 | 전략 판단과 Broker 구현 사이 Execution 계층으로 재정의 |
| 전체 흐름 | Signal·Decision → Plan → Order → Connector → Fill → Position 구조 추가 |
| 성공 기준 | 후보 생성·주문 요청·Broker 접수·체결·Position 반영을 각각 분리 |
| Daily Step | Step 8~17을 Execution 관점의 역할 표로 재구성 |
| BUY 경로 | Signal Builder·Sizing·Repository 책임 분리 |
| SELL 경로 | Position Decision 변환과 Order 연결 책임 분리 |
| Auto Execute | READY 조회·Mode 확인·Connector 호출·상태 반영 경계 정리 |
| MarketConnector | Step 12~13과 Step 17을 외부 책임으로 명확화 |
| SELL Fill | 부분 체결·중복 Fill·잔여 수량·CLOSED 전이 확인 기준 추가 |
| BUY Fill | 누적 체결·가중 평균가·부분 체결 상태 기준 추가 |
| BUY Position | 신규 생성·추가 매수·재실행 중복 방지 기준 추가 |
| Intraday | 점검 저장과 `INTRADAY_STOP_SELL` 후보 생성을 별도 영향으로 구분 |
| Plan 계약 | Source·거래일·Run·환경·Summary·No Target 기준 추가 |
| Order 계약 | 식별 기준·개념 상태 흐름·Connector 연결 기준 추가 |
| Idempotency | 후보·제출·Sync·Position 중복 위험을 별도 섹션으로 추가 |
| BUY Sizing | 목표 금액·현금·보유액·가격·최소 금액·절사 기준 정리 |
| SELL 수량 | 전략 수량·Broker 수량·요청 수량·체결 수량 분리 |
| Fill Sync | Request Scope·Fill Scope·Aggregation·Retry·Transaction 기준 추가 |
| Position State | BUY·SELL 체결 반영과 재실행 안전 기준 추가 |
| Backtest | Daily 운영 후보와 분리된 후보 생성 경로로 정리 |
| 파일 구조 | 현재 문서 기준으로 Root와 `docs` 구조 단순화 |
| Worklog | 날짜별 `docs/worklog`를 현재 구조에서 제외하고 신규 생성 금지 반영 |
| DB | Execution Write 대상과 Connector Read 대상을 분리 |
| Search Path | Domain Schema 순서와 동일명 Table 위험 정리 |
| 설정 | 환경변수의 실제 사용 여부와 Fallback을 코드 확인 대상으로 명시 |
| Execution Mode | Dry Run도 DB Write 가능성이 있음을 명시 |
| Container | ECS 실행 대상과 운영 식별자 Placeholder 정책 정리 |
| 확인 항목 | 상태 문자열·Unique Key·부분 체결·Transaction 등 미확정 항목 분리 |

### CHANGELOG.md

| 항목 | 변경 내용 |
|---|---|
| 구조 | 장문 Bullet 중심에서 날짜별 2열 변경 요약 중심으로 재구성 |
| 최신 이력 | 2026-07-23 문서 기준 재정비 내역 추가 |
| 변경 경계 | 문서 변경·코드 변경·DB 변경·실행 여부를 명확히 분리 |
| 과거 이력 | 2026-05-26~2026-07-01 실제 변경 사실 보존 |
| Worklog 이력 | 과거 생성 사실은 유지하고 현재 신규 생성 금지 정책과 구분 |
| 민감정보 | 실제 운영 식별자와 Credential 원문 미기록 원칙 유지 |

### docs/source-file-catalog.md

| 항목 | 변경 내용 |
|---|---|
| 표 구조 | 기존 5열 장문 표를 파일별 2열 책임 구조로 재구성 |
| 책임 분리 | Entrypoint·Builder·Repository·Sync·Container 책임 분리 |
| 데이터 계약 | Plan·Order·Fill·Position 계약 표 추가 |
| DB 영향 | DB Write 대상과 Connector Read 대상 분리 |
| 영향 지도 | 파일 변경 영향 지도 추가 |
| Worklog | 현재 목록에서 Worklog 제거 |
| 갱신 기준 | 파일·DB·상태·Connector·Docker 변경 시 Catalog 갱신 조건 추가 |

### 문서 구조 정리

| 대상 | 처리 |
|---|---|
| `docs/database.md` | 파일 삭제 반영, 4개 문서에서 참조·링크 제거 |
| `docs/worklog/*.md` | 파일 4건 삭제, 현재 구조에서 제외 |
| 문서 체계 | 5문서에서 4문서로 정리 |
| 과거 이력 | Worklog와 Database 문서의 과거 사실은 과거 섹션에 보존 |

### 주요 계약 보강

| 계약 | 보강 내용 |
|---|---|
| Plan과 Order | Plan 생성 성공과 모든 Order 생성 성공을 동일하게 보지 않음 |
| Order와 Connector | Execution DB 상태와 Broker 주문 상태를 동일하게 보지 않음 |
| Connector와 Fill | 주문 접수와 체결 완료를 별도 상태로 구분 |
| Fill과 Position | Fill 반영 성공과 Position 반영 성공을 별도 검증 |
| 부분 체결 | 일부 Fill을 전량 `FILLED`로 조기 처리하지 않도록 기준 추가 |
| 중복 제출 | 기존 Connector Request와 Broker 접수 여부를 재시도 전에 확인 |
| 중복 Sync | 동일 Fill의 누적 집계와 Position 재반영 방지 |
| SELL Position | 체결 수량만 차감하고 잔여 수량 0일 때 종료 여부 확인 |
| BUY Position | 동일 Fill의 중복 생성과 추가 매수 병합 기준 확인 |
| No Target | 정상 빈 후보와 입력 누락·조회 실패를 구분 |
| Transaction | 외부 주문 성공 후 내부 DB 실패 시 복구 경계 확인 |

### 문서 정비 원칙

| 항목 | 기준 |
|---|---|
| 현재 상태 | README에 기록 |
| 작업 규칙 | AGENTS에 기록 |
| 변경 이력 | CHANGELOG에 기록 |
| 파일 책임 | Source File Catalog에 기록 |
| DB 상세 | README Search Path와 Catalog DB 영향에 기록 |
| Worklog | 신규 생성하지 않음 |
| 반복 설명 | 상세 문서 링크로 분리 |
| 불확실한 사실 | 코드·DB·Wrapper 확인 전 단정하지 않음 |

### 안전과 검증

| 항목 | 결과 |
|---|---|
| Python Entry Point 실행 | 수행하지 않음 |
| Execution Order 생성 | 수행하지 않음 |
| Connector BUY·SELL 호출 | 수행하지 않음 |
| Broker·KIS 주문 제출 | 수행하지 않음 |
| Fill Sync | 수행하지 않음 |
| Position Sync | 수행하지 않음 |
| Intraday Monitor | 수행하지 않음 |
| DB DDL·DML | 수행하지 않음 |
| AWS CLI·SDK | 수행하지 않음 |
| ECS·SSM·Step Functions | 수행하지 않음 |
| 민감정보 조회·기록 | 수행하지 않음 |
| 문서 파일 정적 검토 | 수행 |

## 2026-07-01

### AWS Paper 운영 문서 보강

| 항목 | 변경 내용 |
|---|---|
| README | AWS Paper Daily Step 8~17의 Execution 역할 추가 |
| Intraday | 장중 10분 Evaluate 흐름 설명 추가 |
| Container | ECS RunTask 대상 Entry Point 정리 |
| Placeholder | Cluster·Task Definition·Image·Log 식별자 기록 기준 추가 |
| 책임 경계 | Execution 직접 책임과 외부 MS 책임 구분 |
| 파일 구조 | Docker·Requirements·생성 Helper와 Docs 항목 반영 |
| Source Catalog | Container 관련 파일과 실행 위험 설명 보강 |
| Database | Execution Search Path와 Schema 책임 범위 명시 |

### 당시 추가 문서

| 항목 | 변경 내용 |
|---|---|
| Worklog | `docs/worklog/2026-07-01.md` 생성 |
| 현재 정책 | 과거 생성 사실은 보존하되 신규 Worklog는 만들지 않음 |

### 당시 작업 경계

| 항목 | 결과 |
|---|---|
| 기능 변경 | 없음 |
| Python 코드 변경 | 없음 |
| SQL 의미 변경 | 없음 |
| 주문 흐름 변경 | 없음 |
| Execution Mode 변경 | 없음 |
| 주문·체결·Position 실행 | 수행하지 않음 |
| DB DDL·DML | 수행하지 않음 |
| 외부 API·Crawler | 수행하지 않음 |
| AWS 운영 식별자 원문 기록 | 하지 않음 |

### 참고 범위

당시 참고 문서에서는 Execution 책임에 필요한 사실만 선별했다.

| 제외 영역 | 담당 |
|---|---|
| View 화면 구현 | port-view |
| KIS API 내부 구현 | MarketConnector |
| Crawler·Preprocessor 내부 구현 | 해당 데이터 MS |
| BUY·SELL 판단 알고리즘 | StrategyDecision |
| Backtest 내부 구현 | StrategyResearch |
| 전체 State Machine | Scheduler·Step Functions |
| EventBridge 전체 라인업 | 공통 운영 문서 |
| Lambda 내부 구현 | 해당 AWS 구성 |
| 일회성 DB Row·Command ID | 운영 로그 |

## 2026-05-28

### 문서와 주석 정리

| 항목 | 변경 내용 |
|---|---|
| Source Catalog | `docs/source-file-catalog.md` 최초 추가 |
| Module Docstring | 주요 Python 파일 역할과 영향 설명 추가 |
| Function Docstring | 주문·Fill·Position·Intraday 주요 함수 설명 추가 |
| README | 파일 Catalog와 주석 정리 기준 추가 |
| Intraday | 2026-05-27 정상 점검 결과 저장 정책 문서 반영 |
| Worklog | `docs/worklog/2026-05-28.md` 생성 |

### 당시 작업 경계

| 항목 | 결과 |
|---|---|
| 기능 변경 | 없음 |
| 실행 로직 변경 | 없음 |
| SQL 의미 변경 | 없음 |
| 주문·Connector 실행 | 수행하지 않음 |
| Fill·Position Sync | 수행하지 않음 |
| Intraday Monitor | 수행하지 않음 |
| DB DDL·DML | 수행하지 않음 |

## 2026-05-27

### DB 설정과 Schema 전환

| 항목 | 변경 내용 |
|---|---|
| DB 환경변수 | `INTEREST_DB_*` 기반으로 외부화 |
| DB Password | `INTEREST_DB_PASSWORD`를 기본값 없는 필수 값으로 정리 |
| Legacy Script | 하드코딩 설정을 `db_config.get_db_config()` 사용으로 변경 |
| 기본 DB | 로컬 PostgreSQL DB Name을 `portfolio`로 정리 |
| Schema 구조 | 단일 DB + Schema-per-domain 구조 문서화 |
| Search Path | 기존 SQL이 Connection Search Path 기반으로 동작하도록 정리 |

이 날짜의 항목은 실제 설정·코드 변경 이력이다.
현재 코드와 일치하는지는 최신 소스에서 다시 확인한다.

## 2026-05-26

### 초기 문서와 파일 정리

| 항목 | 변경 내용 |
|---|---|
| AGENTS | 초기 `AGENTS.md` 추가 |
| README | 초기 `README.md` 추가 |
| Worklog | `docs/worklog/2026-05-26.md` 생성 |
| Test Script | 로컬 테스트·스크래치 후보 파일 제거 |
| Python Cache | `__pycache__/` 제거 |

### 당시 제거 파일

| 파일 | 분류 |
|---|---|
| `test_connector_buy_1_share.py` | 로컬 주문 테스트 |
| `test_repository_sell_functions.py` | Repository SELL 테스트 |
| `test_sell_evaluator.py` | Sell Evaluator 테스트 |
| `__pycache__/` | Python Cache 산출물 |

### 당시 작업 기준

| 항목 | 기준 |
|---|---|
| 문서 근거 | 당시 파일 구조와 소스의 읽기 전용 확인 |
| 주문 실행 | 수행하지 않음 |
| Connector 호출 | 수행하지 않음 |
| Fill·Position Sync | 수행하지 않음 |
| Intraday Monitor | 수행하지 않음 |
| DB DDL·DML | 수행하지 않음 |
| 외부 API·Crawler | 수행하지 않음 |
| 민감정보 | 실제 값을 기록하지 않음 |
