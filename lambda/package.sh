#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_DIR="$ROOT/build/lambda"

rm -rf "$PACKAGE_DIR" "$ROOT/build/lambda.zip"
mkdir -p "$PACKAGE_DIR"
python3 -m pip install --disable-pip-version-check \
  --platform manylinux2014_x86_64 \
  --python-version 3.12 \
  --implementation cp \
  --abi cp312 \
  --only-binary=:all: \
  --target "$PACKAGE_DIR" \
  -r "$ROOT/lambda/requirements.txt"
cp "$ROOT/lambda/handler.py" "$PACKAGE_DIR/"
cp -R "$ROOT/app" "$PACKAGE_DIR/app"
cp -R "$ROOT/frontend" "$PACKAGE_DIR/frontend"
find "$PACKAGE_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$PACKAGE_DIR" -type f -name '*.pyc' -delete
(cd "$PACKAGE_DIR" && zip -qr "$ROOT/build/lambda.zip" .)
