# Source File Catalog

Organizes the responsibilities, inputs·outputs, DB impact, and confirmation targets on change
of the primary sources and documents of `port_strategy_execution`.

This document is not a full file inventory but a file responsibility map for
files important to Execution operations and maintenance.

It does not perform actual order creation·submission, Connector calls, Fill·Position Sync,
DB DDL·DML, external API, and AWS execution.

## 1. Document Usage Basis

| Item | Value |
|---|---|
| Target | The primary files of the `port_strategy_execution` Root and `docs` |
| Basis | Static confirmation of the current file structure and source |
| Primary perspective | Responsibility, input, output, DB impact, external impact, change risk |
| Excluded | Cache, Build artifacts, IDE temporary files |
| Execution | Do not execute Python Entry Points and DB·Connector during documentation work |
| Sensitive information | Do not record actual values or even partial strings |
| Update timing | On changes to file·responsibility·input/output·status·DB·Wrapper |
| Current structure | `README.md` |
| Work rules | `AGENTS.md` |
| Change history | `CHANGELOG.md` |

## 2. Service Responsibility Map

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
          Approval·Execution boundary
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

| Layer | Execution responsibility |
|---|---|
| Input query | Query Signal·Decision·Backtest·Connector state |
| Candidate conversion | Convert source data into Execution Order Payload |
| Quantity calculation | BUY Sizing and SELL quantity limits |
| Plan | Manage the execution candidate group and Summary |
| Order | Manage BUY·SELL candidates and processing status |
| Order linkage | Pass approved Orders to the Connector Helper |
| Fill Sync | Reflect Connector Fill into Execution state |
| Position Sync | Reflect fills into the strategy Position |
| Intraday | Check OPEN Positions and create Stop Sell candidates |

## 3. Root Documents

### `AGENTS.md`

| Item | Value |
|---|---|
| Responsibility | Define Execution-specific work·safety·data contracts |
| Primary content | Plan·Order·Fill·Position·duplicate submission·Transaction rules |
| Usage timing | Before starting any Execution code·documentation work |
| Change impact | The entire Kiro work scope and validation criteria |
| Caution | Does not replace the README current state or the CHANGELOG past history |
| Update condition | When the work scope, contracts, risks, or documentation system change |

### `README.md`

| Item | Value |
|---|---|
| Responsibility | Describe the current service structure and operational AS-IS |
| Primary content | Responsibility boundary, Daily Step, Intraday, data contracts, configuration |
| Usage timing | Understanding the service and confirming the operational flow |
| Change impact | New contributors' understanding of the structure |
| Caution | Do not accumulate past change history at length |
| Update condition | When the current structure·input/output·operating location·usage changes |

### `CHANGELOG.md`

| Item | Value |
|---|---|
| Responsibility | Preserve the primary change facts by date |
| Primary content | Documentation·code·DB·operational changes and whether executed |
| Usage timing | Confirming the change background and facts at the time |
| Change impact | Traceability and regression analysis |
| Caution | Do not repeat the current-state description |
| Update condition | When a meaningful code·configuration·documentation basis changes |

### `docs/source-file-catalog.md`

| Item | Value |
|---|---|
| Responsibility | A per-file responsibility·input/output·impact map |
| Primary content | Entrypoint, Builder, Repository, Sync, Wrapper |
| Usage timing | Confirming modification targets and related files |
| Change impact | Preventing missed impact scope |
| Caution | Do not unconditionally list every trivial file |
| Update condition | On file addition·deletion·rename·responsibility·call-relationship change |

## 4. Configuration and DB Common Layer

### `db_config.py`

| Item | Value |
|---|---|
| Responsibility | Compose the PostgreSQL connection settings |
| Input | `INTEREST_DB_*` environment variables and related compatibility settings |
| Output | Settings for the `psycopg2` connection |
| DB impact | The connection itself is absent, or possible depending on the call path |
| Primary contract | DB Name, User, Password required conditions, Search Path |
| Change risk | Wrong DB·Schema connection, Credential exposure |
| Confirmation target | Search Path order; `PORTFOLIO_DB_NAME` is currently unused by the code |
| Execution | Do not execute before confirming Import Side Effects |

### `execution_config.py`

| Item | Value |
|---|---|
| Responsibility | Provide Execution common environment settings |
| Input | Account·Broker·environment·strategy·Sizing environment variables |
| Output | Settings used by Entry Points and Builders |
| DB impact | No direct DB Write |
| External impact | Environment and Account affect the order target |
| Primary contract | Execution Mode, Strategy Name·Version, order limits |
| Change risk | Actual order environment·account·scale changes |
| Confirmation target | Default values, whether Required, Validation method |

