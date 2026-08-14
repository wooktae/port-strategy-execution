#!/usr/bin/env bash
set -Eeuo pipefail

REGION="${AWS_REGION:-ap-northeast-2}"
SOURCE_SHA="${SOURCE_SHA:-}"

ECR_REPOSITORY="portfolio-strategy-execution"
TASK_FAMILY="portfolio-paper-strategy-execution"

EXPECTED_STATE_MACHINE_COUNT=12
EXPECTED_EXECUTION_STATE_COUNT=28

STATE_MACHINE_NAMES=(
  "portfolio-paper-daily-step1-11-safe"
  "portfolio-paper-daily-step1-17-approval"
  "portfolio-paper-daily-step10-only"
  "portfolio-paper-daily-step11-only"
  "portfolio-paper-daily-step12-17-approval"
  "portfolio-paper-daily-step14-only"
  "portfolio-paper-daily-step15-only"
  "portfolio-paper-daily-step16-only"
  "portfolio-paper-daily-step6-step7-step8-step9-step10-step11"
  "portfolio-paper-daily-step8-only"
  "portfolio-paper-daily-step9-only"
  "portfolio-paper-intraday-stop-sell-approval"
)

WORK="${RUNNER_TEMP:-/tmp}/execution-release"
BACKUP_DIR="${WORK}/backup"
TARGET_DIR="${WORK}/target"
MODIFIED_FILE="${WORK}/modified.tsv"

rm -rf "${WORK}"
mkdir -p "${BACKUP_DIR}" "${TARGET_DIR}"
: > "${MODIFIED_FILE}"

rollback_required="false"

fail() {
  echo "ERROR=$1"
  return 1
}

canonical_hash() {
  python - "$1" <<'PY'
import hashlib
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    obj = json.load(f)

raw = json.dumps(
    obj,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")

print(hashlib.sha256(raw).hexdigest())
PY
}

wait_active() {
  local arn="$1"

  for _ in $(seq 1 30); do
    local status

    status="$(
      aws stepfunctions describe-state-machine \
        --region "${REGION}" \
        --state-machine-arn "${arn}" \
        --query status \
        --output text
    )"

    if [[ "${status}" == "ACTIVE" ]]; then
      return 0
    fi

    sleep 2
  done

  return 1
}

rollback() {
  local original_exit="$?"

  trap - ERR
  set +e

  echo "=== EXECUTION AUTOMATIC ROLLBACK ==="

  if [[ "${rollback_required}" != "true" || ! -s "${MODIFIED_FILE}" ]]; then
    echo "ROLLBACK_REQUIRED=NO"
    exit "${original_exit}"
  fi

  mapfile -t changed < "${MODIFIED_FILE}"

  rollback_failed=0

  for ((i=${#changed[@]}-1; i>=0; i--)); do
    IFS=$'\t' read -r arn backup target <<< "${changed[$i]}"

    echo "ROLLBACK_STATE_MACHINE=${arn}"

    current="${WORK}/rollback-current-${i}.json"
    verify="${WORK}/rollback-verify-${i}.json"

    aws stepfunctions describe-state-machine \
      --region "${REGION}" \
      --state-machine-arn "${arn}" \
      --query definition \
      --output text > "${current}"

    if [[ "$(canonical_hash "${current}")" != "$(canonical_hash "${target}")" ]]; then
      echo "ROLLBACK_STALE_GUARD=FAILED"
      rollback_failed=1
      continue
    fi

    aws stepfunctions update-state-machine \
      --region "${REGION}" \
      --state-machine-arn "${arn}" \
      --definition "file://${backup}" \
      >/dev/null

    if ! wait_active "${arn}"; then
      echo "ROLLBACK_ACTIVE_VERIFY=FAILED"
      rollback_failed=1
      continue
    fi

    aws stepfunctions describe-state-machine \
      --region "${REGION}" \
      --state-machine-arn "${arn}" \
      --query definition \
      --output text > "${verify}"

    if [[ "$(canonical_hash "${verify}")" != "$(canonical_hash "${backup}")" ]]; then
      echo "ROLLBACK_DEFINITION_VERIFY=FAILED"
      rollback_failed=1
      continue
    fi

    echo "ROLLBACK_STATE_MACHINE=SUCCESS"
  done

  if [[ "${rollback_failed}" -ne 0 ]]; then
    echo "EXECUTION_AUTOMATIC_ROLLBACK=FAILED"
    exit 90
  fi

  echo "EXECUTION_AUTOMATIC_ROLLBACK=SUCCESS"
  exit "${original_exit}"
}

trap rollback ERR

echo "=== VERIFY RELEASE INPUT ==="

if [[ ! "${SOURCE_SHA}" =~ ^[0-9a-fA-F]{40}$ ]]; then
  fail "INVALID_SOURCE_SHA"
fi

IMAGE_TAG="${SOURCE_SHA:0:12}"

echo "SOURCE_SHA=${SOURCE_SHA}"
echo "IMAGE_TAG=${IMAGE_TAG}"

echo "=== RESOLVE ECR ARTIFACT ==="

ACCOUNT_ID="$(
  aws sts get-caller-identity \
    --query Account \
    --output text
)"

IMAGE_DIGEST="$(
  aws ecr describe-images \
    --region "${REGION}" \
    --repository-name "${ECR_REPOSITORY}" \
    --image-ids "imageTag=${IMAGE_TAG}" \
    --query 'imageDetails[0].imageDigest' \
    --output text
)"

if [[ -z "${IMAGE_DIGEST}" || "${IMAGE_DIGEST}" == "None" ]]; then
  fail "IMAGE_DIGEST_NOT_FOUND"
fi

IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}@${IMAGE_DIGEST}"

