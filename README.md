# port_strategy_execution

`port_strategy_execution` is a Python microservice that converts strategy decision results into
execution-layer plans and order candidates, and connects order requests, fills, and strategy
position state.

This document describes the current repository structure and operational AS-IS.
It does not perform actual order creation and submission, fill synchronization, position updates,
DB writes, external API calls, or AWS execution procedures without approval.

## 1. Service Summary

| Item | Value |
|---|---|
| Service | `port_strategy_execution` |
| Primary responsibility | Execution Plan and Order creation, and connection of Order, Fill, and strategy Position |
| Primary input | Daily BUY signal, Daily Position SELL decision, connector account, balance, position, and fill |
| Primary output | `strategy_execution_plan`, `strategy_execution_order`, `strategy_position_state` |
| Operating location | AWS Paper Daily Step 8~11, 14~16, and intraday Intraday Evaluate |
| Execution form | Centered on root-level Python entrypoints |
| Order API | Via MarketConnector helper |
| Default policy | Separate candidate creation from the approval boundary and prevent duplicate orders |
| CI · Release | main Push based Build/Test/ECR and Automatic no-order Release |
| Artifact Identity | Git SHA Tag and ECR Image Digest |
| Promotion method | Compose a new Task Definition from the validated Digest and current operating Runtime settings, then automatically promote the State Machine reference |
| Execution boundary | Separate Business Execution from Release Definition changes |
| Documentation basis | Static confirmation of the current code and file structure |

## 2. Primary Responsibilities

| Area | Responsibility |
|---|---|
| Daily BUY Execution | Convert Daily BUY signal into BUY execution order candidates |
| Daily SELL Execution | Convert Daily Position SELL decision into SELL execution order candidates |
| Execution Plan | Create execution-unit Plans and manage summary status |
| Execution Order | Create BUY·SELL order candidates, query, and update status |
| Auto Execute | Pass approved READY Orders to the connector call path |
| Fill Sync | Reflect connector order requests and fills into Execution state |
| Position Sync | Create OPEN Positions from BUY fills and deduct quantity from SELL fills |
| Intraday Monitor | Check OPEN Positions and create Stop Sell candidates |
| Backtest Candidate | Maintain the path that converts Backtest results into separate Execution candidates |

## 3. Responsibility Boundary

Execution is the execution layer between strategy decisions and the Broker implementation.

| Area | Owner |
|---|---|
| Source data collection | Crawler |
| Raw preprocessing and Feature generation | Preprocessor |
| Daily BUY Signal decision | StrategyDecision |
| Daily Position HOLD·SELL·SKIP decision | StrategyDecision |
| Backtest and Research Report | StrategyResearch |
| Connection of Plan·Order·Fill·strategy Position | StrategyExecution |
| Broker·KIS API and Token management | MarketConnector |
| Approval UI and screen display | port-view |
| Full Daily Orchestration | Scheduler and Step Functions |

Execution does not directly own the following responsibilities.

- The BUY·SELL decision algorithm itself
- The MarketConnector internal order API implementation
- Source data collection and Feature generation
- View rendering and approval screens
- The full Step Functions definition
- EventBridge Scheduler operation
- Backtest performance analysis and Report generation

Other MS are described only at the input/output contract level required by Execution.

## 4. End-to-End Data Flow

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
          Approval·Execution boundary
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

Each stage has its own success condition.

| Stage | Success criterion |
|---|---|
| Candidate creation | Plan and Order are created based on the intended source |
| Order request | The connector request link and request status are recorded |
| Order acceptance | The Broker response and connector status are confirmed |
| Fill reflection | Cumulative fill quantity and average price are reflected into Execution |
| Position reflection | BUY·SELL fill results are accurately reflected into the strategy Position |

The success of one stage is not treated as the success of the next stage.

## 5. AWS Paper Daily Role

Execution does not own the full Daily Batch.
The following summarizes only the Step roles from the Execution perspective.

| Step | Execution perspective |
|---|---|
| Step 8 | Daily BUY execution order candidate creation |
| Step 9 | Daily SELL execution order candidate creation |
| Step 10 | READY SELL auto execute path |
| Step 11 | READY BUY auto execute path |
| Step 12~13 | MarketConnector order submission and order query |
| Step 14 | SELL fill sync |
| Step 15 | BUY fill sync |
| Step 16 | BUY position sync |
| Step 17 | MarketConnector balance refresh |

