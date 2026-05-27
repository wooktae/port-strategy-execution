# CHANGELOG

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
