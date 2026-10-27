# CHANGELOG

Records the primary change history of `port_strategy_execution`.

Confirm the current structure and usage in `README.md`, the work rules in `AGENTS.md`,
and per-file responsibilities and impact in `docs/source-file-catalog.md`.

## 2026-08-14

### main Push Automatic Release Configuration

| Item | Change content |
|---|---|
| Trigger | Configured a main Push based Automatic no-order Release |
| CI authentication | GitHub Actions → OIDC → Execution-dedicated CodeBuild |
| CodeBuild scope | Compile·pytest·Ruff·Docker Build·Container Source Compile·Container Import/File Smoke |
| Artifact | Git SHA based ECR Image Publish on validation success |
| Release control-plane | The GitHub Workflow performs the subsequent operational Promotion |
| Approval stage | No manual Approve stage |

### Release Responsibility Boundary

| Item | Result |
|---|---|
| CodeBuild | Build·Test·Container Smoke·ECR Artifact creation |
| GitHub Workflow | Operational promotion Release control-plane |
| Business Execution | Not executed in the Release Pipeline |
| ecs:RunTask | Not used |
| states:StartExecution | Not used |
| ssm:SendCommand | Not used |
| DB Write | None |
| Broker·KIS order | None |

### Operational Promotion Automation

| Item | Content |
|---|---|
| Script | Added `.devops/scripts/deploy-execution.sh` |
| Baseline discovery | Dynamically confirm the Execution Task Definition baseline from the operational State Machine Definition |
| New Revision | Clone operating settings and register with only the validated ECR Image Digest replaced |
| Reference switch | Automatically change the Execution reference of the related State Machines |
| Activation Scope | 12 State Machines / 28 Execution States |
| Safety boundary | Definition Backup·Stale Promotion Guard·After-check·automatic Rollback on failure |
| Execution boundary | No State Machine execution itself during the Release |

### Final Actual Validation

| Item | Result |
|---|---|
| GitHub Actions Workflow | Success |
| CodeBuild | Success |
| ECR Artifact | Creation success |
| New Task Definition | Registration success |
| Activation Scope Promotion | 12 State Machines / 28 automatic promotions succeeded |
| New operating Revision | Automatic promotion validation complete |
| Artifact consistency | Confirmed Source SHA·ECR Digest·active Task Definition Digest match |
| pytest | 22 passed |
| Business Execution | None |

### PORT_ACCOUNT_NO CI Contract Complement

| Item | Content |
|---|---|
| Required | `PORT_ACCOUNT_NO` required in `execution_config.py`, fail-fast if unset |
| Runtime | Secret-based injection in the AWS Runtime |
| pytest | test placeholder used in CodeBuild pytest |
| Container Smoke | Validate the account environment-variable contract with a placeholder |

### Changed Files

| Item | Value |
|---|---|
| Documents | `README.md`, `AGENTS.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` |

This Kiro work performed only documentation currency updates.
The CI·Release·Promotion validation was used only as documentation evidence from the results performed that day.
Actual SHA, Digest, ARN, Workflow Run ID, Account ID, Secret, and account number are not recorded.
DevOps Architecture, detailed IAM policy, and the common Release strategy are managed in `port-devops`.

## 2026-08-07

### MARKET BUY Cash Protection

| Item | Change content |
|---|---|
| Reserve Ratio | Apply a 110% cash Reserve to MARKET BUY |
| Effective price | Use 110% of the latest price in the quantity calculation |
| Quantity truncation | Truncate to an integer quantity based on the effective order price |
| Amount separation | Separate the estimated order amount from the required cash including Reserve |
| Sequential deduction | Deduct remaining cash based on the required cash of READY candidates |
| Reuse prevention | Prohibit reusing the initial available cash for subsequent candidates |
| Traceability | Keep the allocation basis in the Validation·Snapshot Payload |

### Testing and Deployment

