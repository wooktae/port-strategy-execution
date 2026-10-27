# AGENTS.md - port_strategy_execution

## 1. Highest-Priority Documentation Readability Rules

These rules take priority in all Markdown documentation authoring and modification for `port_strategy_execution`.

- New standalone summary tables use two columns by default.
- The default columns are `Item / Value`, and depending on context `File / Role`, `Stage / Responsibility`, `Status / Meaning` may be used.
- When adding a row to an existing table, preserve its existing column structure.
- Keep table cells to no more than two sentences where possible.
- Do not place three or more facts in a long sentence within one cell.
- Split three or more facts into multiple rows or a link to a detailed document.
- New table cells do not exceed 300 characters.
- A single line does not exceed 500 characters.
- Do not paste long file lists, complete SQL, complete logs, and complete DB results into the document body.
- Do not repeat the same fact at length across `README.md`, `CHANGELOG.md`, and `docs/source-file-catalog.md`.
- Do not create duplicate sections that differ only in title.
- Do not mix the current state and past change history in one paragraph.
- Preserve code notation for unique file names, function names, table names, column names, status values, and execution options.
- Save Korean Markdown as UTF-8 without BOM.
- Do not create tab characters and trailing whitespace.

## 2. Rule Priority

| Scope | Priority basis |
|---|---|
| User's latest explicit request | Highest work instruction |
| Workspace-common safety·work method | Latest rules in `.kiro/AGENTS.md` |
| Execution responsibility·data·status contract | This `AGENTS.md` |
| Direct conflict | The more restrictive and safer rule |

- Do not ignore the common rules in `.kiro/AGENTS.md`.
- This file complements the responsibilities and risks specific to `port_strategy_execution`.
- When the user specifies the target files and scope, do not exceed that scope.
- If rules conflict or the implementation fact is unclear, do not execute; report the static confirmation result and its limitations.

## 3. Project Role

`port_strategy_execution` is a Python MS that converts strategy decision results into execution-layer plans and order candidates, and connects order requests, fills, and strategy position state.

The primary responsibilities are as follows.

| Area | Responsibility |
|---|---|
| Daily BUY Execution | Convert Daily BUY signal into BUY execution order candidates |
| Daily SELL Execution | Convert Daily position SELL decision into SELL execution order candidates |
| Execution Plan | Create `strategy_execution_plan` and manage summary status |
| Execution Order | Create, query, and update status of `strategy_execution_order` |
| Auto Execute | Pass approved READY BUY·SELL orders to the connector call path |
| Fill Sync | Reflect fill status based on `connector_order_request`, `connector_fill` |
| Position Sync | Create OPEN positions from BUY fills and deduct quantity from SELL fills |
| Intraday Monitor | Check OPEN positions and create stop sell candidates |
| Backtest Candidate | Maintain the path that can convert Backtest results into separate execution candidates |

The current repository is centered on root-level executable Python scripts rather than a package layer.

## 4. Responsibility Boundary

Do not mix the areas Execution owns directly with the responsibilities of other MS.

| Area | Owner |
|---|---|
| Source data collection | Crawler |
| Raw preprocessing and Feature generation | Preprocessor |
| Daily BUY signal decision | StrategyDecision |
| Daily Position HOLD·SELL·SKIP decision | StrategyDecision |
| Backtest and Research Report | StrategyResearch |
| Connection of Execution Plan·Order with the strategy Position | StrategyExecution |
| Broker·KIS API internal implementation and Token | MarketConnector |
| Approval UI and screen display | port-view |
| Full Daily Orchestration | Scheduler and Step Functions |

- Execution does not own the BUY·SELL decision algorithm itself.
- Execution does not duplicate the MarketConnector internal order API implementation.
- Execution does not own the full Step Functions definition or Scheduler operation.
- The internal implementation of other MS is documented only at the input/output contract level required by Execution.

## 5. Work Scope