### `execution_db.py`

| Item | Value |
|---|---|
| Responsibility | Provide DB Connection and Query Helpers |
| Input | DB settings, SQL, Parameters |
| Output | Row, Row List, Execute result |
| DB impact | Both Read·Write possible |
| Primary functions | `get_conn`, `fetch_one`, `fetch_all`, `execute_one` family |
| Change risk | Commit boundary, Cursor return, exception handling changes |
| Confirmation target | Whether the Helper commits internally and the Dict Row policy |
| Execution | Do not call without approval |

### `execution_repository.py`

| Item | Value |
|---|---|
| Responsibility | Central point for Execution DB Read·Write |
| Input | Plan·Order·Position·Decision·Check Payload |
| Output | DB Row, ID, Summary, Update result |
| Write targets | Plan, Order, Position, Decision link, Intraday Check |
| Read targets | Connector Request·Fill·Balance·Position Snapshot |
| Candidate query | Provide the Daily BUY candidate query order |
| Cash allocation | Query Position·Price·Open Order needed for Plan-level cumulative cash allocation |
| Terminal query | Read responsibility for CANCELED Orders and Terminal Chains |
| Primary contract | Unique Key, Upsert, Status, Connector Request link |
| Change risk | Duplicate orders, partial reflection, Position mismatch |
| Confirmation target | The actually modified functions and SQL, Join Cardinality, Commit·Rollback scope |
| Execution | Treat all calls as DB-impacting paths |

## 5. Container and Dependency

### `Dockerfile`

| Item | Value |
|---|---|
| Responsibility | Git SHA based Execution Container Image definition |
| Input | Build Context, Requirements, Runtime Source |
| Output | ECS or Local Container Image |
| Runtime scope | Root Runtime Source and `requirements.txt` |
| Excluded | Per `.dockerignore`, excludes `.devops` Build Scripts and Tokens·Secrets |
| Default CMD | `python daily_auto_buy_execute_run.py` (no `--execute`) |
| Change risk | Wrong Source Copy, missing Dependency, CMD change |
| Confirmation target | Base Image, Workdir, Copy paths, default CMD |
| Sensitive information | Prohibit recording Image URI·Digest·Registry values |

### CI and DevOps Assets

| File | Responsibility |
|---|---|
| `.github/workflows/execution-codebuild.yml` | main Push·`workflow_dispatch` Trigger, OIDC CodeBuild start·wait, Release control-plane call on main Push |
| `.devops/codebuild/buildspec.yml` | Compile·pytest·Ruff·Docker Build·Container Source Compile·Container Import/File Smoke, Build-only contract, optional ECR Push |
| `.devops/scripts/container-smoke.py` | Validate Runtime file·Import contract, prohibited paths, and the account placeholder environment variable |
| `.devops/scripts/deploy-execution.sh` | Release control-plane Promotion Script |
| `.dockerignore` | Exclude Token·`.devops`·`tests`·`docs` from the Image |
| `.gitignore` | Exclude `access_token.txt` and local artifacts from Git |
| `pytest.ini` | Test settings targeting `tests` |
| `tests/` | Cancellation·multi-candidate sequential cash allocation·MARKET BUY 110% Reserve·chain·Container contract tests |

Responsibility separation is as follows.

- CodeBuild has only the Build·Test·Container Smoke·ECR Artifact creation responsibility and does not change ECS·Step Functions operations.
- The GitHub Workflow Release control-plane can register an ECS Task Definition and change the State Machine Definition reference with a validated Artifact.
- The Release control-plane does not perform State Machine execution and `ecs:RunTask`.
- The Release control-plane does not perform Business orders and DB Writes.

### `.devops/scripts/deploy-execution.sh`

| Item | Value |
|---|---|
| Responsibility | The Release control-plane Script that performs the subsequent operational Promotion after main Push |
| Baseline discovery | Dynamically confirm the Execution Task Definition baseline from the operational State Machine Definition |
| Artifact resolve | Confirm the ECR Image Digest based on the Source SHA |
| New Revision | Clone the operational Task Definition and register with only the validated Image Digest replaced |
| Backup | Back up the State Machine Definition before the change |
| Activation Scope | Validate the target State Machine and Execution State references |
| Promotion | Switch the Execution reference of the related State Machines |
| Stale Guard | Block Promotion if the baseline changed |
| Rollback | Automatically restore to the Backup Definition on failure |
| After-check | Validate reference consistency after Promotion |
| Execution boundary | No State Machine execution·`ecs:RunTask`·order·DB Write |
| Sensitive information | Do not record ARN·Resource ID·Revision number in documentation |