### 5.1 Step 8 · Daily BUY Execution

`daily_buy_execution_run.py` can read the latest Daily Run and BUY Signal
to create BUY Execution Plan and Order candidates.

The primary related files are as follows.

| File | Role |
|---|---|
| `daily_buy_execution_run.py` | BUY candidate creation entrypoint |
| `execution_daily_signal_builder.py` | Convert Signal into Order payload |
| `execution_buy_sizing.py` | Compute order quantity |
| `execution_repository.py` | Store Plan·Order and update summary |

This is the candidate creation stage.
It does not mean Broker order submission succeeded.

### 5.2 Step 9 · Daily SELL Execution

`daily_sell_execution_run.py` can read the SELL Decision of the latest Daily Position Decision Run
to create SELL Execution Order candidates.

| File | Role |
|---|---|
| `daily_sell_execution_run.py` | SELL candidate creation entrypoint |
| `execution_daily_position_sell_builder.py` | Convert Decision into Order payload |
| `execution_repository.py` | Store Order and link Decision |

A `strategy_daily_position_decision.execution_order_id` link may occur.
On re-run, the existing link and duplicate Order must be confirmed together.

### 5.3 Step 10~11 · Auto Execute

| Step | Entry Point | Primary impact |
|---|---|---|
| Step 10 | `daily_auto_sell_execute_run.py --execute` | Query READY SELL and call connector SELL |
| Step 11 | `daily_auto_buy_execute_run.py --execute` | Query READY BUY and call connector BUY |

Auto Execute has the following boundaries.

- Query READY Orders
- Confirm execution mode
- Confirm quantity and target account
- Call connector helper
- Link connector request
- Update Execution status
- On failure, decide error status or retry

Even when it calls the connector helper, responsibility for the Broker order API implementation belongs to MarketConnector.

### 5.4 Step 12~13 · MarketConnector Segment

This segment is a MarketConnector responsibility.

Execution understands that the following data is prepared as input for the subsequent Sync.

- `connector_order_request`
- `connector_fill`
- Broker order status
- Cumulative fill quantity
- Average fill price

The Execution documentation does not duplicate the MarketConnector internal Token, Endpoint, and retry implementation.

### 5.5 Step 14 · SELL Fill Sync

`execution_sync_sell_fill.py` can read the connector request and fill of SELL orders
and reflect them into the Execution Order and strategy Position.

The primary items to confirm are as follows.

| Item | Confirmation content |
|---|---|
| Cumulative fill quantity | Confirm it is cumulative-based, not only new fills |
| Partial fill | Confirm partial quantity is not treated as a full fill |
| Duplicate fill | Confirm the criterion that prevents reprocessing the same fill |
| Remaining Quantity | Confirm it is deducted exactly by the fill quantity |
| Position Status | Confirm CLOSED transition only when remaining quantity is 0 |
| Order Status | Confirm the actual completion condition and status string |

### 5.6 Step 15 · BUY Fill Sync

`execution_sync_buy_fill.py` reads the final Connector Request status and fills of BUY orders
and reflects the Execution Order into a Terminal status.

| Item | Confirmation content |
|---|---|
| FILLED | Handle as `FILLED` Terminal after aggregating fills |
| CANCELED | Handle a normally canceled Request as a separate `CANCELED` Terminal |
| CANCELED + 0 fills | Treat as normal termination, not a failure |
| CANCELED + fills present | Judge as an error |
| Partial fill | Compare requested and cumulative quantity without confusing it with CANCELED |
| Average price | Based on the actual fill weighted average |
| Summary | Separate filled·canceled·terminal·failed counts |
| Failure aggregation | Exclude normal CANCELED from the failed count |

FILLED and CANCELED are distinguished as separate Terminal results.
A normally canceled order with no fills is not aggregated into the failed count.

### 5.7 Step 16 · BUY Position Sync

`execution_sync_buy_position.py` reflects only FILLED BUY Orders into the strategy Position.

