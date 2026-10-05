#!/usr/bin/env python3
"""百度网盘 OAuth：用授权码换 token，写入 backend 的 .env。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.level2_ingest import baidu_client, config  # noqa: E402


def _extract_code(raw: str) -> str:
    raw = raw.strip()
    if "code=" in raw:
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        codes = qs.get("code") or []
        if codes:
            return codes[0]
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baidu OAuth (callback: ivip.site)")
    parser.add_argument(
        "--code",
        help="Auth code or full callback URL (https://www.ivip.site/?code=...)",
    )
    args = parser.parse_args(argv)

    if not config.BAIDU_APP_KEY or not config.BAIDU_SECRET_KEY:
        print("Set BAIDU_APP_KEY and BAIDU_SECRET_KEY in .env first")
        return 2

    url = baidu_client.build_authorize_url()
    print("Open this URL in browser (Cursor: Cmd+Shift+P -> Simple Browser: Show):")
    print()
    print(url)
    print()
    print(f"After auth you will land on {config.BAIDU_REDIRECT_URI}?code=...")
    print("Copy the code query param (or paste full URL) below.")
    print()

    code_raw = args.code
    if not code_raw:
        try:
            code_raw = input("Paste code or callback URL: ").strip()
        except EOFError:
            print("No code provided")
            return 1

    code = _extract_code(code_raw)
    if not code:
        print("Could not parse authorization code")
        return 1

    data = baidu_client.exchange_code(code)
    print("Success. Tokens written to .env:")
    print(f"  access_token: {data['access_token'][:16]}...")
    if data.get("refresh_token"):
        print(f"  refresh_token: {data['refresh_token'][:16]}...")
    if data.get("expires_in"):
        print(f"  expires_in: {data['expires_in']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