echo "IMAGE_DIGEST=${IMAGE_DIGEST}"
echo "IMAGE_URI=${IMAGE_URI}"
echo "ARTIFACT_RESOLVE=SUCCESS"

echo "=== RESOLVE ACTIVATION SCOPE ==="

mapfile -t ALL_STATE_MACHINES < <(
  aws stepfunctions list-state-machines \
    --region "${REGION}" \
    --query 'stateMachines[].[name,stateMachineArn]' \
    --output text
)

declare -a SM_ARNS=()
declare -a BACKUPS=()
declare -a TARGETS=()
declare -a BASELINE_HASHES=()

BASELINE_TASK_ARN=""
TOTAL_EXECUTION_STATES=0

for index in "${!STATE_MACHINE_NAMES[@]}"; do
  name="${STATE_MACHINE_NAMES[$index]}"
  arn=""

  for row in "${ALL_STATE_MACHINES[@]}"; do
    row_name="${row%%$'\t'*}"
    row_arn="${row#*$'\t'}"

    if [[ "${row_name}" == "${name}" ]]; then
      arn="${row_arn}"
      break
    fi
  done

  if [[ -z "${arn}" ]]; then
    fail "STATE_MACHINE_NOT_FOUND:${name}"
  fi

  backup="${BACKUP_DIR}/${index}.json"

  aws stepfunctions describe-state-machine \
    --region "${REGION}" \
    --state-machine-arn "${arn}" \
    --query definition \
    --output text > "${backup}"

  read -r state_count unique_count task_arn < <(
    python - "${backup}" "${TASK_FAMILY}" <<'PY'
import json
import re
import sys

path = sys.argv[1]
family = sys.argv[2]

pattern = re.compile(
    r"arn:aws:ecs:[^:\"]+:\d{12}:task-definition/"
    + re.escape(family)
    + r":\d+"
)

with open(path, encoding="utf-8") as f:
    definition = json.load(f)

state_count = 0
refs = []

for state in definition.get("States", {}).values():
    payload = json.dumps(state, ensure_ascii=False)
    matches = pattern.findall(payload)

    if matches:
        state_count += 1
        refs.extend(matches)

unique = sorted(set(refs))

task_arn = unique[0] if len(unique) == 1 else "MULTIPLE"

print(state_count, len(unique), task_arn)
PY
  )

  if [[ "${unique_count}" -ne 1 ]]; then
    fail "INVALID_EXECUTION_REFERENCE_COUNT:${name}:${unique_count}"
  fi

  if [[ -z "${BASELINE_TASK_ARN}" ]]; then
    BASELINE_TASK_ARN="${task_arn}"
  elif [[ "${task_arn}" != "${BASELINE_TASK_ARN}" ]]; then
    fail "MIXED_EXECUTION_BASELINE:${name}"
  fi

  TOTAL_EXECUTION_STATES=$((TOTAL_EXECUTION_STATES + state_count))

  SM_ARNS+=("${arn}")
  BACKUPS+=("${backup}")
  BASELINE_HASHES+=("$(canonical_hash "${backup}")")

  echo "STATE_MACHINE=${name}"
  echo "EXECUTION_STATE_COUNT=${state_count}"
  echo "TASK_DEFINITION=${task_arn}"
done

if [[ "${#SM_ARNS[@]}" -ne "${EXPECTED_STATE_MACHINE_COUNT}" ]]; then
  fail "STATE_MACHINE_COUNT_MISMATCH:${#SM_ARNS[@]}"
fi

if [[ "${TOTAL_EXECUTION_STATES}" -ne "${EXPECTED_EXECUTION_STATE_COUNT}" ]]; then
  fail "EXECUTION_STATE_COUNT_MISMATCH:${TOTAL_EXECUTION_STATES}"