- The default work scope is the `port_strategy_execution` root and its subordinate files.
- Files outside the root are used only as read-only for dependency confirmation.
- Do not modify other MS files without a user request.
- For a documentation work request, modify only the target Markdown files.
- For a code work request, modify only the specified Python·configuration·test files.
- Do not create a full repository scan, sub-agent, orchestrator, or new scanner.
- Do not create or assume nonexistent files, tests, wrappers, and tables for documentation convenience.
- Do not treat generated reports, dumps, tokens, caches, and temporary files as operational sources.

## 6. Static Confirmation Before Starting Work

Before modifying, read only the necessary files directly, in the following order.

1. User-specified target files
2. This `AGENTS.md`
3. The entrypoints and helpers referenced by the target files
4. Related DB read·write and connector call points
5. Related tests and execution wrappers
6. `README.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` if affected by documentation changes

During static confirmation, distinguish the following.

| Category | Judgment basis |
|---|---|
| Current implementation | Confirmed directly in the actual code |
| Operational fact | Confirmed by repository or user-provided evidence |
| Design principle | Rules stated in AGENTS and documents |
| Unverified | Content lacking code·operational evidence |
| No assumptions | Do not assert responsibility·status·table by name alone |

## 7. Default Execution-Prohibition Principle

Do not perform the following without the user's explicit approval and confirmation of the target environment.

- Create an execution plan or execution order
- Execute an automatic BUY order
- Execute an automatic SELL order
- Call the connector·broker·KIS order API
- Query fills and fill sync
- Position sync and position state changes
- Intraday quote query and monitor execution
- Create intraday stop sell orders
- DB DDL·DML and commit
- External API calls and crawling
- AWS CLI·SDK calls
- ECS RunTask, SSM RunCommand, Step Functions execution
- EventBridge Scheduler changes
- Slack or webhook calls
- Git commit, push, reset, restore, and checkout

Python import may also cause a DB connection or execution side effect at module import, so it is not performed during documentation review.

## 8. Execution-Prohibited Entry Points

The following files may cause DB writes, order calls, and fill·position changes, so they are not executed without explicit approval.

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

- Do not judge options such as `--execute`, `--create-order`, `--confirm-live` as safe by name alone.
- A path that looks like a dry-run may still store the execution mode or validation result in the DB, so confirm the actual code.
- Do not assume a loader·helper with `if __name__ == "__main__":` is a simple import target.

## 9. Primary File Responsibilities

### 9.1 Daily BUY

| File | Responsibility to confirm |
|---|---|
| `daily_buy_execution_run.py` | Query the latest Daily Run and BUY signal, and the Plan·Order creation flow |
| `execution_daily_signal_builder.py` | Convert BUY signal into execution order payload |
| `execution_buy_sizing.py` | Compute order quantity based on cash·holding·target amount |
| `execution_repository.py` | Plan·Order upsert and summary update |

### 9.2 Daily SELL

| File | Responsibility to confirm |
|---|---|
| `daily_sell_execution_run.py` | Query the latest Position Decision Run and SELL decision |
| `execution_daily_position_sell_builder.py` | Convert SELL decision into execution order payload |
| `execution_repository.py` | Store Order and link the decision row |

### 9.3 Auto Execute

| File | Responsibility to confirm |
|---|---|
| `daily_auto_buy_execute_run.py` | Query READY BUY and the connector BUY call path |
| `daily_auto_sell_execute_run.py` | Query READY SELL, confirm sellable quantity, and call connector SELL |
| `execution_execute_order.py` | Single Order execution mode and live confirmation boundary |

### 9.4 Fill·Position Sync

| File | Responsibility to confirm |
|---|---|
| `execution_sync_buy_fill.py` | Aggregate BUY fills and reflect execution order status |
| `execution_sync_sell_fill.py` | Aggregate SELL fills and reflect remaining quantity·status |
| `execution_sync_buy_position.py` | Create or merge OPEN position based on FILLED BUY |

### 9.5 Intraday

