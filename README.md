# port_strategy_execution

`port_strategy_execution`은 전략 판단 결과를 실제 실행 계층의 계획과 주문 후보로 변환하고,
주문 요청·체결·전략 포지션 상태를 연결하는 Python 마이크로서비스다.

이 문서는 현재 저장소의 구조와 운영 AS-IS를 설명한다.
실제 주문 생성·제출, 체결 동기화, 포지션 갱신, DB 쓰기, 외부 API 호출과 AWS 실행 절차는
승인 없이 수행하지 않는다.

## 1. 서비스 요약

| 항목 | 값 |
|---|---|
| 서비스 | `port_strategy_execution` |
| 주 책임 | Execution Plan·Order 생성과 주문·체결·전략 Position 연결 |
| 주요 입력 | Daily BUY signal, Daily Position SELL decision, connector 계좌·잔고·포지션·체결 |
| 주요 출력 | `strategy_execution_plan`, `strategy_execution_order`, `strategy_position_state` |
| 운영 위치 | AWS Paper Daily Step 8~11, 14~16과 장중 Intraday Evaluate |
| 실행 형태 | 루트 실행형 Python entrypoint 중심 |
| 주문 API | MarketConnector helper 경유 |
| 기본 정책 | 후보 생성과 승인 경계를 분리하고 중복 주문을 방지 |
| 문서 기준 | 현재 코드·파일 구조의 정적 확인 결과 |

## 2. 주요 책임

| 영역 | 책임 |
|---|---|
| Daily BUY Execution | Daily BUY signal을 BUY execution order 후보로 변환 |
| Daily SELL Execution | Daily Position SELL decision을 SELL execution order 후보로 변환 |
| Execution Plan | 실행 단위 Plan 생성과 요약 상태 관리 |
| Execution Order | BUY·SELL 주문 후보 생성, 조회와 상태 갱신 |
| Auto Execute | 승인된 READY Order를 connector 호출 경로에 전달 |
| Fill Sync | connector 주문 요청과 체결을 Execution 상태에 반영 |
| Position Sync | BUY fill 기반 OPEN Position 생성과 SELL fill 기반 수량 차감 |
| Intraday Monitor | OPEN Position 점검과 Stop Sell 후보 생성 |
| Backtest Candidate | Backtest 결과를 별도 Execution 후보로 변환하는 경로 유지 |

## 3. 책임 경계

Execution은 전략 판단과 Broker 구현 사이의 실행 계층이다.

| 영역 | 담당 |
|---|---|
| 원천 데이터 수집 | Crawler |
| Raw 전처리와 Feature 생성 | Preprocessor |
| Daily BUY Signal 판단 | StrategyDecision |
| Daily Position HOLD·SELL·SKIP 판단 | StrategyDecision |
| Backtest와 Research Report | StrategyResearch |
| Plan·Order·Fill·전략 Position 연결 | StrategyExecution |
| Broker·KIS API와 Token 관리 | MarketConnector |
| 승인 UI와 화면 표시 | port-view |
| 전체 Daily Orchestration | Scheduler와 Step Functions |

Execution은 아래 책임을 직접 소유하지 않는다.

- BUY·SELL 판단 알고리즘 자체
- MarketConnector 내부 주문 API 구현
- 원천 데이터 수집과 Feature 생성
- View 렌더링과 승인 화면
- 전체 Step Functions 정의
- EventBridge Scheduler 운영
- Backtest 성과 분석과 Report 생성

다른 MS는 Execution에 필요한 입력·출력 계약 수준으로만 설명한다.

## 4. 전체 데이터 흐름

```text
Daily BUY Signal
Daily Position SELL Decision
Backtest Trade Result
Connector Account · Balance · Position
                    │
                    ▼
             Execution Builder
                    │
                    ▼
        strategy_execution_plan
        strategy_execution_order
                    │
            승인·실행 경계
                    │
                    ▼
        MarketConnector Order Request
                    │
                    ▼
 connector_order_request · connector_fill
                    │
                    ▼
            Execution Fill Sync
                    │
                    ▼
 strategy_execution_order · strategy_position_state
```

각 단계는 별도 성공 조건을 가진다.