fi

echo "STATE_MACHINE_COUNT=${#SM_ARNS[@]}"
echo "EXECUTION_STATE_COUNT=${TOTAL_EXECUTION_STATES}"
echo "OPERATING_BASELINE=${BASELINE_TASK_ARN}"
echo "ACTIVATION_SCOPE_VERIFY=SUCCESS"

echo "=== BUILD NEW TASK DEFINITION ==="

BASELINE_TD="${WORK}/baseline-task-definition.json"
REGISTER_TD="${WORK}/register-task-definition.json"

aws ecs describe-task-definition \
  --region "${REGION}" \
  --task-definition "${BASELINE_TASK_ARN}" \
  --query taskDefinition \
  --output json > "${BASELINE_TD}"

python - \
  "${BASELINE_TD}" \
  "${REGISTER_TD}" \
  "${ECR_REPOSITORY}" \
  "${IMAGE_URI}" <<'PY'
import json
import sys

src, dst, repository, image_uri = sys.argv[1:]

with open(src, encoding="utf-8") as f:
    td = json.load(f)

for key in (
    "taskDefinitionArn",
    "revision",
    "status",
    "requiresAttributes",
    "compatibilities",
    "registeredAt",
    "registeredBy",
    "deregisteredAt",
):
    td.pop(key, None)

matched = []

for container in td.get("containerDefinitions", []):
    image = str(container.get("image", ""))

    if f"/{repository}" in image:
        matched.append(container)

if len(matched) != 1:
    raise SystemExit(
        f"EXECUTION_CONTAINER_MATCH_COUNT={len(matched)}"
    )

matched[0]["image"] = image_uri

with open(dst, "w", encoding="utf-8") as f:
    json.dump(td, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY

NEW_TASK_ARN="$(
  aws ecs register-task-definition \
    --region "${REGION}" \
    --cli-input-json "file://${REGISTER_TD}" \
    --query taskDefinition.taskDefinitionArn \
    --output text
)"

if [[ -z "${NEW_TASK_ARN}" || "${NEW_TASK_ARN}" == "None" ]]; then
  fail "TASK_DEFINITION_REGISTER_FAILED"
fi

REGISTERED_IMAGE="$(
  aws ecs describe-task-definition \
    --region "${REGION}" \
    --task-definition "${NEW_TASK_ARN}" \
    --query "taskDefinition.containerDefinitions[?contains(image, '/${ECR_REPOSITORY}')].image | [0]" \
    --output text
)"

if [[ "${REGISTERED_IMAGE}" != "${IMAGE_URI}" ]]; then
  fail "REGISTERED_IMAGE_MISMATCH"
fi

echo "NEW_TASK_DEFINITION=${NEW_TASK_ARN}"
echo "TASK_DEFINITION_REGISTER=SUCCESS"

echo "=== PREPARE STATE MACHINE DEFINITIONS ==="

for index in "${!SM_ARNS[@]}"; do
  backup="${BACKUPS[$index]}"
  target="${TARGET_DIR}/${index}.json"

  python - \
    "${backup}" \
    "${target}" \
    "${BASELINE_TASK_ARN}" \
    "${NEW_TASK_ARN}" <<'PY'
import json
import sys

src, dst, old_ref, new_ref = sys.argv[1:]

with open(src, encoding="utf-8") as f:
    obj = json.load(f)

count = 0

def replace(value):
    global count

    if isinstance(value, dict):
        return {k: replace(v) for k, v in value.items()}

    if isinstance(value, list):
        return [replace(v) for v in value]

    if isinstance(value, str):
        found = value.count(old_ref)

        if found:
            count += found
            return value.replace(old_ref, new_ref)

    return value

result = replace(obj)

if count == 0:
    raise SystemExit("TASK_DEFINITION_REPLACEMENT_COUNT=0")

