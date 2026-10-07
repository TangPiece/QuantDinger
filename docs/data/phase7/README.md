# Phase 7 — Controlled Live

> **Status:** Phase 7A implemented (read-only Live).

## Roadmap

```text
7A  Live Adapter / Read-only Production   ← done
7B  Live Shadow                           ← next
7C  Single Order
7D  Controlled Live
7E  Gradual Scale
```

## Reading

1. [01_live_readonly.md](01_live_readonly.md)

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