| 구분 | 성공 판단 |
|---|---|
| 후보 생성 | Plan과 Order가 의도한 source 기준으로 생성됨 |
| 주문 요청 | connector request 연결과 요청 상태가 기록됨 |
| 주문 접수 | Broker 응답과 connector 상태가 확인됨 |
| 체결 반영 | 누적 체결 수량과 평균가가 Execution에 반영됨 |
| Position 반영 | BUY·SELL 체결 결과가 전략 Position에 정확히 반영됨 |

한 단계의 성공을 다음 단계의 성공으로 간주하지 않는다.

## 5. AWS Paper Daily 역할

Execution은 전체 Daily Batch를 소유하지 않는다.
아래는 Execution 관점의 Step 역할만 정리한 것이다.

| Step | Execution 관점 |
|---|---|
| Step 8 | Daily BUY execution order 후보 생성 |
| Step 9 | Daily SELL execution order 후보 생성 |
| Step 10 | READY SELL auto execute 경로 |
| Step 11 | READY BUY auto execute 경로 |
| Step 12~13 | MarketConnector 주문 제출과 주문 조회 |
| Step 14 | SELL fill sync |
| Step 15 | BUY fill sync |
| Step 16 | BUY position sync |
| Step 17 | MarketConnector balance refresh |

### 5.1 Step 8 · Daily BUY Execution

`daily_buy_execution_run.py`가 최신 Daily Run과 BUY Signal을 읽어
BUY Execution Plan과 Order 후보를 생성할 수 있다.

주요 연결 파일은 아래와 같다.

| 파일 | 역할 |
|---|---|
| `daily_buy_execution_run.py` | BUY 후보 생성 entrypoint |
| `execution_daily_signal_builder.py` | Signal을 Order payload로 변환 |
| `execution_buy_sizing.py` | 주문 수량 계산 |
| `execution_repository.py` | Plan·Order 저장과 요약 갱신 |

이 단계는 후보 생성 단계다.
Broker 주문 제출 성공을 의미하지 않는다.

### 5.2 Step 9 · Daily SELL Execution

`daily_sell_execution_run.py`가 최신 Daily Position Decision Run의
SELL Decision을 읽어 SELL Execution Order 후보를 만들 수 있다.

| 파일 | 역할 |
|---|---|
| `daily_sell_execution_run.py` | SELL 후보 생성 entrypoint |
| `execution_daily_position_sell_builder.py` | Decision을 Order payload로 변환 |
| `execution_repository.py` | Order 저장과 Decision 연결 |

`strategy_daily_position_decision.execution_order_id` 연결이 발생할 수 있다.
재실행 시 기존 연결과 중복 Order 여부를 함께 확인해야 한다.

### 5.3 Step 10~11 · Auto Execute

| Step | Entry Point | 주요 영향 |
|---|---|---|
| Step 10 | `daily_auto_sell_execute_run.py --execute` | READY SELL 조회와 connector SELL 호출 |
| Step 11 | `daily_auto_buy_execute_run.py --execute` | READY BUY 조회와 connector BUY 호출 |

Auto Execute는 아래 경계를 가진다.

- READY Order 조회
- 실행 모드 확인
- 수량과 대상 계좌 확인
- connector helper 호출
- connector request 연결
- Execution 상태 갱신
- 실패 시 오류 상태 또는 재시도 판단

Connector helper를 호출하더라도 Broker 주문 API 구현 책임은 MarketConnector에 있다.

### 5.4 Step 12~13 · MarketConnector 구간

이 구간은 MarketConnector 책임이다.

Execution은 아래 데이터가 후속 Sync 입력으로 준비된다고 이해한다.

- `connector_order_request`
- `connector_fill`
- Broker 주문 상태
- 누적 체결 수량
- 평균 체결가

Execution 문서에서 MarketConnector 내부 Token·Endpoint·재시도 구현을 복제하지 않는다.

### 5.5 Step 14 · SELL Fill Sync

`execution_sync_sell_fill.py`는 SELL 주문의 connector request와 fill을 읽어
Execution Order와 전략 Position에 반영할 수 있다.

주요 확인 대상은 아래와 같다.