### `requirements.txt`

| Item | Value |
|---|---|
| Responsibility | Declare the Python Runtime Dependency |
| Primary dependencies | `psycopg2-binary` and others |
| Output | Packages installed at Image Build |
| Change risk | Runtime compatibility, vulnerabilities, Image size |
| Confirmation target | Consistency between actual Imports and the list |
| Caution | An external-path Import Module may not be in the Package list |

### `create_execution_docker_files.py`

| Item | Value |
|---|---|
| Responsibility | Helper that generates the Dockerfile and Requirements |
| Input | The Templates and target paths inside the script |
| Output | Write the `Dockerfile`, `requirements.txt` files |
| Operating location | Development aid |
| DB impact | None |
| File impact | May overwrite existing Container files |
| Change risk | Loss of manual edits and regeneration of an outdated Template |
| Execution | Do not execute without approval and Diff confirmation |

## 6. Daily BUY Candidate Creation

### `daily_buy_execution_run.py`

| Item | Value |
|---|---|
| Responsibility | Daily BUY Execution candidate creation Entrypoint |
| AWS location | Paper Daily Step 8 candidate |
| Input | Latest Daily Run, BUY Signal, Account·Balance·Position |
| Processing | Plan query·creation, Signal conversion, Sizing, Order Upsert |
| Output | `strategy_execution_plan`, `strategy_execution_order` |
| External order | Does not mean Broker order completion at this stage |
| Primary risk | Wrong Source Run, duplicate candidates, misjudged empty candidate |
| Confirmation target | Latest Run selection, Business Date, Plan Summary |
| Execution | May write to DB, so do not execute without approval |

### `execution_daily_signal_builder.py`

| Item | Value |
|---|---|
| Responsibility | Convert Daily BUY Signal into Order Payload |
| Input | Signal, Current Holding, Latest Price, Sizing result |
| Output | Order structure and Validation Result·Order Snapshot |
| Cumulative cash | Preserve the candidate order and sequentially allocate remaining cash within the Plan |
| READY deduction | Deduct the required cash including Reserve of READY candidates from remaining cash |
| BLOCKED · 0 shares | Do not deduct remaining cash |
| Reuse prohibition | Do not reuse the initial available cash as-is for subsequent candidates |
| DB impact | None directly; uses Repository query Helpers |
| Primary contract | Source ID, Ticker, Side, Quantity, Reason |
| Change risk | Loss of Signal traceability, changes to quantity·price·cash allocation meaning |
| Confirmation target | Required Fields, Validation, candidate order, remaining-cash boundary |
| Caution | The Builder result does not mean an actual order success |

### `execution_buy_sizing.py`

| Item | Value |
|---|---|
| Responsibility | Compute the orderable quantity and required cash of a single BUY candidate |
| Input | Target Amount, Available Cash, Current Holding, Latest Price |
| Output | order_qty, estimated_order_amount, required_cash_amount, sizing_detail |
| MARKET Reserve | Apply 110% (`MARKET_BUY_CASH_RESERVE_RATIO`) to quantity·required cash |
| Effective price | Use 110% of `latest_price` in the quantity calculation |
| Amount separation | Separate the estimated order amount from the required cash including Reserve |
| DB impact | None directly |
| Responsibility boundary | Handles only single BUY candidate calculation; does not guarantee the Broker orderable amount |
| Multiple candidates | Confirm multi-candidate cumulative cash allocation in the Signal Builder flow |
| Change risk | Actual order quantity·cash boundary·Decimal·0-share·minimum amount handling |
| Confirmation target | Truncation, 0 Price, Cash shortage, existing holding |

## 7. Daily SELL Candidate Creation

### `daily_sell_execution_run.py`

| Item | Value |
|---|---|
| Responsibility | Convert Daily Position SELL Decision into Order candidates |
| AWS location | Paper Daily Step 9 candidate |
| Input | Latest Position Decision Run and SELL Row |
| Processing | Order creation·Upsert and Decision link |
| Output | `strategy_execution_order`, the Decision's Order ID |
| Primary risk | Duplicate Decision consumption, wrong Position link |
| Confirmation target | Run selection, Source ID, Position State, Quantity |
| Re-run | First confirm the existing link and existing Order |
| Execution | May write to DB, so do not execute without approval |

### `execution_daily_position_sell_builder.py`

