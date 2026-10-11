#!/usr/bin/env bash
# L2 百因子并行链路：明细 → factors/l2_daily Parquet（+可选 R2）+ D1 元数据。
# 不写入旧热表 l2_factors，不影响图表读侧。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -n "${LEVEL2_PYTHON:-}" && -x "${LEVEL2_PYTHON}" ]]; then
  PY="${LEVEL2_PYTHON}"
else
  PY="$(command -v python3)"
fi
export QUANTDINGER_SKIP_APP_INIT=1

usage() {
  cat <<'USAGE'
用法:
  run_level2_l2_daily.sh DATE [选项]
  run_level2_l2_daily.sh --start YYYYMMDD --end YYYYMMDD [选项]

选项:
  --groups trade,book,order,microstructure
  --parquet-dir DIR
  --output DIR
  --force
  --no-r2
  --no-compact
  --no-seed

示例:
  ./scripts/run_level2_l2_daily.sh 20261009
  ./scripts/run_level2_l2_daily.sh --start 20261001 --end 20261009 --groups trade
  ./scripts/run_level2_l2_daily.sh 20261009 --force --no-r2
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

ARGS=()
if [[ "$1" =~ ^[0-9]{8}$ ]]; then
  ARGS+=(--dates "$1")
  shift
fi

ARGS+=("$@")
cd "${ROOT}"
exec "${PY}" -m app.services.level2_factors.l2_daily "${ARGS[@]}"