| 항목 | 확인 내용 |
|---|---|
| 누적 체결 수량 | 신규 fill만이 아니라 누적 기준인지 확인 |
| 부분 체결 | 일부 수량을 전량 체결로 처리하지 않는지 확인 |
| 중복 fill | 동일 fill 재처리 방지 기준 확인 |
| Remaining Quantity | 체결 수량만큼 정확히 차감되는지 확인 |
| Position Status | 잔여 수량 0일 때만 CLOSED 전이하는지 확인 |
| Order Status | 실제 완료 조건과 상태 문자열 확인 |

### 5.6 Step 15 · BUY Fill Sync

`execution_sync_buy_fill.py`는 BUY 주문의 체결 수량과 평균가를 집계해
Execution Order 상태에 반영할 수 있다.

| 항목 | 확인 내용 |
|---|---|
| Fill 집계 | 동일 체결 중복 반영 방지 |
| 부분 체결 | 요청 수량과 누적 체결 수량 분리 |
| 평균가 | 실제 fill 가중 평균 기준 확인 |
| 상태 전이 | 부분 체결과 전량 체결 상태 구분 |
| Connector 연결 | 올바른 request 기준으로 집계하는지 확인 |

### 5.7 Step 16 · BUY Position Sync

`execution_sync_buy_position.py`는 체결된 BUY Order를 전략 Position에 반영할 수 있다.

| 상황 | 확인 기준 |
|---|---|
| 신규 종목 | OPEN Position 신규 생성 |
| 기존 OPEN Position | 추가 매수 병합 정책 확인 |
| 재실행 | 동일 BUY fill의 중복 Position 생성 방지 |
| 평균 단가 | 기존 수량과 신규 체결의 병합 방식 확인 |
| Sync 완료 | Order payload 또는 상태 기록 기준 확인 |

### 5.8 Step 17 · Balance Refresh

Balance Refresh는 MarketConnector 책임 구간이다.

Execution은 이후 아래 Snapshot을 조회 입력으로 사용할 수 있다.

- `connector_balance_snapshot`
- `connector_position_snapshot`

Execution 자체가 Broker Balance Snapshot 생성 책임을 소유한다고 표현하지 않는다.

## 6. 장중 Intraday Evaluate

장중 OPEN Position 점검은 `daily_intraday_position_monitor_run.py` 중심으로 구성된다.

```text
strategy_position_state OPEN
        +
connector_position_snapshot
        │
        ▼
execution_position_loader.py
        │
        ▼
execution_sell_evaluator.py
        │
        ├─ HOLD·점검 결과
        │
        └─ Hard Stop 후보
                │
                ▼
strategy_intraday_position_check
strategy_execution_order
```

### 6.1 주요 파일

| 파일 | 역할 |
|---|---|
| `execution_position_loader.py` | 전략 Position과 connector Snapshot 결합 |
| `execution_sell_evaluator.py` | Position·Stock Feature·Market Feature 평가 |
| `execution_sell_builder.py` | POSITION_SELL Order 후보 생성 |
| `daily_intraday_position_monitor_run.py` | 점검 저장과 Stop Sell 후보 생성 |

### 6.2 점검 결과와 주문 후보

Intraday 점검 결과 저장과 주문 후보 생성은 별도 영향이다.

| 영향 | 의미 |
|---|---|
| 점검 저장 | `strategy_intraday_position_check` 기록 |
| Order 후보 | `INTRADAY_STOP_SELL` 또는 관련 SELL 후보 생성 |
| 실제 주문 | 별도 승인과 connector 실행 경계 필요 |

`--create-order` 같은 옵션은 DB 쓰기와 Order 생성으로 이어질 수 있다.
정적 문서 점검에서는 실행하지 않는다.

## 7. Execution Plan 계약

`strategy_execution_plan`은 하나의 실행 후보 생성 단위를 묶는 상위 개념이다.

Plan 관련 변경 시 아래 항목을 확인한다.

