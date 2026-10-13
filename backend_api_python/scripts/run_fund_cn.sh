#!/usr/bin/env bash
# fund_cn_basic@v1 runner — staging / coverage / pit / compute / catalog
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export QUANTDINGER_SKIP_APP_INIT="${QUANTDINGER_SKIP_APP_INIT:-1}"
exec python -m app.services.research_data.fund_cn "$@"
