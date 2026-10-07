# Phase 7 — Controlled Live

> **Status:** Phase 7A + 7B + 7C implemented (read-only Live + Shadow + single controlled order).

## Roadmap

```text
7A  Live Adapter / Read-only Production   ← done
7B  Live Shadow                           ← done
7C  Single Order                           ← done
7D  Controlled Live
7E  Gradual Scale
```

## Reading

1. [01_live_readonly.md](01_live_readonly.md)
2. [02_live_shadow.md](02_live_shadow.md)
3. [03_controlled_live.md](03_controlled_live.md)

## Commands

```bash
cd backend_api_python

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7a_live_readonly.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7a_live_readonly.py -q
```

Optional real Alpaca Live **GET** smoke (requires `PRODUCTION_READY=true` and `ALPACA_LIVE_*`):

```bash
export PRODUCTION_READY=true
export ALPACA_LIVE_API_KEY=...
export ALPACA_LIVE_API_SECRET=...
export ALPACA_LIVE_BASE_URL=https://api.alpaca.markets
```

Phase 7B Shadow + Live MD（Fake 默认；真实 Data GET 需同组 `ALPACA_LIVE_*`）：

```bash
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7b_shadow_trading.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7b_shadow_trading.py -q \
  --confcutdir=tests/research_data
```

Data host（与 Trading 同钥）：`ALPACA_LIVE_DATA_URL=https://data.alpaca.markets`

Phase 7C Controlled Live（Fake broker 默认；真实 POST opt-in）：

```bash
QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python scripts/verify_phase7c_controlled_live.py

QUANTDINGER_SKIP_APP_INIT=1 \
  .test_deps/py312/bin/python -m pytest tests/research_data/test_phase7c_controlled_live.py -q \
  --confcutdir=tests/research_data
```

Opt-in 真实 Alpaca **POST**（默认 skip）：

```bash
export PRODUCTION_READY=true
export CONTROLLED_LIVE_ALLOW_REAL_SUBMIT=true
export ALPACA_LIVE_API_KEY=...
export ALPACA_LIVE_API_SECRET=...
```