| Item | Value |
|---|---|
| Responsibility | Convert SELL Decision into Order Payload |
| Input | Decision Row and Position link information |
| Output | Daily Position SELL Order structure |
| DB impact | None directly, or confirm per the call structure |
| Primary contract | Decision ID, Position State ID, Side, Quantity |
| Change risk | Selling a different Position and quantity errors |
| Confirmation target | Full·partial sell meaning and Source Payload preservation |

## 8. Auto Execute

### `daily_auto_sell_execute_run.py`

| Item | Value |
|---|---|
| Responsibility | Pass READY SELL Orders to the Connector SELL path |
| AWS location | Paper Daily Step 10 candidate |
| Input | Daily·Intraday SELL Order, latest Sellable Quantity |
| Processing | Validate execution targets, call Connector Helper, update status |
| Output | Connector Request link and Execution status |
| Position impact | May update status such as `SELL_ORDERED` |
| External impact | May lead to a Broker order request |
| Primary risk | Duplicate submission, quantity overflow, DB failure after external success |
| Confirmation target | Existing Request, Mode, Sellable Quantity, Retry |
| Execution | An automatic order path, so execution is prohibited |

### `daily_auto_buy_execute_run.py`

| Item | Value |
|---|---|
| Responsibility | Pass READY BUY Orders to the Connector BUY path |
| AWS location | Paper Daily Step 11 candidate |
| Input | Daily BUY Execution Order |
| Processing | Confirm the execution mode and order values, then call the Connector Helper |
| Output | Connector Request link and Execution status |
| External impact | May lead to a Broker order request |
| Primary risk | Duplicate submission, wrong account·environment·quantity |
| Confirmation target | Existing Request, Mode, Account, Retry |
| Execution | An automatic order path, so execution is prohibited |

### `execution_execute_order.py`

| Item | Value |
|---|---|
| Responsibility | Single Execution Order execution Entrypoint |
| Input | Order ID, Execution Mode, execution options |
| Processing | Validation, Mode storage, may call Connector BUY·SELL |
| Output | Order status and Connector Request link |
| Primary modes | `DRY_RUN`, `MANUAL_TEST`, `PAPER_STRATEGY`, `LIVE_STRATEGY` |
| DB impact | Must confirm Write possibility even without `--execute` |
| External impact | An actual order request depending on the options |
| Primary risk | Live misexecution, duplicate submission, Commit mismatch |
| Confirmation target | `--execute`, Live Confirm, Environment validation |
| Execution | All modes prohibited without explicit approval |

## 9. SELL Fill and Position Reflection

### `execution_sync_sell_fill.py`

| Item | Value |
|---|---|
| Responsibility | Reflect SELL Connector Fill into Execution and Position |
| AWS location | Paper Daily Step 14 candidate |
| Input | SELL Order, Connector Request, Fill |
| Output | Order fill status and Position remaining quantity |
| Write targets | `strategy_execution_order`, `strategy_position_state` |
| Primary contract | Cumulative Fill, partial fill, Remaining Quantity |
| Status impact | Completion·termination candidate on full fill |
| Primary risk | Fill duplicate aggregation, Position duplicate deduction |
| Confirmation target | Fill Key, cumulative quantity, CLOSED condition, Transaction |
| Execution | May change Position quantity, so execution is prohibited |

Do not assert the entire Order is `FILLED` merely because one SELL Fill exists.
Compare the actual requested quantity and cumulative filled quantity.

## 10. BUY Fill and Position Reflection

### `execution_sync_buy_fill.py`

| Item | Value |
|---|---|
| Responsibility | Reflect BUY Connector Fill and cancellation status into the Execution Order Terminal |
| AWS location | Paper Daily Step 15 candidate |
| Input | BUY Order, Connector Request, Fill |
| Output | FILLED·CANCELED Terminal status and Summary |
| Write targets | `strategy_execution_order` |
| Terminal classification | Handle FILLED and CANCELED as separate Terminals |
| Cancellation handling | Normal CANCELED + 0 fills is a normal termination |
| Failure aggregation | Exclude normal CANCELED from the failure count |
| Summary | Separate filled·canceled·terminal·failed |
| Primary risk | Cancellation status misjudgment, partial fill premature completion, Transaction Rollback scope |
| Confirmation target | Request final status, Fill Scope, Quantity, Average Price |
| Execution | May write to DB, so execution is prohibited |

### `execution_sync_buy_position.py`