| Situation | Confirmation criterion |
|---|---|
| FILLED BUY | Target for Position creation or merge into existing OPEN |
| CANCELED BUY | Not a Position creation target |
| Execution order | Run Step 16 after the Step 15 FILLED Commit |
| New ticker | Create a new OPEN Position |
| Existing OPEN Position | Confirm the additional-buy merge policy |
| Re-run | Prevent duplicate Position creation from the same BUY fill |
| Success judgment | Confirm with target·created·failed counts |

Distinguish a 0-target success from an actual Position creation success.
Do not merge Step 15 success into Step 16 Position creation success.

### 5.8 Step 17 · Balance Refresh

Balance Refresh is a MarketConnector responsibility segment.

Execution can subsequently use the following Snapshots as query inputs.

- `connector_balance_snapshot`
- `connector_position_snapshot`

Execution itself is not described as owning responsibility for creating the Broker Balance Snapshot.

### 5.9 P0 Order Chain Validator

`execution_validate_order_chain.py` validates the execution chain read-only after Step 16.
It confirms the Plan → Order → Connector Request → Fill → Position chain together.

| Target | Validation criterion |
|---|---|
| FILLED BUY | Must have Connector Fill and Position trace to be normal |
| CANCELED BUY | With a valid cancellation chain, normal Terminal without Fill·Position |
| Execution status | Does not judge finality by an intermediate status alone |
| Overall judgment | Confirm Connector Request final status, Fill total, and Position together |

It does not assert chain success by an intermediate status such as `SUBMITTED` alone.
`--allow-no-target` is an option for normal termination with 0 targets and does not hide an actual Target error.

## 6. Intraday Evaluate

The intraday OPEN Position check is centered on `daily_intraday_position_monitor_run.py`.

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
        ├─ HOLD·check result
        │
        └─ Hard Stop candidate
                │
                ▼
strategy_intraday_position_check
strategy_execution_order
```

### 6.1 Primary Files

| File | Role |
|---|---|
| `execution_position_loader.py` | Combine strategy Position with connector Snapshot |
| `execution_sell_evaluator.py` | Evaluate Position·Stock Feature·Market Feature |
| `execution_sell_builder.py` | Create POSITION_SELL Order candidates |
| `daily_intraday_position_monitor_run.py` | Store checks and create Stop Sell candidates |

### 6.2 Check Result and Order Candidate

Storing the intraday check result and creating an order candidate are separate impacts.

| Impact | Meaning |
|---|---|
| Check storage | Record `strategy_intraday_position_check` |
| Order candidate | Create `INTRADAY_STOP_SELL` or a related SELL candidate |
| Actual order | Requires a separate approval and connector execution boundary |

Options such as `--create-order` can lead to DB writes and Order creation.
They are not executed in static documentation review.

## 7. Execution Plan Contract

`strategy_execution_plan` is the higher-level concept that groups one execution candidate creation unit.

When changing anything Plan-related, confirm the following items.

| Item | Confirmation criterion |
|---|---|
| Source | Distinguish Daily Signal, Position Decision, or Backtest |
| Business Date | Based on the actual target trade date |
| Source Run ID | Linked to the correct source Run |
| Environment | Distinguish Paper·Live |
| Strategy | Strategy Name and Version |
| Summary | BUY·SELL·Skip·Error aggregation criteria |
| Status | Meaning of in-progress, complete, and failed states |
| Re-run | Reuse or new-creation policy based on the same Source |
| Empty candidate | Distinguish a normal No Target from a missing input |

The mere existence of a Plan does not mean all Orders were created normally.

## 8. Execution Order Contract

`strategy_execution_order` is the central table that connects executable BUY·SELL candidates
with the order processing status.

### 8.1 Primary Identification Criteria

| Item | Purpose |
|---|---|
| Plan ID | Link to the higher execution unit |
| Source Type | Distinguish Daily Signal·Position Decision·Backtest·Intraday |
| Source ID | Maintain traceability with the source row |
| Ticker | Order target ticker |
| Side | BUY or SELL |
| Requested Quantity | Requested order quantity |
| Execution Mode | Dry Run·Manual·Paper·Live boundary |
| Connector Request ID | Link to the MarketConnector order request |
| Status | Represent candidate·request·fill·failure status |

Confirm the actual column names and keys in the code and DB definition.
Do not add nonexistent columns for documentation convenience.

### 8.2 Status Transition

Confirm the status strings and transition conditions against the implementation.

The conceptual flow is as follows.

```text
Candidate
  → Ready
  → Requested
  → Accepted or Working
  → Partially Filled
  → Filled