| 항목 | 확인 기준 |
|---|---|
| Source | Daily Signal, Position Decision 또는 Backtest 구분 |
| Business Date | 실제 대상 거래일 기준 |
| Source Run ID | 올바른 원천 Run과 연결 |
| Environment | Paper·Live 구분 |
| Strategy | Strategy Name과 Version |
| Summary | BUY·SELL·Skip·Error 집계 기준 |
| Status | 생성 중·완료·실패 상태 의미 |
| 재실행 | 동일 Source 기준 재사용 또는 신규 생성 정책 |
| 빈 후보 | 정상 No Target과 입력 누락을 구분 |

Plan이 존재한다는 사실만으로 모든 Order가 정상 생성되었다고 판단하지 않는다.

## 8. Execution Order 계약

`strategy_execution_order`는 실제 실행 가능한 BUY·SELL 후보와
주문 처리 상태를 연결하는 중심 테이블이다.

### 8.1 주요 식별 기준

| 항목 | 목적 |
|---|---|
| Plan ID | 상위 실행 단위 연결 |
| Source Type | Daily Signal·Position Decision·Backtest·Intraday 구분 |
| Source ID | 원천 row와 추적성 유지 |
| Ticker | 주문 대상 종목 |
| Side | BUY 또는 SELL |
| Requested Quantity | 주문 요청 수량 |
| Execution Mode | Dry Run·Manual·Paper·Live 경계 |
| Connector Request ID | MarketConnector 주문 요청 연결 |
| Status | 후보·요청·체결·실패 상태 표현 |

실제 컬럼명과 key는 코드와 DB 정의에서 확인한다.
문서 편의를 위해 존재하지 않는 컬럼을 추가하지 않는다.

### 8.2 상태 전이

상태 문자열과 전이 조건은 구현을 기준으로 확인한다.

개념 흐름은 아래와 같다.

```text
Candidate
  → Ready
  → Requested
  → Accepted or Working
  → Partially Filled
  → Filled
```

실패·취소·거절·No Target 상태는 별도 경로일 수 있다.

- 상태 이름을 관행만으로 확정하지 않는다.
- Connector 상태와 Execution 상태를 같은 값으로 단정하지 않는다.
- 부분 체결을 `FILLED`로 조기 전이하지 않는다.
- DB 업데이트 성공을 Broker 주문 성공으로 간주하지 않는다.

### 8.3 Idempotency와 중복 주문

재시도와 재실행에서 가장 먼저 확인할 위험이다.

| 위험 | 확인 기준 |
|---|---|
| 후보 중복 | 동일 Source·Ticker·Side의 중복 Order 생성 방지 |
| 제출 중복 | 기존 connector request 존재 여부 확인 |
| 외부 성공·DB 실패 | Broker 접수 후 로컬 연결 실패 복구 기준 |
| Sync 중복 | 동일 fill의 반복 집계 방지 |
| Position 중복 | 동일 BUY 체결의 반복 Position 반영 방지 |

중복 방지 key, unique constraint와 upsert conflict target은 실제 정의를 확인한다.

## 9. BUY Sizing 계약

`execution_buy_sizing.py`는 BUY Signal을 실제 주문 수량으로 변환하는 계산 계층이다.

| 입력 | 확인 내용 |
|---|---|
| Target Amount | 전략 목표 금액 |
| Available Cash | 사용 가능한 현금 |
| Current Holding | 현재 보유 수량과 평가액 |
| Latest Price | 주문 수량 계산 기준 가격 |
| Maximum Ratio | 최대 주문 금액 비율 |
| Minimum Amount | 최소 주문 금액 |
| Rounding | 정수 수량과 절사 기준 |

아래 상황을 명확히 구분한다.

- 계산 수량 0
- 최소 주문 금액 미달
- 사용 가능 현금 부족
- 이미 목표 보유 금액 충족
- 가격 누락 또는 0
- 현재 보유량과 connector Snapshot 불일치

Sizing 로직 변경은 실제 주문 금액에 직접 영향을 준다.

## 10. SELL 수량 계약

SELL 수량은 전략 Position과 Broker 보유 수량을 함께 고려할 수 있다.

| 기준 | 의미 |
|---|---|
| Strategy Remaining Quantity | 전략상 아직 보유한 수량 |
| Connector Sellable Quantity | Broker에서 실제 매도 가능한 수량 |
| Requested Quantity | 이번 Order에서 요청할 수량 |
| Filled Quantity | 실제 체결된 누적 수량 |