| File | Responsibility to confirm |
|---|---|
| `execution_position_loader.py` | Combine strategy OPEN position with connector snapshot |
| `execution_sell_evaluator.py` | Evaluate Position·Stock Feature·Market Feature |
| `execution_sell_builder.py` | Create POSITION_SELL execution order candidates |
| `daily_intraday_position_monitor_run.py` | Store check results and create hard stop order candidates |

### 9.6 Common DB·Config

| File | Responsibility to confirm |
|---|---|
| `execution_repository.py` | Central point for Execution DB read·write |
| `execution_db.py` | Connection and fetch·execute helper |
| `db_config.py` | DB environment variables and search path settings |
| `execution_config.py` | Account·broker·environment·strategy·sizing settings |

## 10. Daily Execution Flow Contract

Do not confuse the following stages in documents and code.

| Stage | Execution perspective |
|---|---|
| Step 8 | Daily BUY execution order candidate creation |
| Step 9 | Daily SELL execution order candidate creation |
| Step 10 | READY SELL auto execute path |
| Step 11 | READY BUY auto execute path |
| Step 12~13 | MarketConnector order submission·query segment |
| Step 14 | SELL fill sync |
| Step 15 | BUY fill sync |
| Step 16 | BUY position sync |
| Step 17 | MarketConnector balance refresh segment |

- Confirm the actual Step numbers and calling files against the orchestration definition or operational evidence.
- Do not finalize the full state machine order by looking at Execution internal files alone.
- Do not extend the internal implementation of Step 12~13 and Step 17 into Execution responsibility.
- Do not merge candidate creation success, order submission success, fill success, and position sync success into one success state.

## 11. Execution Plan Contract

When changing `strategy_execution_plan`, confirm the following.

- plan source and source run identifiers
- business date or trade date
- strategy name and version
- plan status
- order count and summary aggregation
- re-run policy for the same source
- create-or-get or upsert criterion
- empty-candidate cycle handling
- plan status when some orders fail
- the point at which final completion is judged

Use only the Plan status strings and unique keys confirmed in the code.

## 12. Execution Order Contract

When changing `strategy_execution_order`, confirm the following.

- side and order type
- source type and source row identifier
- ticker and order quantity
- price policy such as limit·market
- execution mode
- status transition
- connector order request link
- request quantity and filled quantity
- average fill price
- error·reason payload
- idempotency criterion
- retryable status
- final status and reprocessing policy

- Confirm status values such as `READY`, `REQUESTED`, `ACCEPTED`, `FILLED`, `FAILED` against the actual code and DB contract.
- Do not add nonexistent status values for documentation convenience.
- Maintain the unique key and upsert criteria so the same source row does not create duplicate orders.
- Do not arbitrarily create a path that resubmits an order whose connector request is already linked.

### 12.1 Order Chain Validator Contract

`execution_validate_order_chain.py` is a read-only validation and adheres to the following.

- Do not judge by the Execution Order status alone.
- Confirm the Connector Request final status.
- Confirm the Fill cumulative quantity.
- Confirm the Position trace of a FILLED BUY.
- A normal CANCELED chain allows the absence of Fill·Position.
- Maintain that `--allow-no-target` is not an option that hides an actual Target error.
- Validator success confirms the target count and error count together.

## 13. Order Submission Safety Contract

When modifying the Auto BUY·SELL and single Order execution paths, always confirm the following.

| Item | Confirmation criterion |
|---|---|
| Target status | The actually submittable execution order status |
| Execution mode | `DRY_RUN`, `MANUAL_TEST`, `PAPER_STRATEGY`, `LIVE_STRATEGY` |
| Approval boundary | User·operator approval or an orchestration gate |
| Duplicate submission | Whether an existing connector request and broker order exist |
| Quantity | requested quantity and orderable quantity |
| Environment | local·paper·live separation |
| Failure handling | DB status, rollback, retry, and exit code |