| Item | Result |
|---|---|
| Python Compile | Success |
| Cash allocation tests | 5 targeted tests passed |
| Full tests | 22 passed |
| GitHub Actions | Success |
| CodeBuild | Success |
| Image | Git SHA based Execution Image created |
| Task Definition | New Execution Revision registered |
| Candidate Smoke | Compile Smoke success |
| State reference | Promoted Execution State to the new Revision |
| Previous reference | Confirmed no residual previous Revision reference |

### Daily Incident Confirmation

| Item | Result |
|---|---|
| Step 8 Revision | Referenced an outdated Execution Task Definition |
| Cash duplication | Multiple BUY candidates computed based on the same initial available cash |
| Order overflow | BUY quantity exceeded the account's orderable range |
| Order rejection | BUY rejected due to insufficient Broker orderable amount |
| SELL | Existing SELL order filled normally |
| External Batch | One past Daily Batch remained in long-running RUNNING |
| Recorder | Confirmed the issue that an ok=false failure propagates to Step Functions as a success |

The Batch Recorder and the full Step Functions definition are not owned by Execution,
and are recorded only as an operational Orchestration issue.

### Daily Recovery

| Item | Result |
|---|---|
| Residual Batch | Terminated the RUNNING Batch as FAILED |
| Candidate re-creation | Recomputed BUY candidates with the new Revision |
| Reserve application | Confirmed cumulative cash allocation and the 110% Reserve |
| BUY fill | 1 BUY filled normally |
| BUY Fill Sync | Success |
| BUY Position Sync | Success |
| BUY rejection | 1 BUY REJECTED due to insufficient Broker orderable amount |
| SELL | Existing SELL FILLED maintained |
| Validator | Ran the Order Chain Validator |
| Final status | Daily Step12~17 remained FAILED due to the rejected BUY chain |

### Follow-up Confirmation Candidates

| Item | Confirmation needed |
|---|---|
| READY Plan Count | Organize the Actionable·Terminal Order Count contract |
| Terminal classification | Classify FAILED·REJECTED as a Terminal Failure Chain |
| Orderable amount | Reconcile Broker orderable amount and Available Cash |
| Recorder propagation | The Step Functions failure propagation method for ok=false |

The items above are confirmation candidates and are not changes completed in the current code.

### Changed Files

| Item | Value |
|---|---|
| Python | `execution_buy_sizing.py`, `execution_daily_signal_builder.py` |
| Tests | `tests/test_execution_daily_signal_cash_allocation.py` |
| Documents | `README.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` |

Actually reflected files are based on the Git Diff; assumed file names are not recorded.

### Work Boundary

| Item | Result |
|---|---|
| Paper order recovery | Actual recovery execution performed |
| Connector order·query | Performed |
| Fill Sync | Performed |
| Position Sync | Performed |
| Validator | Performed |
| DB DDL | Not performed |
| Status distortion | Did not change FAILED·REJECTED to success |
| One-time identifiers | Order·Request·Broker numbers not recorded |
| Secret·Token verbatim | Not queried or recorded |

This Kiro documentation work performed only static file confirmation.
The above operational validation was used only as documentation evidence from the results performed that day.

## 2026-08-03

### Execution Error Improvement

| Item | Change content |
|---|---|
| CANCELED BUY | Handle a normal cancellation as a separate Terminal status |
| Step 15 aggregation | Exclude canceled orders from the failure aggregation |
| Step 15 Summary | Separate filled·canceled·terminal·failed |
| P0 Validator | Do not judge a normal cancellation chain as an error |
| FILLED BUY | Maintain the required Position trace criterion |

### BUY Amount Calculation Improvement

| Item | Change content |
|---|---|
| Cumulative allocation | Compute multiple BUY candidates based on cumulative available cash within the Plan |
| Processing order | Preserve the confirmed candidate order |
| READY deduction | Deduct only the estimated amount of READY orders from remaining cash |
| BLOCKED | Do not deduct cash |
| Overflow prevention | Reduce or block a subsequent BUY that exceeds remaining cash |
| Responsibility separation | Distinguish single-ticker Sizing from Plan-level allocation |

### Testing and Source Validation