| Item | Value |
|---|---|
| Responsibility | Reflect FILLED BUY Fill into the strategy Position |
| AWS location | Paper Daily Step 16 candidate |
| Input | FILLED BUY Order and existing OPEN Position |
| Target | Only FILLED BUY is a target, CANCELED is excluded |
| Output | New Position or additional-buy merge |
| Write targets | `strategy_position_state`, Order Sync record |
| Tracing | `source_buy_execution_order_id`, Connector Request·Fill tracing |
| Success judgment | Separate a 0-target success from an actual creation success |
| Primary contract | Prevent reprocessing the same Fill and average price calculation |
| Primary risk | Duplicate Position, double quantity reflection |
| Confirmation target | Existing OPEN selection, Merge formula, re-run duplicate prevention |
| Execution | May create·change Position, so execution is prohibited |

### `execution_validate_order_chain.py`

| Item | Value |
|---|---|
| Responsibility | Validator for the Execution Order → Connector Request → Fill → Position chain |
| AWS location | Post-Step 16 P0 validation candidate |
| Input | Plan·Order·Connector Request·Fill·Position |
| Output | Target count·error count and a non-zero exit |
| Type | Read-only, no DB Insert·Update·Delete |
| FILLED BUY | Connector Fill and Position trace required |
| CANCELED BUY | With a valid cancellation chain, normal Terminal without Fill·Position |
| CLI options | `--run-date`, `--plan-id`, `--allow-no-target` |
| Primary risk | Status misjudgment and False Positive |
| Confirmation target | Request final status, Fill total, Position trace |
| Execution | Read-only but a DB connection, so do not execute without approval |

## 11. Position Context and SELL Evaluation

### `execution_position_loader.py`

| Item | Value |
|---|---|
| Responsibility | Compose the strategy OPEN Position Context |
| Input | `strategy_position_state`, Connector Position Snapshot |
| Output | Position Context for the SELL Evaluator |
| DB impact | Read |
| Primary contract | Distinguish Strategy Quantity and Broker Quantity |
| Primary risk | Wrong latest Snapshot selection, Join duplication |
| Confirmation target | Latest basis, Account·Ticker Join, Missing Snapshot |
| Execution | Confirm the `main()` and Side Effects at the bottom of the file; execution is prohibited |

### `execution_sell_evaluator.py`

| Item | Value |
|---|---|
| Responsibility | Generate the SELL·HOLD evaluation Payload of a Position |
| Input | Position Context, Stock Feature, Market Feature |
| Output | Decision, Reason, Metric Payload |
| DB impact | None directly, or confirm the call structure |
| Primary contract | Evaluation reference date and Feature Date |
| Change risk | Changes to the actual sell candidate result |
| Confirmation target | Hard Stop, Missing Feature, Look-ahead possibility |
| Caution | Do not assume it is the same implementation as the StrategyDecision Daily Position decision |

### `execution_sell_builder.py`

| Item | Value |
|---|---|
| Responsibility | Convert an OPEN Position evaluation into a POSITION_SELL Order |
| Input | Position and Sell Evaluation |
| Output | `strategy_execution_order` and Position evaluation result |
| DB impact | Update·Upsert possible |
| Primary contract | Position ID, Source Type, Quantity, Reason |
| Primary risk | Duplicate SELL candidates and Position status contamination |
| Confirmation target | Existing Order, Evaluation Update, Transaction |
| Execution | May write to DB, so do not execute without approval |

## 12. Intraday Monitor

### `daily_intraday_position_monitor_run.py`

| Item | Value |
|---|---|
| Responsibility | Check intraday OPEN Positions and create Stop Sell candidates |
| Operating location | Intraday 10-minute Intraday Evaluate candidate |
| Input | OPEN Position, Connector Position, Quote, Feature |
| Processing | Query Current Price, evaluate Stop conditions, store Check |
| Default output | `strategy_intraday_position_check` |
| Optional output | `INTRADAY_STOP_SELL` Execution Order |
| External impact | May call the Connector Quote API |
| Primary options | `--create-order` and others; confirm in the actual code |
| Primary risk | Repeated Order creation, Quote errors, misjudged trading time |
| Confirmation target | Normal Check storage, Hard Stop, Approval boundary |
| Execution | May call external APIs and write to DB, so execution is prohibited |

Storing the check result and creating a Stop Sell Order are separate impacts.
Do not represent check success as order creation success or Broker order submission.

## 13. Backtest-Based Execution Candidates

### `backtest_execution_run.py`