두 수량이 다를 때 임의로 한쪽을 정답으로 선택하지 않는다.

확인해야 할 상황은 아래와 같다.

- 전략 수량보다 Broker 수량이 적음
- Broker 수량이 0
- 미체결 SELL Order가 이미 존재
- 부분 매도 이후 재평가
- SELL_ORDERED 상태의 Position 재선택
- 동일 종목에 여러 OPEN Position 존재

## 11. Fill Sync 계약

Fill Sync는 connector 데이터를 Execution 상태로 복사하는 단순 작업이 아니다.

| 항목 | 확인 기준 |
|---|---|
| Request Scope | 올바른 connector request 선택 |
| Fill Scope | 주문번호·종목·Side·거래일 범위 |
| Aggregation | 누적 수량과 가중 평균가 |
| Duplicate | 동일 체결 식별자 중복 처리 |
| Partial Fill | 요청 수량보다 작은 체결 처리 |
| Retry | 재실행 결과가 동일해야 함 |
| Transaction | Order와 Position 변경의 원자성 |
| Error | 일부 반영 후 실패 복구 기준 |

체결 0건은 아래 두 상황으로 구분한다.

- 아직 미체결인 정상 상태
- connector request 또는 fill 연결 누락

## 12. Position State 계약

`strategy_position_state`는 전략 기준의 보유 상태다.
Broker Position Snapshot과 같은 개념이 아니다.

### 12.1 BUY Position 반영

| 상황 | 기대 확인 |
|---|---|
| 최초 BUY | OPEN Position 생성 |
| 추가 BUY | 기존 OPEN 병합 여부 확인 |
| 부분 체결 | 체결 수량만 반영 |
| 재실행 | 동일 체결 중복 반영 금지 |
| 평균 단가 | 기존 Position과 신규 Fill 병합 공식 확인 |

### 12.2 SELL Position 반영

| 상황 | 기대 확인 |
|---|---|
| 일부 SELL | `remaining_qty`만 차감 |
| 전량 SELL | 잔여 수량 0과 CLOSED 전이 |
| 미체결 | Position 수량 변경 금지 |
| 중복 Sync | 동일 fill 재차감 금지 |
| SELL_ORDERED | 주문 중 상태와 OPEN·CLOSED 관계 확인 |

Position 상태 변경은 Order와 Fill 근거를 추적할 수 있어야 한다.

## 13. Backtest 기반 후보

`backtest_execution_run.py`는 Research 결과를 Execution 후보로 변환할 수 있는 별도 경로다.

| 파일 | 역할 |
|---|---|
| `backtest_execution_run.py` | Backtest Run·Daily·Trade Log 기반 후보 생성 |
| `execution_builder.py` | Backtest BUY·SELL 결과를 Order payload로 변환 |
| `execution_build_candidates.py` | Legacy 또는 독립형 후보 생성 경로 |

Backtest 후보는 Daily 운영 Signal과 같은 입력으로 표현하지 않는다.

- Research 결과는 실제 투자 권고가 아니다.
- Backtest 후보를 Daily 자동 주문 대상으로 자동 승격하지 않는다.
- 실제 운영 사용 여부는 호출 경로와 Wrapper를 확인한다.
- Legacy 여부는 파일명만 보고 단정하지 않는다.

## 14. 주요 파일 구조

```text
.
├── AGENTS.md
├── CHANGELOG.md
├── Dockerfile
├── README.md
├── access_token.txt
├── backtest_execution_run.py
├── create_execution_docker_files.py
├── daily_auto_buy_execute_run.py
├── daily_auto_sell_execute_run.py
├── daily_buy_execution_run.py
├── daily_intraday_position_monitor_run.py
├── daily_sell_execution_run.py
├── db_config.py
├── execution_build_candidates.py
├── execution_builder.py
├── execution_buy_sizing.py
├── execution_config.py
├── execution_daily_position_sell_builder.py
├── execution_daily_signal_builder.py
├── execution_db.py
├── execution_execute_order.py
├── execution_position_loader.py
├── execution_repository.py
├── execution_sell_builder.py
├── execution_sell_evaluator.py
├── execution_sync_buy_fill.py
├── execution_sync_buy_position.py
├── execution_sync_sell_fill.py
├── requirements.txt
└── docs/
    └── source-file-catalog.md
```