| Item | Result |
|---|---|
| Unit tests | 20 passed |
| Ruff | Success |
| Python Compile | Success |
| Runtime Token | Confirmed exclusion from Git·Docker Image |
| Source SHA | Changed Source matches the Remote SHA |
| Working Tree | Clean |

### CI and Artifact

| Item | Result |
|---|---|
| Repository | Configured the Execution GitHub Repository and main Branch |
| Authentication | Configured GitHub Actions and the OIDC Role |
| CodeBuild | Linked start·wait success |
| Image | Git SHA based Docker Image created |
| ECR | Confirmed Tag and Digest |
| Execution boundary | No ECS·DB·order execution in Build-only |

### Candidate Validation

| Item | Result |
|---|---|
| Task Definition | Registered a Candidate Revision |
| Compile-only | Success |
| Source·Image | Core Source SHA-256 match |
| Runtime Import | Success |
| Auto BUY Dry-run | Success, 0 READY targets |
| Duplicate order | 0 active duplicates |
| Connector chain | 1 filled BUY·1 canceled BUY normal Terminal |
| Candidate Step 15 | Success |
| Candidate Step 16 | Position creation success |
| Candidate P0 Validator | 2 targets·0 errors success |
| Order impact | No new Connector Request or order submission |

### Operational Promotion and Recovery

| Item | Result |
|---|---|
| Promotion | Promoted 5 Execution-related State references to the new Revision |
| Backup | Backed up the original State Machine Definition |
| Rollback | Restored to the previous Revision successfully |
| Re-promotion | Re-promoted the new Revision successfully |
| Final status | State Machine ACTIVE, Execution references the new Revision |
| Execution impact | No Workflow·ECS·DB·order execution during promotion·Rollback |

### Changed Files

| Item | Value |
|---|---|
| Python | `execution_sync_buy_fill.py`, `execution_sync_buy_position.py` |
| Python | `execution_validate_order_chain.py`, `execution_daily_signal_builder.py` |
| Python | `execution_buy_sizing.py`, `execution_repository.py` |
| Tests | Cancellation·cash allocation·chain validation tests in `tests/` |
| CI | `.github/workflows/execution-codebuild.yml`, `.devops/codebuild/buildspec.yml` |
| CI | `.devops/scripts/container-smoke.py` |
| Container | `Dockerfile`, `.dockerignore`, `.gitignore`, `pytest.ini`, `requirements-dev.txt` |
| Documents | `README.md`, `AGENTS.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` |

Actually reflected files are based on the Git Diff; assumed file names are not recorded.

### Work Boundary

| Item | Result |
|---|---|
| New operational order | Not submitted |
| Candidate validation | Performed Step 15·Step 16·Validator based on existing order data |
| Position row | 1 created during the Candidate Step 16 validation |
| State Machine | Reference changed via promotion·Rollback·re-promotion |
| DB DDL | Not performed |
| Secret·Token verbatim | Not queried or recorded |

## 2026-07-23

### Execution Documentation Baseline Reorganization

| Item | Change content |
|---|---|
| Change scope | Reorganized the `AGENTS.md`, `README.md`, `CHANGELOG.md`, `docs/source-file-catalog.md` documentation baseline |
| Work nature | Documentation improvement that statically compared the current code and operational structure |
| Document structure | Reflected the deletion of `docs/database.md` and `docs/worklog/*.md` |
| Functional change | None |
| Code change | None |
| DB change | None |
| Order execution | None |
| AWS execution | None |
| External API call | None |

### AGENTS.md

