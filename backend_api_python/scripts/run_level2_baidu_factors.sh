#!/usr/bin/env bash
# 从百度网盘按日下载 Level2 明细，算因子并上传 R2。
# 日内先并行下完全市场，再计算、上传；成功后清本地明细，再进下一日。
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
# 这套解释器可能没有 Flask。跳过 Web 应用后才能导入批量模块。
export QUANTDINGER_SKIP_APP_INIT=1
STAGING="${ROOT}/data/level2_staging"
JOB_KEY="baidu_factor"

usage() {
  cat <<'USAGE'
用法:
  run_level2_baidu_factors.sh --start YYYYMMDD --end YYYYMMDD [选项]
  run_level2_baidu_factors.sh --start YYYYMMDD --end YYYYMMDD start [选项]
  run_level2_baidu_factors.sh status | tail | stop

  按日历日从早到晚：并行下载当日全部股票 → 计算日频因子 → 上传 R2 → 清本地明细。
  已上传日期默认跳过。上传失败会停止后续日期。

示例:
  ./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922
  ./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922 --dry-run
  ./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922 start
  ./scripts/run_level2_baidu_factors.sh status
  ./scripts/run_level2_baidu_factors.sh tail
  ./scripts/run_level2_baidu_factors.sh stop
  ./scripts/run_level2_baidu_factors.sh --start 20251009 --end 20260922 --force --mirror

选项:
  --start YYYYMMDD        起始日（含）
  --end YYYYMMDD          结束日（含）
  --download-workers N    百度并行下载数，默认 8
  --workers N             因子计算并行度，默认 8
  --force                 已上传的日期也重算并覆盖上传
  --dry-run               只打印将处理的日历日
  --mirror                全部日期成功后再重建股票镜像
  --books-dir PATH        明细临时目录，默认 data/level2_parquet
  --output PATH           因子输出目录，默认 staging/factors
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
  echo "${STAGING}/logs/${JOB_KEY}.log"
}

pid_path() {
  echo "${STAGING}/logs/${JOB_KEY}.pid"
}

# 进度日志超过 32MB 时只留末尾约 256KB，再交给后续追加。
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

read_pid() {
  local pf
  pf="$(pid_path)"
  [[ -f "$pf" ]] || return 1
  tr -d '[:space:]' < "$pf"
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

cmd_status() {
  local pf pid
  pf="$(pid_path)"
  echo "key:     ${JOB_KEY}"
  echo "log:     $(log_path)"
  echo "pidfile: ${pf}"
  echo "books:   ${ROOT}/data/level2_parquet"
  echo "factors: ${STAGING}/factors"
  if pid="$(read_pid 2>/dev/null)" && is_running "$pid"; then
    echo "status:  running (pid=${pid})"
    ps -p "$pid" -o pid=,etime=,pcpu=,command= 2>/dev/null || true
    return 0
  fi
  echo "status:  not running"
  return 1
}

cmd_tail() {
  local lf
  lf="$(log_path)"
  mkdir -p "${STAGING}/logs"
  touch "$lf"
  tail -f "$lf"
}

cmd_stop() {
  local pid
  pid="$(read_pid 2>/dev/null)" || die "无 pid 文件: $(pid_path)"
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

cmd_run_foreground() {
  [[ -x "$PY" ]] || die "未找到 python: $PY"
  cd "$ROOT"
  exec "$PY" -m app.services.level2_ingest.baidu_factor_pipeline "$@"
}

cmd_start() {
  [[ -x "$PY" ]] || die "未找到 python: $PY"

  if pid="$(read_pid 2>/dev/null)" && is_running "$pid"; then
    die "已在运行 pid=${pid}，先 stop 或删 pid 文件"
  fi

  mkdir -p "${STAGING}/logs"
  local lf pf
  lf="$(log_path)"
  pf="$(pid_path)"
  trim_log "$lf"

  export ROOT PY LF="$lf" PF="$pf"
  export PIPELINE_ARGS
  if (($# > 0)); then
    PIPELINE_ARGS="$(printf '%s\n' "$@")"
  else
    PIPELINE_ARGS=""
  fi
  PIPELINE_ARGS="$PIPELINE_ARGS" \
    "$PY" - <<'PY'
import os
import subprocess
from pathlib import Path

root = Path(os.environ["ROOT"])
py = Path(os.environ["PY"])
log = Path(os.environ["LF"])
pidf = Path(os.environ["PF"])
extra = [ln for ln in os.environ.get("PIPELINE_ARGS", "").splitlines() if ln]

cmd = [str(py), "-m", "app.services.level2_ingest.baidu_factor_pipeline", *extra]

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

  echo "tail:   ./scripts/run_level2_baidu_factors.sh tail"
  echo "status: ./scripts/run_level2_baidu_factors.sh status"
}

main() {
  [[ $# -ge 1 ]] || { usage; exit 1; }

  case "$1" in
    status)
      cmd_status
      return
      ;;
    tail)
      cmd_tail
      return
      ;;
    stop)
      cmd_stop
      return
      ;;
    -h|--help|help)
      usage
      return
      ;;
  esac

  local start_date="" end_date=""
  local pipeline_args=()
  local do_start=0
  local foreground=1

  while (($# > 0)); do
    case "$1" in
      --start)
        [[ $# -ge 2 ]] || die "--start 需要日期"
        start_date="$2"
        pipeline_args+=(--start "$2")
        shift 2
        ;;
      --end)
        [[ $# -ge 2 ]] || die "--end 需要日期"
        end_date="$2"
        pipeline_args+=(--end "$2")
        shift 2
        ;;
      --download-workers|--workers|--books-dir|--output)
        [[ $# -ge 2 ]] || die "$1 需要参数"
        pipeline_args+=("$1" "$2")
        shift 2
        ;;
      --force|--dry-run|--mirror)
        pipeline_args+=("$1")
        shift
        ;;
      start)
        do_start=1
        foreground=0
        shift
        ;;
      status|tail|stop)
        die "status/tail/stop 请单独调用，不要与 --start/--end 混用"
        ;;
      -h|--help|help)
        usage
        return
        ;;
      *)
        die "未知参数: $1"
        ;;
    esac
  done

  [[ -n "$start_date" ]] || die "需要 --start YYYYMMDD"
  [[ -n "$end_date" ]] || die "需要 --end YYYYMMDD"
  validate_date "$start_date"
  validate_date "$end_date"

  if (( do_start )); then
    cmd_start "${pipeline_args[@]}"
  elif (( foreground )); then
    cmd_run_foreground "${pipeline_args[@]}"
  fi
}

main "$@"