날짜별 `docs/worklog/*.md`는 현재 문서 구조에 포함하지 않는다.
새 Worklog 파일을 만들지 않는다.

`access_token.txt`는 민감정보 후보 파일로 취급한다.
값을 읽거나 README·로그·완료 보고에 기록하지 않는다.

## 15. 파일 그룹

### 15.1 Daily BUY

| 파일 | 역할 |
|---|---|
| `daily_buy_execution_run.py` | Daily BUY 후보 생성 |
| `execution_daily_signal_builder.py` | Signal 변환 |
| `execution_buy_sizing.py` | BUY 수량 계산 |

### 15.2 Daily SELL

| 파일 | 역할 |
|---|---|
| `daily_sell_execution_run.py` | Daily SELL 후보 생성 |
| `execution_daily_position_sell_builder.py` | Position Decision 변환 |

### 15.3 Auto Execute

| 파일 | 역할 |
|---|---|
| `daily_auto_buy_execute_run.py` | READY BUY connector 호출 경로 |
| `daily_auto_sell_execute_run.py` | READY SELL connector 호출 경로 |
| `execution_execute_order.py` | 단일 Order 실행과 실행 모드 확인 |

### 15.4 Fill·Position Sync

| 파일 | 역할 |
|---|---|
| `execution_sync_buy_fill.py` | BUY Fill 반영 |
| `execution_sync_sell_fill.py` | SELL Fill과 Position 수량 반영 |
| `execution_sync_buy_position.py` | BUY Fill 기반 Position 생성·병합 |

### 15.5 Intraday

| 파일 | 역할 |
|---|---|
| `execution_position_loader.py` | OPEN Position Context 조회 |
| `execution_sell_evaluator.py` | SELL·HOLD 평가 |
| `execution_sell_builder.py` | POSITION_SELL 후보 생성 |
| `daily_intraday_position_monitor_run.py` | 장중 점검과 Stop 후보 생성 |

### 15.6 Repository·DB·Config

| 파일 | 역할 |
|---|---|
| `execution_repository.py` | Execution DB Read·Write 집중 지점 |
| `execution_db.py` | Connection과 Fetch·Execute Helper |
| `db_config.py` | DB 환경변수와 Search Path |
| `execution_config.py` | 계좌·Broker·환경·전략·Sizing 설정 |

### 15.7 Container

| 파일 | 역할 |
|---|---|
| `Dockerfile` | Execution Container Image 정의 |
| `requirements.txt` | Python Runtime Dependency |
| `create_execution_docker_files.py` | Docker 관련 파일 생성 Helper |

`create_execution_docker_files.py`는 운영 주문 entrypoint가 아니다.
파일 생성 영향은 있으므로 승인 없이 실행하지 않는다.

## 16. 주요 DB 대상

### 16.1 Execution Write 가능 테이블

| 테이블 | 주요 용도 |
|---|---|
| `strategy_execution_plan` | 실행 후보 묶음과 Summary |
| `strategy_execution_order` | BUY·SELL Order 후보와 상태 |
| `strategy_position_state` | 전략 Position 상태와 잔여 수량 |
| `strategy_daily_position_decision` | SELL Decision과 Order 연결 |
| `strategy_intraday_position_check` | 장중 Position 점검 결과 |

### 16.2 Connector Read 대상

| 테이블 | 주요 용도 |
|---|---|
| `connector_order_request` | 주문 요청과 Broker 상태 |
| `connector_fill` | 체결 수량과 가격 |
| `connector_account` | 계좌 기준 정보 |
| `connector_balance_snapshot` | 최신 잔고 |
| `connector_position_snapshot` | 최신 Broker Position |

실제 schema, column, key, status와 join 조건은 코드에서 확인한다.

## 17. DB 구조와 Search Path

기본 DB는 `portfolio`다.

현재 구조는 단일 DB 안에 domain별 schema를 두는 방식이며,
Execution 연결은 search path를 통해 관련 schema를 조회할 수 있다.