| Item | Change content |
|---|---|
| Documentation readability | Added, as top-priority rules, short sentences, two-column tables, and long-cell separation criteria |
| Rule priority | Organized the relationship among the user's latest instruction, Workspace-common rules, and Execution-specific rules |
| Responsibility boundary | Separated roles from Decision·Research·MarketConnector·View·Scheduler |
| Work scope | Clarified the principle of direct modification within `port_strategy_execution` |
| Execution restriction | Strengthened the criteria prohibiting order·DB·Connector·Fill·Position·Intraday execution |
| Plan contract | Added Source, Business Date, Run ID, Summary, re-run, and empty-candidate criteria |
| Order contract | Added Source tracing, status transition, and Connector Request link criteria |
| Duplicate prevention | Added candidate·order-submission·Fill·Position duplicate risk and Idempotency confirmation criteria |
| BUY Sizing | Organized change risks for cash·current holding·price·minimum order·rounding |
| SELL quantity | Added handling criteria for the difference between strategy remaining quantity and Broker sellable quantity |
| Fill Sync | Added partial fill·cumulative fill·average price·duplicate fill·retry criteria |
| Position Sync | Added new Position·additional buy·partial sell·CLOSED transition criteria |
| Transaction | Added criteria for confirming the Commit·Rollback boundary of Order·Fill·Position changes |
| Intraday | Separated storing check results from the Stop Sell Order creation impact |
| Backtest candidate | Organized to treat them as a separate path from Daily operational candidates |
| Deletion safety | Prohibited deletion before confirming Import·Entrypoint·Wrapper·ECS·other-MS references |
| Documentation system | Separated the README·CHANGELOG·Catalog document roles |
| Worklog | Prohibited new creation of date-specific Worklogs |
| Catalog update | Added update criteria for changes to file responsibility·data flow·DB·Connector·status transition |
| Completion report | Organized to distinguish performed and unperformed validation |

### README.md

| Item | Change content |
|---|---|
| Service summary | Organized the primary input·output·operating location·execution form in the first section |
| Responsibility boundary | Redefined as the Execution layer between strategy decisions and the Broker implementation |
| End-to-end flow | Added the Signal·Decision → Plan → Order → Connector → Fill → Position structure |
| Success criteria | Separated candidate creation·order request·Broker acceptance·fill·Position reflection |
| Daily Step | Reorganized Step 8~17 into a role table from the Execution perspective |
| BUY path | Separated the Signal Builder·Sizing·Repository responsibilities |
| SELL path | Separated the Position Decision conversion and Order link responsibilities |
| Auto Execute | Organized the READY query·Mode confirmation·Connector call·status reflection boundary |
| MarketConnector | Clarified Step 12~13 and Step 17 as external responsibilities |
| SELL Fill | Added partial fill·duplicate Fill·remaining quantity·CLOSED transition confirmation criteria |
| BUY Fill | Added cumulative fill·weighted average price·partial fill status criteria |
| BUY Position | Added new creation·additional buy·re-run duplicate prevention criteria |
| Intraday | Distinguished check storage and `INTRADAY_STOP_SELL` candidate creation as separate impacts |
| Plan contract | Added Source·trade date·Run·environment·Summary·No Target criteria |
| Order contract | Added identification criteria·conceptual status flow·Connector link criteria |
| Idempotency | Added candidate·submission·Sync·Position duplicate risk as a separate section |
| BUY Sizing | Organized target amount·cash·holding value·price·minimum amount·truncation criteria |
| SELL quantity | Separated strategy quantity·Broker quantity·requested quantity·filled quantity |
| Fill Sync | Added Request Scope·Fill Scope·Aggregation·Retry·Transaction criteria |
| Position State | Added BUY·SELL fill reflection and re-run safety criteria |
| Backtest | Organized as a candidate creation path separate from Daily operational candidates |
| File structure | Simplified the Root and `docs` structure per the current documentation |
| Worklog | Excluded date-specific `docs/worklog` from the current structure and reflected the new-creation prohibition |
| DB | Separated Execution Write targets and Connector Read targets |
| Search Path | Organized the domain schema order and same-name table risk |
| Configuration | Specified whether environment variables are actually used and Fallback as code-confirmation targets |
| Execution Mode | Specified that a Dry Run may also produce a DB Write |
| Container | Organized ECS execution targets and the operational-identifier Placeholder policy |
| Confirmation items | Separated undecided items such as status strings·Unique Key·partial fill·Transaction |

### CHANGELOG.md

