#!/usr/bin/env bash
# convert_local / convert_all 后台启动：macOS 用 start_new_session 脱离终端。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -n "${LEVEL2_PYTHON:-}" && -x "${LEVEL2_PYTHON}" ]]; then
  PY="${LEVEL2_PYTHON}"
elif [[ -x "${ROOT}/../../level2/.venv/bin/python" ]]; then
  # 批量转换需要 pyarrow。backend 自己的 venv 还没有时，沿用原来的解释器。
  PY="${ROOT}/../../level2/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
export QUANTDINGER_SKIP_APP_INIT=1
STAGING="${ROOT}/data/level2_staging"
BATCH_KEY="all"

usage() {
  cat <<'EOF'
用法:
  run_level2_convert.sh all [start 选项] | status | tail | stop
  run_level2_convert.sh DATE [start 选项] | status | tail | stop

  all     扫描 data/level2_raw 下全部 .7z 与已解压目录，串行解压后
          直接从 CSV 算日频因子并写入 D1，不落明细 Parquet。
          达标后删 CSV 与 .7z。--dry-run 只调度，不算不写。
  DATE    单日 YYYYMMDD（仍走 convert_local：CSV→明细 Parquet）

  start   后台启动（默认）
  status  查看 PID / 进度
  tail    跟踪日志
  stop    SIGTERM 停止

示例:
  ./scripts/run_level2_convert.sh all
  ./scripts/run_level2_convert.sh all --no-delete
  ./scripts/run_level2_convert.sh all --workers 8
  ./scripts/run_level2_convert.sh all status
  ./scripts/run_level2_convert.sh all tail
  ./scripts/run_level2_convert.sh all stop
  ./scripts/run_level2_convert.sh 20260506 --source 7z
  ./scripts/run_level2_convert.sh 20260506 stop

all 的 start 选项（传给 convert_all）:
  --workers N              因子计算并行度（默认 8）
  --dry-run
  --no-skip                已写入 D1 的日期也重算并覆盖
  --no-delete              写完不删 CSV 目录与 .7z（默认会删）
  --all-symbols
  --local-only
  --7z-only
  --dates YYYYMMDD ...

单日 start 选项（传给 convert_local）:
  --source auto|local|7z   默认 auto
  --workers N
  --dry-run
  --no-skip
  --no-delete
  --all-symbols
  --code CODE
  --type TYPE
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

validate_date() {
  local d="$1"
  [[ "$d" =~ ^[0-9]{8}$ ]] || die "DATE 须为 YYYYMMDD，收到: $d"
}

# 日志与 pid：单日 convert_YYYYMMDD.*；批量 convert_all.*
log_path() {
  echo "${STAGING}/logs/convert_${1}.log"
}

# 转换日志超过 32MB 时只留末尾约 256KB，再交给后续追加。
trim_log() {
  local file="$1"
  local limit=$((32 * 1024 * 1024))
  local keep=$((256 * 1024))
  local size
  [[ -f "$file" ]] || return 0
  size="$(wc -c < "$file" | tr -d '[:space:]')"
  if (( size <= limit )); then
    return 0
  fi
  tail -c "$keep" "$file" > "${file}.tail"
  mv "${file}.tail" "$file"
}

pid_path() {
  echo "${STAGING}/logs/convert_${1}.pid"
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
    echo "parquet: $(parquet_count_all) (全部日期合计)"
    echo "data:    ${ROOT}/data/level2_raw"
  else
    echo "parquet: $(parquet_count "$key")"
  fi
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

# 后台启动：MODE=date|all，KEY 为日期或 all
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
  trim_log "$lf"

  local convert_args=()
  local module=""

  if [[ "$mode" == "all" ]]; then
    module="app.services.level2_ingest.convert_all"
    if ((${#extra_args[@]} > 0)); then
      convert_args+=("${extra_args[@]}")
    fi
  else
    module="app.services.level2_ingest.convert_local"
    local has_source=0
    local arg
    if ((${#extra_args[@]} > 0)); then
      for arg in "${extra_args[@]}"; do
        if [[ "$arg" == "--source" ]]; then
          has_source=1
          break
        fi
      done
    fi
    convert_args=(--date "$key")
    if [[ "$has_source" -eq 0 ]]; then
      convert_args+=(--source auto)
    fi
    if ((${#extra_args[@]} > 0)); then
      convert_args+=("${extra_args[@]}")
    fi
  fi

  export ROOT PY LF="$lf" PF="$pf" MODULE="$module"
  export CONVERT_ARGS
  # bash 3.2 + set -u：空数组 "${convert_args[@]}" 会 unbound
  if ((${#convert_args[@]} > 0)); then
    CONVERT_ARGS="$(printf '%s\n' "${convert_args[@]}")"
  else
    CONVERT_ARGS=""
  fi
  CONVERT_ARGS="$CONVERT_ARGS" \
    "$PY" - <<'PY'
import os
import subprocess
from pathlib import Path

root = Path(os.environ["ROOT"])
py = Path(os.environ["PY"])
log = Path(os.environ["LF"])
pidf = Path(os.environ["PF"])
module = os.environ["MODULE"]
extra = [ln for ln in os.environ.get("CONVERT_ARGS", "").splitlines() if ln]

cmd = [str(py), "-m", module, *extra]

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

  echo "tail:   ./scripts/run_level2_convert.sh ${key} tail"
  echo "status: ./scripts/run_level2_convert.sh ${key} status"
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
