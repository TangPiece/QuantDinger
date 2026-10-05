#!/usr/bin/env bash
# 无 Homebrew 时，为 macOS arm64 的 pip lightgbm wheel 补齐 libomp。
# 用法: ./scripts/bootstrap_lightgbm_libomp_macos.sh [python]
set -euo pipefail

PY="${1:-python3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LGB_LIB="$("$PY" - <<'PY' 2>/dev/null || true
try:
    import lightgbm, pathlib
    print(pathlib.Path(lightgbm.__file__).parent / "lib")
except Exception:
    pass
PY
)"

if [[ -z "${LGB_LIB}" || ! -d "${LGB_LIB}" ]]; then
  LGB_LIB="$("$PY" - <<'PY'
import site, pathlib
for p in site.getsitepackages():
    cand = pathlib.Path(p) / "lightgbm" / "lib"
    if cand.is_dir():
        print(cand)
        break
else:
    raise SystemExit("lightgbm package not installed")
PY
)"
fi

if [[ -z "${LGB_LIB}" || ! -d "${LGB_LIB}" ]]; then
  echo "lightgbm lib dir not found for: $PY" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

URL="$(python3 - <<'PY'
import json, urllib.request
data = json.load(urllib.request.urlopen("https://formulae.brew.sh/api/formula/libomp.json"))
files = data["bottle"]["stable"]["files"]
for key in ("arm64_sequoia", "arm64_sonoma", "arm64_ventura", "arm64_tahoe"):
    if key in files:
        print(files[key]["url"])
        break
else:
    for k, v in files.items():
        if str(k).startswith("arm64"):
            print(v["url"])
            break
    else:
        raise SystemExit("no arm64 libomp bottle")
PY
)"

echo "Downloading libomp bottle..."
curl -fsSL -H "Authorization: Bearer QQ==" -o libomp.tar.gz "$URL"
mkdir -p extract
tar -xzf libomp.tar.gz -C extract
OMP_SRC="$(find extract -name 'libomp.dylib' | head -1)"
cp -f "$OMP_SRC" "$LGB_LIB/libomp.dylib"
install_name_tool -change '@rpath/libomp.dylib' '@loader_path/libomp.dylib' \
  "$LGB_LIB/lib_lightgbm.dylib" || true

"$PY" -c "import lightgbm; print('lightgbm OK', lightgbm.__version__)"