```

Failure·cancellation·rejection·No Target states may be separate paths.

- Do not finalize status names by convention alone.
- Do not assume Connector status and Execution status are the same value.
- Do not transition a partial fill to `FILLED` early.
- Do not treat a successful DB update as a successful Broker order.

### 8.3 Idempotency and Duplicate Orders

This is the first risk to confirm during retries and re-runs.

| Risk | Confirmation criterion |
|---|---|
| Duplicate candidate | Prevent duplicate Order creation for the same Source·Ticker·Side |
| Duplicate submission | Confirm whether an existing connector request exists |
| External success·DB failure | Recovery criterion for a local link failure after Broker acceptance |
| Duplicate Sync | Prevent repeated aggregation of the same fill |
| Duplicate Position | Prevent repeated Position reflection of the same BUY fill |

Confirm the actual definitions of duplicate-prevention keys, unique constraints, and upsert conflict targets.

## 9. BUY Sizing Contract

`execution_buy_sizing.py` is the calculation layer that converts a BUY Signal into an actual order quantity.
Orders are currently market-order (`MARKET`) based, and a cash Reserve is applied to prepare for market-fill fluctuation.

| Input | Confirmation content |
|---|---|
| Target Amount | Target holding amount based on total valuation and target weight |
| Available Cash | Usable cash |
| Current Holding | Current holding quantity and valuation |
| Latest Price | Latest price used as the quantity calculation basis |
| Maximum Ratio | Maximum order amount ratio |
| Minimum Amount | Minimum order amount |
| Rounding | Integer quantity and truncation criterion |

The market-order BUY quantity and required cash are computed based on the Reserve Ratio `1.10`.

| Item | Criterion |
|---|---|
| Reserve Ratio | `MARKET_BUY_CASH_RESERVE_RATIO` is `1.10` |
| Effective order price | Apply 110% of `latest_price` in the quantity calculation |
| Quantity truncation | Truncate to an integer quantity based on the effective order price |
| Estimated order amount | `latest_price * order_qty` |
| Required cash | 110% of the estimated order amount (`required_cash_amount`) |
| Cash validation | BLOCKED if the required cash exceeds available cash |

Distinguish the estimated order amount from the required cash including Reserve.
Applying the Reserve itself does not guarantee the Broker orderable amount.

Clearly distinguish the following situations.

- Computed quantity 0
- Below the minimum order amount
- Insufficient available cash
- Target holding amount already met
- Missing or 0 price
- Mismatch between current holding and connector Snapshot

A change to the Sizing logic directly affects the actual order amount.

### 9.1 Multi-Candidate Cumulative Available-Cash Allocation

`execution_buy_sizing.py` handles only the order quantity calculation for a single ticker.
Cumulative available-cash allocation across multiple BUY candidates is handled by the
candidate creation flow in `execution_daily_signal_builder.py`.

| Item | Criterion |
|---|---|
| Processing order | Preserve the confirmed candidate order |
| Cumulative cash | Manage remaining available cash within one Daily Plan |
| READY deduction | Deduct the required cash including Reserve of a READY order from the next candidate |
| BLOCKED · 0 shares | Do not deduct available cash |
| Overflow prevention | If a subsequent BUY exceeds remaining cash, reduce or block it |
| Deduction basis | Based on 110% required cash, not the estimated order amount |
| Traceability | Keep per-candidate available cash, estimated order amount, and required cash in the Payload |

Distinguish the single-ticker Sizing function from the Plan-level cumulative allocation responsibility.
Do not reuse the initial available cash as-is in subsequent candidate calculations.

## 10. SELL Quantity Contract

The SELL quantity may consider the strategy Position and the Broker holding quantity together.

| Basis | Meaning |
|---|---|
| Strategy Remaining Quantity | Quantity still held per the strategy |
| Connector Sellable Quantity | Quantity actually sellable at the Broker |
| Requested Quantity | Quantity to request in this Order |
| Filled Quantity | Actual cumulative filled quantity |

When the two quantities differ, do not arbitrarily choose one as correct.

The situations to confirm are as follows.

- Broker quantity is less than the strategy quantity
- Broker quantity is 0
- An unfilled SELL Order already exists
- Re-evaluation after a partial sell
- Reselection of a Position in SELL_ORDERED status
- Multiple OPEN Positions exist for the same ticker

## 11. Fill Sync Contract

Fill Sync is not a simple task of copying connector data into Execution state.

| Item | Confirmation criterion |
|---|---|
| Request Scope | Select the correct connector request |
| Fill Scope | Order number·ticker·Side·trade date range |
| Aggregation | Cumulative quantity and weighted average price |
| Duplicate | Duplicate handling of the same fill identifier |
| Partial Fill | Handling a fill smaller than the requested quantity |
| Retry | Re-run results must be identical |
| Transaction | Atomicity of Order and Position changes |
| Error | Recovery criterion for a failure after partial reflection |

Distinguish 0 fills into the following two situations.

- A normal state that is not yet filled
- A missing connector request or fill link

## 12. Position State Contract

`strategy_position_state` is the holding state based on the strategy.
It is not the same concept as the Broker Position Snapshot.

### 12.1 BUY Position Reflection

| Situation | Expected confirmation |
|---|---|
| First BUY | Create OPEN Position |
| Additional BUY | Confirm whether to merge into the existing OPEN |
| Partial fill | Reflect only the filled quantity |
| Re-run | Prohibit duplicate reflection of the same fill |
| Average price | Confirm the formula that merges the existing Position with a new Fill |

### 12.2 SELL Position Reflection

| Situation | Expected confirmation |
|---|---|
| Partial SELL | Deduct only `remaining_qty` |
| Full SELL | Remaining quantity 0 and CLOSED transition |
| Unfilled | Prohibit Position quantity changes |
| Duplicate Sync | Prohibit re-deduction of the same fill |
| SELL_ORDERED | Confirm the ordering status and the OPEN·CLOSED relationship |

A Position status change must be traceable to Order and Fill evidence.

## 13. Backtest-Based Candidates

`backtest_execution_run.py` is a separate path that can convert Research results into Execution candidates.

| File | Role |
|---|---|
| `backtest_execution_run.py` | Create candidates based on Backtest Run·Daily·Trade Log |
| `execution_builder.py` | Convert Backtest BUY·SELL results into Order payload |
| `execution_build_candidates.py` | Legacy or standalone candidate creation path |

Backtest candidates are not represented as the same input as Daily operational Signals.

- Research results are not actual investment recommendations.
- Backtest candidates are not automatically promoted to Daily automatic order targets.
- Confirm actual operational use against the call path and Wrapper.
- Do not determine legacy status by the filename alone.

## 14. Primary File Structure

```text
.
├── .github/
│   └── workflows/
│       └── execution-codebuild.yml
├── .devops/
│   ├── codebuild/
│   │   └── buildspec.yml
│   └── scripts/
│       ├── container-smoke.py
│       └── deploy-execution.sh
├── .dockerignore
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── Dockerfile
├── README.md
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
├── execution_validate_order_chain.py
├── execution_validate_ready_plan_order.py
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
├── tests/
└── docs/
    └── source-file-catalog.md