- Do not weaken the confirmation conditions of the Live path.
- Do not arbitrarily change the `--execute` default and whether it is specified.
- Confirm whether the DB commits before the connector helper call and the status recording order after the call.
- Consider the possibility of a local DB write failure after an external order success.
- Do not conclude the broker order was not submitted based on the local DB status alone.
- Confirm whether a re-call on timeout and exception leads to a duplicate order.

## 14. BUY Sizing Contract

When modifying `execution_buy_sizing.py` and the BUY builder, confirm the following.

- available cash
- current holding quantity and valuation
- target amount or target weight
- maximum order amount ratio
- minimum order amount
- reference price
- integer quantity rounding
- 0-share and below-minimum-amount handling
- cash allocation order across multiple BUY candidates
- handling of an existing OPEN position for the same ticker
- account snapshot freshness

Sizing calculation does not assume the unit, rounding, and price point.

For multi-candidate cumulative available-cash allocation, adhere to the following.

- Multiple BUY candidates are computed based on cumulative available cash within one Plan.
- Explicitly preserve the candidate processing order.
- Only READY orders deduct remaining cash.
- BLOCKED·SKIPPED·0-share candidates do not deduct cash.
- Do not reuse the initial available cash for subsequent candidate calculations.
- Confirm the units of the market-order margin and the estimated order amount.
- Distinguish the single-ticker Sizing function from the Plan-level cumulative allocation responsibility.
- In tests, validate candidate order, READY·BLOCKED mixtures, and cash boundary values.

## 15. SELL Quantity Contract

When creating and submitting a SELL order, confirm the following.

- strategy position remaining quantity
- holding quantity in the connector position snapshot
- sellable quantity
- existing SELL_ORDERED or unfilled orders
- partial fill cumulative quantity
- duplicate SELL prevention criterion
- full·partial sell policy
- 0-share and negative prevention
- position status transition

When the strategy position quantity and broker snapshot quantity differ, do not arbitrarily choose one as correct.

## 16. Fill Sync Contract

When changing BUY·SELL fill sync, confirm the following.

| Item | Confirmation criterion |
|---|---|
| Source request | `connector_order_request` link basis |
| Fill source | `connector_fill` aggregation basis |
| Duplicate Fill | fill unique key and deduplication |
| Partial fill | Compare requested quantity and cumulative filled quantity |
| Average price | weighted average calculation basis |
| Final status | FILLED judgment condition |
| No fill | Maintain status or a separate status transition |
| Re-run | Prevent re-reflection of the same fill |

- Do not assert full FILLED by the existence of a fill row alone.
- Do not treat a partial fill as a full fill.
- If cancellation·rejection·correction states exist, confirm the actual connector contract.
- Do not arbitrarily merge or split the transaction boundaries of fill sync and position sync.

When handling a CANCELED canceled order, adhere to the following.

- CANCELED is not the same status as a failure.
- Confirm the valid cancellation request and the original order's final status together.
- Distinguish a normal cancellation with 0 fills from a missing data link.
- A CANCELED order may be excluded from the failure aggregation, but do not treat an unfounded status as a success.
- In the Summary, separate FILLED·CANCELED·Terminal·Failed.
- Confirm the Transaction boundary so that a single canceled order does not roll back the entire Transaction after some Orders succeed.

## 17. Position State Contract

When changing `strategy_position_state`, maintain the following.

- Do not finalize an OPEN position before the BUY fill.
- Confirm the merge criterion for an existing OPEN row of the same ticker and strategy.
- Confirm the calculation of quantity, remaining quantity, and average entry price.
- Distinguish the SELL order submission status from the SELL fill completion status.
- A partial SELL deducts only the remaining quantity.
- Consider the CLOSED transition only under the condition that remaining quantity becomes 0.
- Do not allow negative remaining quantity.
- Preserve the link between execution order and source decision.
- Ensure a duplicate sync does not repeatedly increase·deduct quantity.

When reflecting BUY fills and cancellations, adhere to the following.