```text
execution,decision,research,connector,preprocessor,interest,reference,legacy,public
```

주의사항은 아래와 같다.

- 동일한 table name이 여러 schema에 있으면 search path 순서가 결과를 바꿀 수 있다.
- 새 SQL에서 schema-qualified name 사용 여부는 기존 패턴과 운영 기준을 확인한다.
- unique key와 upsert conflict target을 추정하지 않는다.
- Plan·Order·Fill·Position 갱신의 transaction 범위를 확인한다.
- repository helper가 내부 commit하는지 호출자가 commit하는지 확인한다.
- DDL helper가 import 또는 실행 중 자동 호출되는지 확인한다.

## 18. 외부 의존성

### 18.1 Python Dependency

| 의존성 | 용도 |
|---|---|
| `psycopg2` | PostgreSQL 연결 |
| `psycopg2.extras` | Dict·Batch 계열 Helper |
| `decimal` | 금액과 수량 계산 |
| `connector_buy` | BUY 주문 Helper |
| `connector_sell` | SELL 주문 Helper |
| Connector Quote Module | Intraday Quote 조회 |
| Holiday Helper | 거래일·휴장일 확인 |

실제 Import 목록은 각 파일과 `requirements.txt`를 기준으로 확인한다.

### 18.2 외부 저장소

MarketConnector 모듈을 외부 경로에서 import하는 코드가 있을 수 있다.

예시 경로:

```text
C:\Workspaces\port-marketconnector
```

외부 저장소는 읽기 전용 의존성으로 취급한다.
Execution 작업 요청만으로 MarketConnector 파일을 수정하지 않는다.

## 19. 설정

`db_config.py`와 `execution_config.py`는 환경변수에서 설정을 읽는다.

### 19.1 DB

| 환경변수 | 의미 |
|---|---|
| `INTEREST_DB_HOST` | DB Host |
| `INTEREST_DB_PORT` | DB Port |
| `INTEREST_DB_NAME` | DB Name |
| `INTEREST_DB_USER` | DB User |
| `INTEREST_DB_PASSWORD` | DB Password |
| `PORTFOLIO_DB_NAME` | 호환 후보, 현재 코드 미사용 |

`db_config.py`는 `INTEREST_DB_*`만 사용하며 `INTEREST_DB_NAME` 기본값은 `portfolio`다.
`PORTFOLIO_DB_NAME`은 `db_config.py`가 읽지 않으며 fallback 경로도 없다.

### 19.2 Execution

| 환경변수 | 의미 |
|---|---|
| `PORT_ACCOUNT_NO` | 계좌 식별 |
| `PORT_BROKER_NAME` | Broker 구분 |
| `PORT_ENVIRONMENT` | 실행 환경 |
| `PORT_STRATEGY_NAME` | Strategy Name |
| `PORT_STRATEGY_VERSION` | Strategy Version |
| `PORT_MAX_ORDER_AMOUNT_RATIO` | 최대 주문 금액 비율 |
| `PORT_MIN_ORDER_AMOUNT` | 최소 주문 금액 |

실제 비밀번호, Token, 계좌번호, Webhook과 운영 식별자는 문서에 기록하지 않는다.

## 20. Execution Mode

Execution Mode는 주문 안전 경계다.

개념상 아래 모드가 사용될 수 있다.

| 모드 | 의미 |
|---|---|
| `DRY_RUN` | 실제 주문 없이 검증 중심 |
| `MANUAL_TEST` | 수동 테스트 경로 |
| `PAPER_STRATEGY` | Paper Broker 실행 |
| `LIVE_STRATEGY` | Live Broker 실행 |

실제 허용 조건과 상태 저장 방식은 코드를 확인한다.

- Dry Run도 DB Write가 발생할 수 있다.
- `--execute`가 없다고 완전한 읽기 전용으로 단정하지 않는다.
- Live 실행은 환경과 별도 확인 옵션을 요구할 수 있다.
- Mode 변경은 승인 정책과 주문 위험에 직접 영향을 준다.

## 21. Container 실행

Paper Daily Step 8~11, 14~16과 Intraday Monitor는
ECS RunTask 또는 Container Command Override 대상으로 호출될 수 있다.