| Item | Change content |
|---|---|
| Structure | Reorganized from long bullets to date-specific two-column change summaries |
| Latest history | Added the 2026-07-23 documentation baseline reorganization record |
| Change boundary | Clearly separated documentation change·code change·DB change·whether executed |
| Past history | Preserved the actual change facts of 2026-05-26~2026-07-01 |
| Worklog history | Kept past creation facts and distinguished them from the current new-creation prohibition policy |
| Sensitive information | Maintained the principle of not recording actual operational identifiers and Credentials verbatim |

### docs/source-file-catalog.md

| Item | Change content |
|---|---|
| Table structure | Reorganized the existing 5-column long-form table into a per-file 2-column responsibility structure |
| Responsibility separation | Separated Entrypoint·Builder·Repository·Sync·Container responsibilities |
| Data contract | Added the Plan·Order·Fill·Position contract table |
| DB impact | Separated DB Write targets and Connector Read targets |
| Impact map | Added a file change impact map |
| Worklog | Removed Worklog from the current list |
| Update criteria | Added Catalog update conditions for changes to file·DB·status·Connector·Docker |

### Document Structure Cleanup

| Target | Handling |
|---|---|
| `docs/database.md` | Reflected file deletion, removed references·links from the 4 documents |
| `docs/worklog/*.md` | Deleted 4 files, excluded from the current structure |
| Documentation system | Organized from 5 documents to 4 documents |
| Past history | Preserved the past facts of the Worklog and Database documents in the past sections |

### Primary Contract Reinforcement

| Contract | Reinforcement content |
|---|---|
| Plan and Order | Do not view Plan creation success and all-Order creation success as the same |
| Order and Connector | Do not view the Execution DB status and the Broker order status as the same |
| Connector and Fill | Distinguish order acceptance and fill completion as separate statuses |
| Fill and Position | Validate Fill reflection success and Position reflection success separately |
| Partial fill | Added a criterion not to prematurely handle a partial Fill as full `FILLED` |
| Duplicate submission | Confirm the existing Connector Request and Broker acceptance before retry |
| Duplicate Sync | Prevent cumulative aggregation of the same Fill and Position re-reflection |
| SELL Position | Deduct only the filled quantity and confirm termination when remaining quantity is 0 |
| BUY Position | Confirm duplicate creation of the same Fill and additional-buy merge criteria |
| No Target | Distinguish a normal empty candidate from a missing input·query failure |
| Transaction | Confirm the recovery boundary when the internal DB fails after an external order success |

### Documentation Maintenance Principles

| Item | Criterion |
|---|---|
| Current state | Recorded in the README |
| Work rules | Recorded in AGENTS |
| Change history | Recorded in the CHANGELOG |
| File responsibility | Recorded in the Source File Catalog |
| DB detail | Recorded in the README Search Path and Catalog DB impact |
| Worklog | Not newly created |
| Repeated explanation | Separated into detailed document links |
| Uncertain fact | Not asserted before confirming code·DB·Wrapper |

### Safety and Validation

| Item | Result |
|---|---|
| Python Entry Point execution | Not performed |
| Execution Order creation | Not performed |
| Connector BUY·SELL call | Not performed |
| Broker·KIS order submission | Not performed |
| Fill Sync | Not performed |
| Position Sync | Not performed |
| Intraday Monitor | Not performed |
| DB DDL·DML | Not performed |
| AWS CLI·SDK | Not performed |
| ECS·SSM·Step Functions | Not performed |
| Sensitive information query·record | Not performed |
| Document file static review | Performed |

## 2026-07-01

### AWS Paper Operations Documentation Reinforcement

| Item | Change content |
|---|---|
| README | Added the Execution role of AWS Paper Daily Step 8~17 |
| Intraday | Added an explanation of the intraday 10-minute Evaluate flow |
| Container | Organized the ECS RunTask target Entry Points |
| Placeholder | Added recording criteria for Cluster·Task Definition·Image·Log identifiers |
| Responsibility boundary | Distinguished Execution direct responsibility from external MS responsibility |
| File structure | Reflected the Docker·Requirements·generation Helper and Docs items |
| Source Catalog | Reinforced the Container-related files and execution risk explanation |
| Database | Specified the Execution Search Path and Schema responsibility scope |