- Do not create a Position for a CANCELED BUY.
- A FILLED BUY is treated as a Validator failure if it has no Position Trace.
- Confirm the order of the Step 15 FILLED Commit and the Step 16 target query.
- Do not represent a `target_count=0` success as a Position creation success.
- During Position Sync validation, confirm the target·created·failed counts and the Source Order·Request·Fill links.

## 18. Intraday Monitor Contract

When changing the intraday monitor and stop sell candidates, confirm the following.

- OPEN position query criterion
- latest connector position snapshot selection criterion
- latest stock feature and market feature reference date
- quote provider and quote timestamp
- normal check result storage policy
- handling of anomalous·missing data
- hard stop condition
- HOLD·SELL result and reason
- whether `--create-order` is specified
- prevention of duplicate orders for the same position·check time
- separation of the approval gate from actual order submission

- Distinguish storing the check result and creating an order as different impacts.
- Do not arbitrarily revert the current policy of storing normal results in `strategy_intraday_position_check`.
- Do not represent intraday stop order creation success as broker order success.

## 19. Backtest-Based Candidate Contract

`backtest_execution_run.py`, `execution_builder.py`, `execution_build_candidates.py` are treated as a separate line from the Daily operational path.

- Confirm the actual input table and run selection criterion.
- Do not represent backtest BUY·SELL rows as Daily signals or Daily position decisions.
- Do not mix the source type of operational Daily plans and backtest plans.
- Confirm whether legacy or standalone candidate creation files are current operational entrypoints.
- Do not classify as a deletion candidate by the filename alone.

## 20. DB Contract

Per the current documentation, the primary write targets are as follows.

- `strategy_execution_plan`
- `strategy_execution_order`
- `strategy_position_state`
- `strategy_daily_position_decision`
- `strategy_intraday_position_check`

The primary connector read targets are as follows.

- `connector_order_request`
- `connector_fill`
- `connector_account`
- `connector_balance_snapshot`
- `connector_position_snapshot`

When changing the DB, confirm the following.

- actual schema and search path
- table and column existence
- primary key and unique key
- foreign key or logical link
- insert·update·upsert conflict target
- transaction and rollback
- commit location
- cursor and connection close
- rowcount validation
- empty result handling
- duplicate row and join cardinality
- timezone and business date

Do not assume column names. Use only names confirmed in `information_schema` or the actual code.

## 21. Environment Variables and Configuration

- Base DB environment variables on the actual implementation of `db_config.py`.
- Do not read or record the actual value of `INTEREST_DB_PASSWORD`.
- Document compatibility environment variables such as `PORTFOLIO_DB_NAME` only after confirming actual code use.
- Account number, broker, environment, strategy, and sizing keys may be documented by key name only.
- Record default values only when they are in the actual code and are not sensitive.
- Do not mix local·paper·live environment values and accounts.
- Confirm that the execution schema search path matches between the actual connection settings and the documentation.
- `PORT_ACCOUNT_NO` is required in `execution_config.py` and fails fast if unset. Do not create a code Fallback.
- When changing the `PORT_ACCOUNT_NO` setting, confirm not only the Runtime but also CI Harness contracts such as pytest·Container Smoke together.
- The CI Harness uses only a test placeholder rather than the actual account number, and does not record the actual account number and Secret verbatim.

## 22. External Dependencies

- Treat the MarketConnector module as an external dependency.
- Do not arbitrarily change the connector module import path.
- Confirm the actual import and call location of the crawler holiday helper dependency.
- Do not duplicate the internal responsibility of external modules into the Execution documentation.
- If `requirements.txt` and the actual imports differ, report the missing·unnecessary dependency.
- Do not add standard library modules to requirements.

## 23. Security and Sensitive Information

- `access_token.txt` is a sensitive-information candidate file.
- Do not read or quote the file value, token, API key, password, account number, and webhook URL.
- Do not leave DB host, ARN, image URI, subnet, security group, broker order number, and connector order id verbatim in documentation.
- When an operational identifier is needed, use `<EXECUTION_ECS_TASK>`, `<CONNECTOR_ORDER_ID>`, or `[REDACTED]`.
- Do not put secret values directly in commands.
- Use environment variables already set by the user or a local secret loader.
- Do not ask the user to re-enter the password value.