주요 entrypoint는 아래와 같다.

```text
python daily_buy_execution_run.py
python daily_sell_execution_run.py
python daily_auto_sell_execute_run.py --execute
python daily_auto_buy_execute_run.py --execute
python execution_sync_sell_fill.py
python execution_sync_buy_fill.py
python execution_sync_buy_position.py
python daily_intraday_position_monitor_run.py
```

실제 Cluster, Task Definition ARN, Image URI, Subnet, Security Group과 Log Group은
README에 원문으로 기록하지 않는다.

필요한 경우 아래 placeholder를 사용한다.

```text
<EXECUTION_ECS_CLUSTER>
<EXECUTION_TASK_DEFINITION_ARN>
<EXECUTION_ECR_IMAGE_URI>
<EXECUTION_LOG_GROUP>
<COMMAND_ID>
```

Docker Base Image와 기본 CMD는 실제 `Dockerfile`을 확인한다.
문서에 적힌 값이 오래되었을 가능성을 고려한다.

## 22. 실행 안전

아래 entrypoint는 승인 없이 실행하지 않는다.

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

주요 위험은 아래와 같다.

| 위험 | 영향 |
|---|---|
| DB Write | Plan·Order·Position·Check 상태 변경 |
| Connector Call | Broker 주문 요청 생성 |
| Fill Sync | Order 상태와 Position 수량 변경 |
| Position Sync | OPEN Position 생성 또는 병합 |
| Intraday Monitor | Quote 조회와 Stop Order 후보 생성 |
| 재실행 | 중복 Order·Fill·Position 반영 |
| 외부 성공·내부 실패 | Broker 주문과 DB 상태 불일치 |

## 23. 안전한 정적 확인

문서화와 리뷰에서는 정적 명령만 사용한다.

```powershell
rg --files
rg -n "pattern"
git status --short
git diff --stat
```

다음 작업은 정적 확인으로 취급하지 않는다.

- Python entrypoint 실행
- Import side effect가 불명확한 module import
- DB 연결과 Query 실행
- Connector BUY·SELL 호출
- Fill Sync와 Position Sync
- Intraday Quote와 Monitor
- AWS CLI·SDK 호출
- ECS·SSM·Step Functions 실행

## 24. 문서 체계

| 문서 | 역할 |
|---|---|
| `AGENTS.md` | 작업·상태·데이터·안전 규칙 |
| `README.md` | 현재 구조와 운영 AS-IS |
| `CHANGELOG.md` | 실제 변경 이력과 당시 사실 |
| `docs/source-file-catalog.md` | 파일 책임·입출력·변경 영향 |

같은 사실을 여러 문서에 장문으로 반복하지 않는다.

- README는 현재 상태를 설명한다.
- CHANGELOG는 과거 변경 사실을 보존한다.
- Source Catalog는 파일별 책임과 변경 영향을 설명한다.
- 날짜별 Worklog는 새로 만들지 않는다.

## 25. 현재 확인이 필요한 항목

아래 항목은 실제 코드와 운영 정의를 정적으로 대조해 확정해야 한다.

| 항목 | 확인 대상 |
|---|---|
| Step Command | 실제 ECS Command Override |
| Plan Key | Daily·Position·Backtest별 재사용 기준 |
| Order Key | 중복 방지 Unique Key와 Conflict Target |
| Status | Plan·Order·Connector의 실제 상태 문자열 |
| Partial Fill | 부분 체결 상태와 재실행 처리 |
| SELL Sync | Position 차감 Transaction 범위 |
| BUY Sync | 추가 매수 병합 기준 |
| Intraday | 점검 저장과 Order 생성 분기 |
| Execution Mode | 각 모드의 실제 허용 조건 |
| Docker | Base Image와 기본 CMD |
| External Import | MarketConnector·Holiday Helper 실제 경로 |

확인되지 않은 내용은 운영 사실로 단정하지 않는다.

## 26. 관련 문서

- [AGENTS.md](AGENTS.md)
- [CHANGELOG.md](CHANGELOG.md)
- [Source File Catalog](docs/source-file-catalog.md)