| Item | Value |
|---|---|
| Responsibility | Convert Backtest results into Execution candidates |
| Input | Backtest Run·Daily·Trade Log |
| Output | Execution Plan·Order candidates |
| DB impact | Plan·Order Write possible |
| Primary contract | Research Source Run and trade result tracing |
| Primary risk | Mixing Backtest results into Daily operational candidates |
| Confirmation target | Run selection, Trade Side, Quantity, Business Date |
| Execution | May write to DB, so do not execute without approval |

### `execution_builder.py`

| Item | Value |
|---|---|
| Responsibility | Convert Backtest Trade into Order Payload |
| Input | BUY·SELL Trade and Position·Price Context |
| Output | Backtest Source Execution Order structure |
| DB impact | None directly, or confirm the call structure |
| Primary contract | Research Source tracing and Daily path separation |
| Change risk | Changes to Backtest candidate meaning and quantity |
| Confirmation target | Validation, Price, Source Type, Position Link |

### `execution_build_candidates.py`

| Item | Value |
|---|---|
| Responsibility | Standalone or past candidate creation path |
| Input | Its own DB Query and settings |
| Output | Execution candidate Upsert possible |
| DB impact | Read·Write |
| Current classification | A preservation target with legacy possibility |
| Primary risk | May use different Keys·Status than the common Repository |
| Confirmation target | Import references, Wrapper, actual operational calls |
| Deletion criterion | Do not delete before statically proving it is unused |
| Execution | Has standalone DB Write possibility, so execution is prohibited |

Do not assert it is a complete Legacy or deletion target by the filename and structure alone.

## 14. Data Contracts

### 14.1 Primary Inputs

| Input | Consuming file |
|---|---|
| Daily BUY Signal | Daily BUY Entrypoint and Signal Builder |
| Daily Position SELL Decision | Daily SELL Entrypoint and SELL Builder |
| Backtest Run·Trade | Backtest Entrypoint and Builder |
| Connector Account | BUY·SELL execution Context |
| Connector Balance | BUY Sizing |
| Connector Position | SELL quantity and Position Context |
| Connector Request | Fill Sync |
| Connector Fill | BUY·SELL Fill Sync |
| Stock·Market Feature | SELL Evaluator and Intraday |

### 14.2 Primary Outputs

| Output | Creating·updating file |
|---|---|
| `strategy_execution_plan` | Daily BUY·Backtest·Repository |
| `strategy_execution_order` | Daily BUY·SELL·Intraday·Backtest·Auto Execute·Sync |
| `strategy_position_state` | SELL Fill·BUY Position·Auto SELL |
| `strategy_daily_position_decision.execution_order_id` | Daily SELL |
| `strategy_intraday_position_check` | Intraday Monitor |

Confirm the actual Table·Column·Schema in the code.

## 15. Plan Contract

| Item | Confirm on change |
|---|---|
| Source Type | Distinguish Daily Signal·Position Decision·Backtest |
| Source Run | Correct Run ID and traceability |
| Business Date | Execution target trade date |
| Environment | Paper·Live separation |
| Strategy | Name and Version |
| Status | Meaning of in-progress·complete·failed |
| Summary | Candidate·Skip·Error aggregation |
| No Target | Distinguish a normal empty candidate from a missing input |
| Re-run | Reuse existing Plan or new-creation policy |

Do not interpret Plan creation success as full success of all subordinate Orders.

## 16. Order Contract

| Item | Confirm on change |
|---|---|
| Plan ID | Link to the higher Plan |
| Source ID | Trace the source Signal·Decision·Trade |
| Ticker·Side | Order target and direction |
| Quantity | Distinguish requested quantity and filled quantity |
| Execution Mode | Dry Run·Manual·Paper·Live |
| Connector Request | Link to the external order request |
| Status | Candidate·request·fill·failure status |
| Payload | Preserve Source and Sync evidence |
| Unique Key | Prevent duplicate candidates and submissions |
| Retry | Recovery for external success·DB failure |

Confirm the actual status strings in the implementation.
Do not assert conceptual statuses as the exact values in the code.

## 17. Fill Contract

| Item | Confirm on change |
|---|---|
| Request Scope | Select the correct Connector Request |
| Fill Scope | Order number·Ticker·Side·trade date |
| Duplicate | Prevent re-aggregation of the same Fill |
| Quantity | Compare cumulative fill and requested quantity |
| Average Price | Quantity-weighted average |
| Partial Fill | Partial fill status and re-run |
| Zero Fill | Distinguish a normal unfilled state from a missing link |
| Transaction | Atomicity of Order and Position reflection |

## 18. Position Contract