For Runtime Token files, adhere to the following.

- Exclude Runtime Token files from Git and the Docker Image.
- Confirm only the existence of the Token file and do not read the value.
- Verify inclusion in the Build Context and Image Layer.
- Do not record the actual value or partial strings in documents and logs.

## 24. Source Modification Rules

- Do not indiscriminately string-replace the original Python files.
- Make localized changes to only the specified files.
- Confirm the function signature, return shape, and exception contract first.
- Confirm import cycles and module side effects.
- Preserve the order of DB writes, connector calls, and status transitions.
- Do not arbitrarily change status strings and reason codes.
- When adding a new retry, first analyze the duplicate-order risk.
- Do not output sensitive information and full payloads in logs.
- Comments describe the implementation as-is and do not present future plans as current features.

## 25. Testing and Validation

For code changes, prioritize validation possible without actual orders or DB writes.

- `python -m py_compile <file>`
- Side-effect-free pure function unit tests
- fixture and mock based tests
- static import path confirmation
- status transition and idempotency tests
- partial fill and duplicate fill tests
- 0-share, negative, minimum amount, and boundary-value tests
- transaction rollback tests

The following validations are not run without explicit approval.

- actual connector BUY·SELL
- actual broker orders
- actual fill query and sync
- actual position sync
- actual intraday quote and monitor
- actual DB write
- actual AWS·SSM·ECS·Step Functions execution

Do not record a validation that could not be run as passed.

### 25.1 Progressive Release Order

Container deployment validation uses the following order by default.

| Stage | Content |
|---|---|
| 1 | Source·Unit Test |
| 2 | Build-only |
| 3 | Git SHA Image and Digest confirmation |
| 4 | Candidate Compile-only |
| 5 | Runtime Source·Import Contract |
| 6 | Order-free Dry-run |
| 7 | Limited Sync·Validator based on existing data |
| 8 | Operational State Machine promotion |
| 9 | Previous Revision Rollback |
| 10 | Validated Revision re-promotion |

Do not treat the success of an earlier stage as the success of a later stage.

## 26. Documentation System

| Document | Role |
|---|---|
| `AGENTS.md` | Execution work·status·data·safety rules |
| `README.md` | Current structure and operational AS-IS |
| `CHANGELOG.md` | Actual change history and facts at the time |
| `docs/source-file-catalog.md` | File responsibilities, input/output, and change impact |

- Do not create new date-specific `docs/worklog/*.md`.
- Do not re-add deleted worklog directories or files to the current structure.
- Do not delete worklog-creation facts recorded in the past CHANGELOG, as they are history at the time.
- Create new documents only when the user specifies.

## 27. Documentation Update Conditions

### 27.1 README.md

Update only the related sections when the following change.

- Project responsibility boundary
- The Execution role in the Daily Step
- entrypoint and execution flow
- Plan·Order·Fill·Position contracts
- Configuration and external dependencies
- Current file structure
- Operational safety criteria

### 27.2 CHANGELOG.md

- Record the actually changed files and content.
- Distinguish documentation changes from functional changes.
- Distinguish whether execution actually occurred.
- Do not distort past history to match the current state.
- Do not include one-time logs, command id, and full DB results.

### 27.3 docs/source-file-catalog.md

When the following change, always confirm whether to update it in the same task.

- File creation·deletion·rename
- entrypoint responsibility change
- builder·sizing·repository role change
- DB read·write target change
- connector call path change
- status transition change
- fill·position sync responsibility change
- intraday monitor responsibility change
- Dockerfile, requirements, and wrapper changes
- documentation file structure change

If there is no change impact, do not modify it unnecessarily and record `Update not required` in the completion report.

## 28. File Deletion and Cleanup