### Documents Added at the Time

| Item | Change content |
|---|---|
| Worklog | Created `docs/worklog/2026-07-01.md` |
| Current policy | Preserved the past creation fact but did not create new Worklogs |

### Work Boundary at the Time

| Item | Result |
|---|---|
| Functional change | None |
| Python code change | None |
| SQL meaning change | None |
| Order flow change | None |
| Execution Mode change | None |
| Order·fill·Position execution | Not performed |
| DB DDL·DML | Not performed |
| External API·Crawler | Not performed |
| AWS operational identifier verbatim record | Not done |

### Reference Scope

At the time, the reference documents selected only the facts necessary for Execution responsibility.

| Excluded area | Owner |
|---|---|
| View screen implementation | port-view |
| KIS API internal implementation | MarketConnector |
| Crawler·Preprocessor internal implementation | The relevant data MS |
| BUY·SELL decision algorithm | StrategyDecision |
| Backtest internal implementation | StrategyResearch |
| Full State Machine | Scheduler·Step Functions |
| Full EventBridge lineup | Common operations documentation |
| Lambda internal implementation | The relevant AWS configuration |
| One-time DB Row·Command ID | Operational logs |

## 2026-05-28

### Documentation and Comment Cleanup

| Item | Change content |
|---|---|
| Source Catalog | Initially added `docs/source-file-catalog.md` |
| Module Docstring | Added role and impact explanations to the primary Python files |
| Function Docstring | Added explanations to the primary order·Fill·Position·Intraday functions |
| README | Added the file Catalog and comment-cleanup criteria |
| Intraday | Reflected the 2026-05-27 normal check result storage policy in the documentation |
| Worklog | Created `docs/worklog/2026-05-28.md` |

### Work Boundary at the Time

| Item | Result |
|---|---|
| Functional change | None |
| Execution logic change | None |
| SQL meaning change | None |
| Order·Connector execution | Not performed |
| Fill·Position Sync | Not performed |
| Intraday Monitor | Not performed |
| DB DDL·DML | Not performed |

## 2026-05-27

### DB Configuration and Schema Transition

| Item | Change content |
|---|---|
| DB environment variables | Externalized based on `INTEREST_DB_*` |
| DB Password | Organized `INTEREST_DB_PASSWORD` as a required value with no default |
| Legacy Script | Changed hardcoded settings to use `db_config.get_db_config()` |
| Default DB | Organized the local PostgreSQL DB Name as `portfolio` |
| Schema structure | Documented the single DB + schema-per-domain structure |
| Search Path | Organized so existing SQL operates based on the Connection Search Path |

The items on this date are the actual configuration·code change history.
Re-confirm whether they match the current code against the latest source.

## 2026-05-26

### Initial Documentation and File Cleanup

| Item | Change content |
|---|---|
| AGENTS | Added the initial `AGENTS.md` |
| README | Added the initial `README.md` |
| Worklog | Created `docs/worklog/2026-05-26.md` |
| Test Script | Removed local test·scratch candidate files |
| Python Cache | Removed `__pycache__/` |

### Files Removed at the Time

| File | Classification |
|---|---|
| `test_connector_buy_1_share.py` | Local order test |
| `test_repository_sell_functions.py` | Repository SELL test |
| `test_sell_evaluator.py` | Sell Evaluator test |
| `__pycache__/` | Python Cache artifact |

### Work Basis at the Time

| Item | Criterion |
|---|---|
| Documentation basis | Read-only confirmation of the file structure and source at the time |
| Order execution | Not performed |
| Connector call | Not performed |
| Fill·Position Sync | Not performed |
| Intraday Monitor | Not performed |
| DB DDL·DML | Not performed |
| External API·Crawler | Not performed |
| Sensitive information | Actual values not recorded |