| Item | Confirm on change |
|---|---|
| New BUY | Create OPEN Position |
| Additional BUY | Existing OPEN merge criterion |
| Partial SELL | Deduct only the filled quantity |
| Full SELL | Remaining quantity 0 and CLOSED transition |
| Re-run | Prohibit duplicate reflection of the same Fill |
| Strategy Quantity | Remaining quantity based on Execution |
| Broker Quantity | Based on the Connector Snapshot |
| SELL_ORDERED | Ordering status and reselection policy |

The strategy Position and the Broker Position are different data contracts.

## 19. DB Impact Map

### 19.1 Tables with High Write Likelihood

| Table | Primary file |
|---|---|
| `strategy_execution_plan` | Daily BUY, Backtest, Repository |
| `strategy_execution_order` | Candidate creation, Auto Execute, Fill Sync, Intraday |
| `strategy_position_state` | Auto SELL, SELL Fill, BUY Position |
| `strategy_daily_position_decision` | Daily SELL link |
| `strategy_intraday_position_check` | Intraday Monitor |

### 19.2 Connector Read Targets

| Table | Primary file |
|---|---|
| `connector_order_request` | Fill Sync and Order link |
| `connector_fill` | BUY·SELL Fill aggregation |
| `connector_account` | Order account Context |
| `connector_balance_snapshot` | BUY Sizing |
| `connector_position_snapshot` | SELL quantity and Position Context |

### 19.3 Confirm Before DB Changes

| Item | Confirmation content |
|---|---|
| Schema | Search Path and same-name Table |
| Unique Key | Actual Constraint and Upsert Target |
| Join | 1:N expansion and duplicate Rows |
| Latest | Date·Timestamp·ID basis |
| Transaction | Repository internal and caller responsibility |
| Commit | Location before and after the external order call |
| Rollback | Partial storage and retry |
| DDL | Whether it runs automatically during Import·Entrypoint |

## 20. External Dependency Relationships

### MarketConnector

| Item | Value |
|---|---|
| Execution use | BUY·SELL Helper, Quote, Connector Table |
| Responsibility boundary | Broker·KIS API and Token are MarketConnector responsibilities |
| Orderable amount | Computing the actual Broker orderable amount is a MarketConnector responsibility |
| Modification scope | Prohibit modifying the external repository based on an Execution request alone |
| Primary risk | Execution DB link failure after an external success |
| Confirmation target | Import path, function Signature, return contract |

### StrategyDecision

| Item | Value |
|---|---|
| Execution use | Daily BUY Signal and Position SELL Decision |
| Responsibility boundary | The BUY·SELL decision algorithm is a Decision responsibility |
| Primary risk | Wrong Decision Run·Row selection |
| Confirmation target | Source ID, Business Date, Status |

### StrategyResearch

| Item | Value |
|---|---|
| Execution use | Backtest Run·Daily·Trade results |
| Responsibility boundary | Backtest calculation and Report are Research responsibilities |
| Primary risk | Daily operational promotion of Research results |
| Confirmation target | Source Type and Run tracing |

### Preprocessor·Crawler

| Item | Value |
|---|---|
| Execution use | Feature and trade-day-related input |
| Responsibility boundary | Raw collection and Feature generation are external responsibilities |
| Primary risk | Outdated Feature·Look-ahead·holiday misjudgment |
| Confirmation target | Feature Date and Business Date |

## 21. AWS and Operational Wrappers

The Execution Entry Points currently found at the Root may be used as ECS RunTask or
Container Command Override targets.

| Operating segment | Entry Point |
|---|---|
| Daily BUY candidate | `daily_buy_execution_run.py` |
| Daily SELL candidate | `daily_sell_execution_run.py` |
| Auto SELL | `daily_auto_sell_execute_run.py --execute` |
| Auto BUY | `daily_auto_buy_execute_run.py --execute` |
| SELL Fill | `execution_sync_sell_fill.py` |
| BUY Fill | `execution_sync_buy_fill.py` |
| BUY Position | `execution_sync_buy_position.py` |
| Intraday | `daily_intraday_position_monitor_run.py` |

Confirm the actual Cluster, Task Definition, Image URI, Command Override, and Log Group
in the external operational definition.

Use only placeholders for operational identifiers, as follows.

```text
<EXECUTION_ECS_CLUSTER>
<EXECUTION_TASK_DEFINITION_ARN>
<EXECUTION_ECR_IMAGE_URI>
<EXECUTION_LOG_GROUP>
<COMMAND_ID>
```