Before deleting a file or classifying it as legacy, confirm the following.

- import or dynamic import
- root entrypoint call
- Docker CMD or command override
- ECS·Batch·Step Functions·Scheduler calls
- PowerShell·BAT·CMD·Shell wrapper
- test and fixture references
- DB output and report consumption
- documentation links
- external MS calls

If evidence is insufficient, record it only as a `cleanup candidate` and do not delete it.

## 29. Git Rules

- Before and after work, confirm the change scope with `git status --short`.
- After work, confirm `git diff --stat` and `git diff --check`.
- Do not revert user changes.
- Do not `git add`, `commit`, `push` without an explicit request.
- Do not `reset`, `restore`, `checkout` without an explicit request.
- For attached-file work where no repository is provided, do not record as if Git validation was performed.

## 30. DevOps CI and State Machine Work Rules

Execution is currently configured as a main Push based Automatic no-order Release.
Maintain the following responsibility boundaries.

- The CI path is GitHub Actions → OIDC → Execution-dedicated CodeBuild.
- CodeBuild has only the Build·Test·Container Smoke·ECR Artifact creation responsibility.
- The GitHub Workflow may hold the Release control-plane responsibility.
- The Release control-plane's State Machine Definition update and State Machine execution are entirely different tasks.
- Do not treat Build·Release Build success as operational order execution success.

Even when Automatic Release is possible, the following are not performed in the Release Pipeline.

- Order execution and Broker·KIS calls
- DB DML and DB Write
- `ecs:RunTask`
- `states:StartExecution`
- `ssm:SendCommand`

When working on State Machine Definition references, adhere to the following.

- Back up the Live Definition before promotion.
- Confirm the target Task Definition reference count and State names.
- Confirm baseline changes with a Stale Promotion Guard.
- Confirm the reference count before and after the change.
- Preserve the Rollback Definition separately and maintain an automatic Rollback path on failure.
- Do not execute the State Machine itself during the Release process.
- Distinguish Definition Promotion from actual Daily order execution as different impacts.

DevOps Architecture, detailed IAM policy, the full Promotion/Rollback design, and the common Release strategy
are not duplicated in this document and are managed in the `port-devops` Repository.

In Kiro documentation work, adhere to the following.

- Do not re-run the AWS·DB·ECS validations performed this time.
- Use the provided validation results only as documentation evidence.
- Perform only static file confirmation.
- Do not execute State Machine·ECS·DB·orders during documentation updates.

## 31. Consistency Check Before Completion

After a document or code change, confirm the following within the related scope.

- Execution responsibility boundary
- Daily Step 8~17 representation
- BUY·SELL candidate creation input
- Plan and Order status
- Duplicate Order prevention
- connector request link
- Auto Execute approval·environment boundary
- partial fill and FILLED judgment
- BUY position creation and merge
- SELL remaining quantity deduction
- separation of intraday check storage and order creation
- separation of backtest candidates and Daily candidates
- DB schema·search path
- whether environment variables are actually used
- requirements and imports
- file structure and documentation links
- whether source-file-catalog needs updating
- whether a new worklog is instructed
- preservation of past CHANGELOG history
- whether sensitive information is newly recorded verbatim
- new cells over 300 characters
- new lines over 500 characters
- UTF-8 No BOM
- tabs and trailing whitespace

## 32. Completion Report

Write the completion report concisely, centered on two-column tables.

| Item | Report content |
|---|---|
| Changed files | Actually modified files |
| Change summary | Responsibility·contract·structure changes |
| Static validation | Validations performed and results |
| Execution validation | Whether performed and the reason for not performing |
| Documentation consistency | Whether README·CHANGELOG·Catalog were updated |
| Sensitive information | Whether recorded verbatim |
| Remaining risk | Items requiring comparison with the actual code·operations |

- If only documentation work was performed, actual order·DB·AWS execution must be 0.
- Do not record an unexecuted validation as a success.
- Leave unclear implementation facts as `Unverified`.