```

`.devops` and `.github` are CI·Build assets and are excluded from the Runtime Image per `.dockerignore`.
`tests/` and `docs/` are also not included in the Runtime Image.

Date-specific `docs/worklog/*.md` are not included in the current document structure.
Do not create new Worklog files.

`access_token.txt` is a Runtime sensitive-file candidate.
It is excluded from Git tracking and the Docker Build Context·Image, and its value is not read or recorded in documents, logs, or completion reports.
It is not shown as a tracked Source in the repository file structure tree.

## 15. File Groups

### 15.1 Daily BUY

| File | Role |
|---|---|
| `daily_buy_execution_run.py` | Daily BUY candidate creation |
| `execution_daily_signal_builder.py` | Signal conversion |
| `execution_buy_sizing.py` | BUY quantity calculation |

### 15.2 Daily SELL

| File | Role |
|---|---|
| `daily_sell_execution_run.py` | Daily SELL candidate creation |
| `execution_daily_position_sell_builder.py` | Position Decision conversion |

### 15.3 Auto Execute

| File | Role |
|---|---|
| `daily_auto_buy_execute_run.py` | READY BUY connector call path |
| `daily_auto_sell_execute_run.py` | READY SELL connector call path |
| `execution_execute_order.py` | Single Order execution and execution-mode confirmation |

### 15.4 Fill·Position Sync

| File | Role |
|---|---|
| `execution_sync_buy_fill.py` | Reflect BUY Fill |
| `execution_sync_sell_fill.py` | Reflect SELL Fill and Position quantity |
| `execution_sync_buy_position.py` | Create·merge Position based on BUY Fill |

### 15.5 Intraday

| File | Role |
|---|---|
| `execution_position_loader.py` | Query OPEN Position Context |
| `execution_sell_evaluator.py` | SELL·HOLD evaluation |
| `execution_sell_builder.py` | Create POSITION_SELL candidates |
| `daily_intraday_position_monitor_run.py` | Intraday check and Stop candidate creation |

### 15.6 Repository·DB·Config

| File | Role |
|---|---|
| `execution_repository.py` | Central point for Execution DB Read·Write |
| `execution_db.py` | Connection and Fetch·Execute Helper |
| `db_config.py` | DB environment variables and Search Path |
| `execution_config.py` | Account·Broker·environment·strategy·Sizing settings |

### 15.7 Container

| File | Role |
|---|---|
| `Dockerfile` | Execution Container Image definition |
| `requirements.txt` | Python Runtime Dependency |
| `create_execution_docker_files.py` | Helper that generates Docker-related files |

`create_execution_docker_files.py` is not an operational order entrypoint.
It has a file-creation impact, so it is not executed without approval.

## 16. Primary DB Targets

### 16.1 Execution Writable Tables

| Table | Primary use |
|---|---|
| `strategy_execution_plan` | Execution candidate group and Summary |
| `strategy_execution_order` | BUY·SELL Order candidates and status |
| `strategy_position_state` | Strategy Position status and remaining quantity |
| `strategy_daily_position_decision` | SELL Decision and Order link |
| `strategy_intraday_position_check` | Intraday Position check result |

### 16.2 Connector Read Targets

| Table | Primary use |
|---|---|
| `connector_order_request` | Order request and Broker status |
| `connector_fill` | Fill quantity and price |
| `connector_account` | Account reference information |
| `connector_balance_snapshot` | Latest balance |
| `connector_position_snapshot` | Latest Broker Position |

Confirm the actual schema, column, key, status, and join conditions in the code.

## 17. DB Structure and Search Path

The default DB is `portfolio`.

The current structure places a schema per domain within a single DB,
and the Execution connection can query the related schemas through the search path.

```text
execution,decision,research,connector,preprocessor,interest,reference,legacy,public
```

The cautions are as follows.

- If the same table name exists in multiple schemas, the search path order can change the result.
- Confirm whether new SQL uses schema-qualified names against the existing pattern and operating basis.
- Do not assume unique keys and upsert conflict targets.
- Confirm the transaction scope of Plan·Order·Fill·Position updates.
- Confirm whether the repository helper commits internally or the caller commits.
- Confirm whether a DDL helper is called automatically on import or during execution.

## 18. External Dependencies

### 18.1 Python Dependency

| Dependency | Use |
|---|---|
| `psycopg2` | PostgreSQL connection |
| `psycopg2.extras` | Dict·Batch family Helpers |
| `decimal` | Amount and quantity calculation |
| `connector_buy` | BUY order Helper |
| `connector_sell` | SELL order Helper |
| Connector Quote Module | Intraday Quote query |
| Holiday Helper | Trade day·holiday confirmation |

Confirm the actual Import list against each file and `requirements.txt`.

### 18.2 External Repository

There may be code that imports the MarketConnector module from an external path.

Example path:

```text
C:\Workspaces\port-marketconnector
```

The external repository is treated as a read-only dependency.
Do not modify MarketConnector files based on an Execution work request alone.

## 19. Configuration

`db_config.py` and `execution_config.py` read settings from environment variables.

### 19.1 DB

| Environment variable | Meaning |
|---|---|
| `INTEREST_DB_HOST` | DB Host |
| `INTEREST_DB_PORT` | DB Port |
| `INTEREST_DB_NAME` | DB Name |
| `INTEREST_DB_USER` | DB User |
| `INTEREST_DB_PASSWORD` | DB Password |
| `PORTFOLIO_DB_NAME` | Compatibility candidate, currently unused by the code |

`db_config.py` uses only `INTEREST_DB_*`, and the `INTEREST_DB_NAME` default is `portfolio`.
`PORTFOLIO_DB_NAME` is not read by `db_config.py` and has no fallback path.

### 19.2 Execution

| Environment variable | Meaning |
|---|---|
| `PORT_ACCOUNT_NO` | Account identifier, required, no code Fallback |
| `PORT_BROKER_NAME` | Broker identifier |
| `PORT_ENVIRONMENT` | Execution environment |
| `PORT_STRATEGY_NAME` | Strategy Name |
| `PORT_STRATEGY_VERSION` | Strategy Version |
| `PORT_MAX_ORDER_AMOUNT_RATIO` | Maximum order amount ratio |
| `PORT_MIN_ORDER_AMOUNT` | Minimum order amount |

`execution_config.py` requires `PORT_ACCOUNT_NO` and fails fast if it is unset.
In the AWS Runtime, the actual account number is injected from a Secret.
In the CI Harness (pytest CodeBuild, Container Smoke), a test placeholder is used rather than the actual account number.

Actual passwords, Tokens, account numbers, Webhooks, and operational identifiers are not recorded in the documentation.

## 20. Execution Mode

Execution Mode is the order safety boundary.

Conceptually, the following modes may be used.

| Mode | Meaning |
|---|---|
| `DRY_RUN` | Validation-centered without an actual order |
| `MANUAL_TEST` | Manual test path |
| `PAPER_STRATEGY` | Paper Broker execution |
| `LIVE_STRATEGY` | Live Broker execution |

Confirm the actual allowed conditions and status storage method in the code.

- A Dry Run may also produce a DB Write.
- Do not assume it is completely read-only just because `--execute` is absent.
- Live execution may require the environment and a separate confirmation option.
- A Mode change directly affects the approval policy and order risk.

## 21. Container Execution

Paper Daily Step 8~11, 14~16, and the Intraday Monitor
may be invoked as ECS RunTask or Container Command Override targets.

The primary entrypoints are as follows.

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

The actual Cluster, Task Definition ARN, Image URI, Subnet, Security Group, and Log Group
are not recorded verbatim in the README.

Use the following placeholders when needed.

```text
<EXECUTION_ECS_CLUSTER>
<EXECUTION_TASK_DEFINITION_ARN>
<EXECUTION_ECR_IMAGE_URI>
<EXECUTION_LOG_GROUP>
<COMMAND_ID>
```

The current `Dockerfile` Base Image is `python:3.13-slim`, and the default CMD is
`python daily_auto_buy_execute_run.py`.
The default CMD operates without `--execute`, and CI only confirms this CMD contract without executing it.

### 21.1 CI and Automatic Release

Execution is currently configured as a main Push based Automatic no-order Release.
CodeBuild handles Build·Test·Container Smoke·ECR Artifact creation,
and the GitHub Workflow Release control-plane performs the subsequent operational Promotion.

| Item | Criterion |
|---|---|
| Trigger | main Push automatic run and `workflow_dispatch` Build-only path |
| CI authentication | GitHub Actions → OIDC → Execution-dedicated CodeBuild |
| CodeBuild scope | Compile·pytest·Ruff·Docker Build·Container Source Compile·Container Import/File Smoke |
| Artifact | Git SHA based ECR Image Publish on validation success |
| Release control-plane | Register a new Task Definition from the validated Digest and current operating Runtime settings, then automatically promote the State Machine reference |
| Approval stage | No manual Approve stage |
| Safety boundary | Definition Backup, Stale Promotion Guard, Promotion After-check, automatic Rollback on failure |
| Business Execution | No order·DB Write·ECS RunTask·Step Functions execution in the Release Pipeline |

The Release control-plane State Machine Definition reference change and State Machine execution are different tasks.
The Release changes only the Definition and does not execute the State Machine itself.
CI·Release Build success is not interpreted as actual Daily order execution success.

DevOps Architecture, detailed IAM policy, the full Promotion/Rollback design, and the common Release strategy
are managed separately in the `port-devops` Repository.

## 22. Execution Safety

The following entrypoints are not executed without approval.

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

The primary risks are as follows.

| Risk | Impact |
|---|---|
| DB Write | Plan·Order·Position·Check status changes |
| Connector Call | Broker order request creation |
| Fill Sync | Order status and Position quantity changes |
| Position Sync | OPEN Position creation or merge |
| Intraday Monitor | Quote query and Stop Order candidate creation |
| Re-run | Duplicate Order·Fill·Position reflection |
| External success·internal failure | Broker order and DB status mismatch |

## 23. Safe Static Confirmation

Documentation and review use only static commands.

```powershell
rg --files
rg -n "pattern"
git status --short
git diff --stat
```

The following are not treated as static confirmation.

- Running a Python entrypoint
- Importing a module with unclear Import side effects
- DB connection and query execution
- Connector BUY·SELL calls
- Fill Sync and Position Sync
- Intraday Quote and Monitor
- AWS CLI·SDK calls
- ECS·SSM·Step Functions execution

## 24. Documentation System

| Document | Role |
|---|---|
| `AGENTS.md` | Work·status·data·safety rules |
| `README.md` | Current structure and operational AS-IS |
| `CHANGELOG.md` | Actual change history and facts at the time |
| `docs/source-file-catalog.md` | File responsibilities·input/output·change impact |

Do not repeat the same facts at length across multiple documents.

- The README describes the current state.
- The CHANGELOG preserves past change facts.
- The Source Catalog describes per-file responsibilities and change impact.
- Do not create new date-specific Worklogs.

## 25. Confirmed Items and Items Requiring Confirmation

### 25.1 Recently Confirmed Items

| Item | Confirmed content |
|---|---|
| Release method | main Push based Automatic no-order Release |
| Artifact Identity | Git SHA Tag and ECR Image Digest |
| Docker CMD | Default CMD is `python daily_auto_buy_execute_run.py` (confirmed without execution) |
| MARKET BUY Reserve | Apply 110% Reserve to market-order quantity·required cash |
| Cumulative cash allocation | Sequentially deduct the required cash including Reserve of READY candidates |
| Step 15 CANCELED | Handle a normal cancellation as a separate Terminal, not a failure |
| BUY Position creation condition | Only FILLED BUY is a target, CANCELED BUY is excluded |
| Operational Promotion | The Release control-plane registers a new Task Definition and automatically switches the State Machine reference |
| Activation Scope | 12 State Machines / 28 Execution States |
| Rollback method | Restore the previous reference with the backup Definition, automatic Rollback on failure |

### 25.2 Items Still Requiring Confirmation

| Item | Confirmation target |
|---|---|
| Step Command | The actual ECS Command Override of the full Daily |
| Plan Key | Reuse criteria per Daily·Position·Backtest |
| Order Key | Duplicate-prevention Unique Key and Conflict Target |
| Status | The full status strings of Plan·Order·Connector |
| Partial Fill | Partial fill status and re-run handling |
| SELL Sync | Position deduction Transaction scope |
| Intraday | Transaction boundary of check storage and Order creation |
| Execution Mode | The actual allowed condition of each mode |
| External Import | The actual paths of MarketConnector·Holiday Helper |
| Available Cash | Difference between Execution available cash and Broker orderable amount |
| READY Plan Count | Actionable·Terminal Count contract of recovery re-runs |
| FAILED·REJECTED Chain | The Validator's Terminal Failure classification criteria |

Do not assert unconfirmed content as operational fact.

## 26. Related Documents

- [AGENTS.md](AGENTS.md)
- [CHANGELOG.md](CHANGELOG.md)
- [Source File Catalog](docs/source-file-catalog.md)