with open(dst, "w", encoding="utf-8") as f:
    json.dump(
        result,
        f,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    f.write("\n")

print(f"TASK_DEFINITION_REPLACEMENT_COUNT={count}")
PY

  TARGETS+=("${target}")
done

echo "PROMOTION_DEFINITION_PREPARE=SUCCESS"

echo "=== PROMOTE EXECUTION REVISION ==="

rollback_required="true"

for index in "${!SM_ARNS[@]}"; do
  arn="${SM_ARNS[$index]}"
  backup="${BACKUPS[$index]}"
  target="${TARGETS[$index]}"

  current="${WORK}/pre-update-${index}.json"

  aws stepfunctions describe-state-machine \
    --region "${REGION}" \
    --state-machine-arn "${arn}" \
    --query definition \
    --output text > "${current}"

  if [[ "$(canonical_hash "${current}")" != "${BASELINE_HASHES[$index]}" ]]; then
    fail "STALE_PROMOTION_GUARD:${arn}"
  fi

  aws stepfunctions update-state-machine \
    --region "${REGION}" \
    --state-machine-arn "${arn}" \
    --definition "file://${target}" \
    >/dev/null

  printf '%s\t%s\t%s\n' \
    "${arn}" \
    "${backup}" \
    "${target}" \
    >> "${MODIFIED_FILE}"

  wait_active "${arn}"

  verify="${WORK}/post-update-${index}.json"

  aws stepfunctions describe-state-machine \
    --region "${REGION}" \
    --state-machine-arn "${arn}" \
    --query definition \
    --output text > "${verify}"

  if [[ "$(canonical_hash "${verify}")" != "$(canonical_hash "${target}")" ]]; then
    fail "PROMOTION_VERIFY_FAILED:${arn}"
  fi

  echo "PROMOTION_VERIFY=SUCCESS:${arn}"
done

echo "=== FINAL ACTIVATION VERIFY ==="

FINAL_STATE_MACHINE_COUNT=0
FINAL_EXECUTION_STATE_COUNT=0

for index in "${!SM_ARNS[@]}"; do
  arn="${SM_ARNS[$index]}"
  final="${WORK}/final-${index}.json"

  aws stepfunctions describe-state-machine \
    --region "${REGION}" \
    --state-machine-arn "${arn}" \
    --query definition \
    --output text > "${final}"

  read -r state_count old_count new_count unexpected_count < <(
    python - \
      "${final}" \
      "${TASK_FAMILY}" \
      "${BASELINE_TASK_ARN}" \
      "${NEW_TASK_ARN}" <<'PY'
import json
import re
import sys

path, family, old_ref, new_ref = sys.argv[1:]

pattern = re.compile(
    r"arn:aws:ecs:[^:\"]+:\d{12}:task-definition/"
    + re.escape(family)
    + r":\d+"
)

with open(path, encoding="utf-8") as f:
    definition = json.load(f)

states = 0
refs = []

for state in definition.get("States", {}).values():
    payload = json.dumps(state, ensure_ascii=False)
    matches = pattern.findall(payload)

    if matches:
        states += 1
        refs.extend(matches)

old_count = sum(ref == old_ref for ref in refs)
new_count = sum(ref == new_ref for ref in refs)
unexpected = sum(
    ref not in {old_ref, new_ref}
    for ref in refs
)

print(states, old_count, new_count, unexpected)
PY
  )

  if [[ "${old_count}" -ne 0 ]]; then
    fail "STALE_PREVIOUS_REVISION:${arn}"
  fi

  if [[ "${unexpected_count}" -ne 0 ]]; then
    fail "UNEXPECTED_EXECUTION_REVISION:${arn}"
  fi

  if [[ "${state_count}" -ne "${new_count}" ]]; then
    fail "NEW_REVISION_COUNT_MISMATCH:${arn}"
  fi

  FINAL_STATE_MACHINE_COUNT=$((FINAL_STATE_MACHINE_COUNT + 1))
  FINAL_EXECUTION_STATE_COUNT=$((FINAL_EXECUTION_STATE_COUNT + state_count))
done

if [[ "${FINAL_STATE_MACHINE_COUNT}" -ne "${EXPECTED_STATE_MACHINE_COUNT}" ]]; then
  fail "FINAL_STATE_MACHINE_COUNT_MISMATCH"
fi

if [[ "${FINAL_EXECUTION_STATE_COUNT}" -ne "${EXPECTED_EXECUTION_STATE_COUNT}" ]]; then
  fail "FINAL_EXECUTION_STATE_COUNT_MISMATCH"
fi

rollback_required="false"
trap - ERR

echo "=== EXECUTION RELEASE SUMMARY ==="
echo "SOURCE_SHA=${SOURCE_SHA}"
echo "IMAGE_DIGEST=${IMAGE_DIGEST}"
echo "PREVIOUS_TASK_DEFINITION=${BASELINE_TASK_ARN}"
echo "NEW_TASK_DEFINITION=${NEW_TASK_ARN}"
echo "STATE_MACHINE_COUNT=${FINAL_STATE_MACHINE_COUNT}"
echo "EXECUTION_STATE_COUNT=${FINAL_EXECUTION_STATE_COUNT}"
echo "STALE_PREVIOUS_REFERENCE_COUNT=0"
echo "ECS_RUN_TASK_EXECUTED=NO"
echo "STEPFUNCTIONS_EXECUTION_STARTED=NO"
echo "SSM_COMMAND_EXECUTED=NO"
echo "ORDER_EXECUTION=NO"
echo "EXECUTION_AUTOMATIC_RELEASE=SUCCESS"