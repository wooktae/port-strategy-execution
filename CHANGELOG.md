# CHANGELOG

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
