#!/usr/bin/env bash
# upload_staging 后台启动：按日上传 .staging/parquet 到 STORAGE_BACKEND。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -n "${LEVEL2_PYTHON:-}" && -x "${LEVEL2_PYTHON}" ]]; then
  PY="${LEVEL2_PYTHON}"
elif [[ -x "${ROOT}/../../level2/.venv/bin/python" ]]; then
  PY="${ROOT}/../../level2/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
export QUANTDINGER_SKIP_APP_INIT=1
STAGING="${ROOT}/data/level2_staging"
BATCH_KEY="all"

usage() {
  cat <<'USAGE'
用法:
  run_level2_upload.sh all [start 选项] | status | tail | stop
  run_level2_upload.sh DATE [start 选项] | status | tail | stop

  all     上传 data/level2_staging/parquet 下全部日期（按日串行）
  DATE    仅上传该日 YYYYMMDD

  start   后台启动（默认）
  status  查看 PID
  tail    跟踪日志
  stop    SIGTERM 停止

示例:
  ./scripts/run_level2_upload.sh all
  ./scripts/run_level2_upload.sh all --workers 4
  ./scripts/run_level2_upload.sh all --dry-run
  ./scripts/run_level2_upload.sh all status
  ./scripts/run_level2_upload.sh all tail
  ./scripts/run_level2_upload.sh all stop
  ./scripts/run_level2_upload.sh 20260506

start 选项（传给 upload_staging）:
  --workers N
  --dry-run
  --no-skip
  --all-symbols
  --dates YYYYMMDD ...   （仅 all 时；单日用 DATE 参数即可）
  --code CODE
  --type TYPE
USAGE
}

die() {
  echo "error: $*" >&2
  exit 1
}

validate_date() {
  local d="$1"
  [[ "$d" =~ ^[0-9]{8}$ ]] || die "DATE 须为 YYYYMMDD，收到: $d"
}

log_path() {
  echo "${STAGING}/logs/upload_${1}.log"
}

pid_path() {
  echo "${STAGING}/logs/upload_${1}.pid"
}

read_pid() {
  local pf
  pf="$(pid_path "$1")"
  [[ -f "$pf" ]] || return 1
  tr -d '[:space:]' < "$pf"
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

parquet_count() {
  local date="$1"
  local dir="${STAGING}/parquet/${date}"
  if [[ ! -d "$dir" ]]; then
    echo 0
    return
  fi
  find "$dir" -name '*.parquet' 2>/dev/null | wc -l | tr -d '[:space:]'
}

parquet_count_all() {
  local dir="${STAGING}/parquet"
  if [[ ! -d "$dir" ]]; then
    echo 0
    return
  fi
  find "$dir" -name '*.parquet' 2>/dev/null | wc -l | tr -d '[:space:]'
}

cmd_status() {
  local key="$1"
  local pf pid
  pf="$(pid_path "$key")"
  echo "key:     ${key}"
  echo "log:     $(log_path "$key")"
  echo "pidfile: ${pf}"
  if [[ "$key" == "$BATCH_KEY" ]]; then
    echo "parquet: $(parquet_count_all) (staging 合计)"
  else
    echo "parquet: $(parquet_count "$key")"
  fi
  echo "staging: ${STAGING}/parquet"
  if pid="$(read_pid "$key" 2>/dev/null)" && is_running "$pid"; then
    echo "status:  running (pid=${pid})"
    ps -p "$pid" -o pid=,etime=,pcpu=,command= 2>/dev/null || true
    return 0
  fi
  echo "status:  not running"
  return 1
}

cmd_tail() {
  local key="$1"
  local lf
  lf="$(log_path "$key")"
  mkdir -p "${STAGING}/logs"
  touch "$lf"
  tail -f "$lf"
}

cmd_stop() {
  local key="$1"
  local pid
  pid="$(read_pid "$key" 2>/dev/null)" || die "无 pid 文件: $(pid_path "$key")"
  if ! is_running "$pid"; then
    echo "进程已不在运行 (pid=${pid})"
    return 0
  fi
  echo "发送 SIGTERM 到 pid=${pid} ..."
  kill -TERM "$pid"
  for _ in $(seq 1 30); do
    if ! is_running "$pid"; then
      echo "已停止"
      return 0
    fi
    sleep 1
  done
  die "进程未在 30s 内退出，可手动 kill -9 ${pid}"
}

cmd_start() {
  local mode="$1"
  local key="$2"
  shift 2
  local extra_args=()
  if (($# > 0)); then
    extra_args=("$@")
  fi

  [[ -x "$PY" ]] || die "未找到 venv python: $PY"

  if pid="$(read_pid "$key" 2>/dev/null)" && is_running "$pid"; then
    die "已在运行 pid=${pid}，先 stop 或删 pid 文件"
  fi

  mkdir -p "${STAGING}/logs"
  local lf pf
  lf="$(log_path "$key")"
  pf="$(pid_path "$key")"

  local upload_args=()
  if [[ "$mode" == "date" ]]; then
    upload_args+=(--dates "$key")
  fi
  if ((${#extra_args[@]} > 0)); then
    upload_args+=("${extra_args[@]}")
  fi

  export ROOT PY LF="$lf" PF="$pf"
  export UPLOAD_ARGS
  if ((${#upload_args[@]} > 0)); then
    UPLOAD_ARGS="$(printf '%s\n' "${upload_args[@]}")"
  else
    UPLOAD_ARGS=""
  fi
  UPLOAD_ARGS="$UPLOAD_ARGS" \
    "$PY" - <<'PY'
import os
import subprocess
from pathlib import Path

root = Path(os.environ["ROOT"])
py = Path(os.environ["PY"])
log = Path(os.environ["LF"])
pidf = Path(os.environ["PF"])
extra = [ln for ln in os.environ.get("UPLOAD_ARGS", "").splitlines() if ln]

cmd = [str(py), "-m", "app.services.level2_ingest.upload_staging", *extra]

log.parent.mkdir(parents=True, exist_ok=True)
with open(log, "a", encoding="utf-8") as out:
    p = subprocess.Popen(
        cmd,
        stdout=out,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(root),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
pidf.write_text(str(p.pid) + "\n", encoding="utf-8")
print(f"started pid={p.pid}")
print(f"log={log}")
print("cmd=" + " ".join(cmd))
PY

  echo "tail:   ./scripts/run_level2_upload.sh ${key} tail"
  echo "status: ./scripts/run_level2_upload.sh ${key} status"
}

main() {
  [[ $# -ge 1 ]] || { usage; exit 1; }

  local key="$1"
  shift

  local mode="date"
  if [[ "$key" == "$BATCH_KEY" ]]; then
    mode="all"
  else
    validate_date "$key"
  fi

  local subcmd="start"
  case "${1:-}" in
    start|status|tail|stop)
      subcmd="$1"
      shift
      ;;
  esac

  case "$subcmd" in
    start)  cmd_start "$mode" "$key" "$@" ;;
    status) cmd_status "$key" ;;
    tail)   cmd_tail "$key" ;;
    stop)   cmd_stop "$key" ;;
    *)      usage; exit 1 ;;
  esac
}

main "$@"
