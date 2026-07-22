# CHANGELOG

## 2026-07-01

### Changed

- `README.md`에 AWS Paper Daily Step 8~17 Execution 역할과 장중 10분 intraday evaluate 흐름 설명을 추가했다.
- `README.md`에 ECS RunTask/컨테이너 실행 대상 entrypoint 목록과 placeholder 정책을 정리했다.
- `README.md` 상단에 Execution 책임 경계(직접 책임/직접 책임 아님)를 명시했다.
- `README.md` 파일 구조에 `Dockerfile`, `requirements.txt`, `create_execution_docker_files.py`, docs 하위 항목을 반영했다.
- `docs/source-file-catalog.md`에 Docker/의존성 관련 파일 3종(`Dockerfile`, `requirements.txt`, `create_execution_docker_files.py`) 항목을 추가하고, 각 실행 계열의 AWS 운영 문맥을 실행 위험 관점에서 보완했다.
- `docs/database.md`에서 Execution DB search_path와 schema 책임 설명을 유지하되 다른 MS schema 상세로 확장하지 않는 원칙을 명시했다.

### Added

- `docs/worklog/2026-07-01.md`를 추가해 PORT-STRATEGY-EXECUTION 문서 최신화 작업을 계획/완료 형식으로 기록했다.

### Notes

- 기능 변경 없음. Python 코드, SQL 의미, 주문/connector 호출 흐름, execution mode 정책은 변경하지 않았다.
- 실제 execution/order 생성, 자동 매수/매도, connector/broker/KIS 주문 API 호출, 체결 조회, fill sync, position sync, intraday monitor 실행, DB DDL/DML, 외부 API 호출, 크롤링, 주문 제출은 수행하지 않았다.
- 참고 자료인 `port-view/.kiro/` 하위 문서는 PORT-STRATEGY-EXECUTION 범위 안 사실만 선별 반영했다. port-view 화면 구현, MarketConnector KIS API 상세, Crawler/Preprocessor 내부 구현, StrategyDecision 판단 알고리즘, StrategyResearch 백테스트, Step Functions state machine 전체 step, EventBridge Scheduler 라인업 세부 운영 로그, Lambda 내부 구현, DB after-check 세부 row, command id, 일회성 검증 로그, 다른 MS 변경 이력은 반영하지 않았다.
- 실제 cluster/task definition ARN/image URI/subnet/security group/command id/broker order number/connector order id/DB host/계좌번호/token/webhook URL 등 민감정보와 운영 식별자 원문은 기록하지 않았다. 필요한 경우 `[REDACTED]` 또는 `<EXECUTION_ECS_TASK>` 계열 placeholder를 사용했다.
- `.kiro` 하위 spec/requirements/design/tasks 파일은 이번 작업 범위에서 생성하지 않았다. 이 저장소 안에 사전 생성된 `.kiro` 파일은 확인되지 않았다.

## 2026-05-28

### Added

- `docs/source-file-catalog.md`를 추가해 전체 주요 파일의 역할, 내용, 운영 주의사항을 한글로 정리했다.
- Python 파일별 module docstring과 운영상 중요한 함수 설명 주석을 추가했다.
- `docs/worklog/2026-05-28.md`에 미커밋 변경 확인과 문서화/주석 정리 작업 기록을 추가했다.

### Changed

- `README.md`에 파일 카탈로그와 주석 정리 기준을 추가했다.
- 2026-05-27 미커밋 변경사항인 intraday monitor 정상 점검 결과 저장 정책을 문서에 반영했다.

### Notes

- 기능 변경 없음. 실행 로직, SQL 의미, 주문/connector 호출 흐름은 변경하지 않았다.
- 실제 주문 실행, connector 호출, 체결 조회, position sync, intraday monitor 실행, DB DDL/DML은 수행하지 않았다.

## 2026-05-27

### Changed

- DB 접속 설정을 `INTEREST_DB_*` 환경변수 기반으로 외부화했다.
- `INTEREST_DB_PASSWORD`는 기본값 없이 필수 환경변수로 처리하도록 정리했다.
- legacy 후보 생성 스크립트의 하드코딩 DB 접속 설정을 공통 `db_config.get_db_config()` 사용으로 변경했다.
- 로컬 PostgreSQL 기본 DB name 설명을 `portfolio`로 정리했다.
- AWS Migration 준비 관점의 단일 DB `portfolio` + schema-per-domain 구조와 execution 모듈 search_path를 문서화했다.
- schema-per-domain 전환 후에도 기존 SQL은 connection search_path 기반으로 동작한다는 내용을 추가했다.

## 2026-05-26

### Added

- 초기 프로젝트 문서 초안을 추가했다.
  - `AGENTS.md`
  - `README.md`
  - `docs/worklog/2026-05-26.md`

### Removed

- 1차 unused/legacy 파일 분석 결과에 따라 로컬 테스트/스크래치 파일과 Python 캐시 산출물을 정리했다.
  - `test_connector_buy_1_share.py`
  - `test_repository_sell_functions.py`
  - `test_sell_evaluator.py`
  - `__pycache__/`

### Notes

- 문서는 현재 파일 구조와 소스를 읽기 전용으로 확인한 결과를 기준으로 작성했다.
- 실제 execution/order 생성, 자동 매수/매도, 체결 조회, fill sync, position sync, intraday monitor, DB DDL/DML, 외부 API 호출, 크롤링, 주문 제출은 수행하지 않았다.
- 민감정보 값은 문서에 기록하지 않으며, 필요한 경우 `[REDACTED]`로 표기한다.