The State Machine Definition itself is not a Source file of this Repository.
The Catalog does not make it a file item and describes it only as an operational reference.
The current Task Definition reference change and Rollback of Execution-related States are performed automatically
on main Push by the `.devops/scripts/deploy-execution.sh` Release control-plane.
This automatic Promotion changes only the Definition reference and does not perform State Machine execution·orders·DB Write.

## 22. Sensitive Information Candidates

### `access_token.txt`

| Item | Value |
|---|---|
| Classification | A sensitive-information candidate local file |
| Possible content | Connector·API authentication related values |
| Reading | Do not read or quote the value even for work purposes |
| Documentation | Record only the file existence and risk |
| Git | Confirm tracking status and Ignore policy separately |
| Handling | Deletion·move·modification requires user approval |

The following values are also not recorded verbatim in documentation.

- Password
- Token and API Key
- Account Number
- Webhook URL
- DB Host and Credential
- Broker Order Number
- Connector Request ID
- ARN·Image URI·Subnet·Security Group
- One-time Command ID and execution logs

## 23. Items Excluded from the Current Documentation

Date-specific `docs/worklog/*.md` are excluded from the current file structure and Catalog list.

Past Worklog-creation facts are preserved only in `CHANGELOG.md`.
Do not create new Worklog files.

The following artifacts are also excluded from the Catalog.

- `__pycache__/`
- `.pytest_cache/`
- `.gradle/`
- `target/`
- `build/`
- IDE temporary files
- Coverage and Compile artifacts
- One-time SQL·JSON·Log Dumps
- Secret or Token verbatim file content

## 24. Cleanup Candidate Judgment Criteria

Before cleaning up or deleting a file, confirm the following items.

| Item | Confirmation content |
|---|---|
| Import | Direct·dynamic Import by other Python files |
| Entrypoint | `__main__` and CLI execution possibility |
| Wrapper | PowerShell·Shell·Batch·Lambda calls |
| Container | Docker CMD and Command Override |
| AWS | ECS·Step Functions·SSM references |
| External MS | Path·Module references from other repositories |
| DB | Standalone Table·Status·Output use |
| Documentation | Operational procedure and Runbook references |
| Git | Recent changes and the user's uncommitted work |

If the unused evidence is insufficient, do not delete it and mark it only as a preservation or cleanup candidate.

## 25. File Change Impact Map

| Change target | Files to confirm together |
|---|---|
| BUY Signal input | Daily BUY Entrypoint, Signal Builder, Repository |
| BUY Sizing | Signal Builder, Repository, Config, Tests, README |
| BUY Fill CANCELED handling | BUY Fill Sync, Order Chain Validator, BUY Position Sync |
| Order Chain Validator | Repository, Connector Request·Fill, Position State |
| SELL Decision input | Daily SELL Entrypoint, SELL Builder, Repository |
| Auto Execute | Auto BUY·SELL, Execute Order, Connector contract |
| Order Status | Repository, Auto Execute, Fill Sync |
| Connector Request link | Execute Order, Auto Execute, Fill Sync |
| BUY Fill | BUY Fill Sync, BUY Position Sync |
| SELL Fill | SELL Fill Sync, Position State |
| Position State | Loader, SELL Builder, Intraday, Sync |
| Intraday | Loader, Evaluator, Builder, Monitor |
| Backtest candidate | Backtest Entrypoint, Builder, Research contract |
| DB Config | DB Helper, Repository, Container settings |
| Docker·CI | Workflow, Buildspec, Dockerfile, Ignore files, Tests |
| State Machine Revision change | Execution Task Definition reference and Rollback Definition |
| File addition·deletion | README structure and Source Catalog |
| Primary contract change | AGENTS, README, CHANGELOG |

## 26. Catalog Update Conditions

When the following change, confirm this document in the same task.

- File addition·deletion·rename
- Entrypoint and CLI option change
- File responsibility or call-order change
- Input·output Payload change
- Plan·Order·Fill·Position status change
- Table·Column·Schema·Unique Key change
- Upsert and Transaction policy change
- Connector Helper and return contract change
- BUY Sizing and SELL quantity policy change
- Partial Fill and Retry handling change
- Intraday Check or Stop Order policy change
- Whether Backtest candidates are used operationally
- Docker·Requirements·ECS Command change
- Sensitive-information file and configuration method change
- Documentation structure and Worklog policy change

Do not mechanically update all unrelated files
merely for a simple typo fix or explanatory-sentence cleanup.

## 27. Related Documents

- [AGENTS.md](../AGENTS.md)
- [README.md](../README.md)
- [CHANGELOG.md](../CHANGELOG.md)
