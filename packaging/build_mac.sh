#!/bin/bash
# Builds RSC.app and RSC-<version>.dmg. Run on a Mac (GitHub Actions does this: .github/workflows/mac-app.yml).
#   ./packaging/build_mac.sh            -> dist/RSC.app and dist/RSC-<version>.dmg
# The app is signed "ad hoc" (no Apple Developer ID), so Nick opens it once with right-click > Open (docs/mac-app.md).
set -Eeuo pipefail
cd "$(dirname "$0")/.."
VERSION="$(sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -1)"
PY="${PYTHON:-python3}"
rm -rf build dist .build-venv
"$PY" -m venv .build-venv
. .build-venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet . pywebview pyinstaller pillow
python packaging/make_icon.py build/icon
pyinstaller --noconfirm --windowed --name RSC --icon build/icon/RSC.icns \
  --collect-data rsc --hidden-import rsc.web --osx-bundle-identifier com.reclaimedspacecrafters.app \
  packaging/rsc_app.py
codesign --force --deep --sign - dist/RSC.app
DMG_DIR="$(mktemp -d)"; cp -R dist/RSC.app "$DMG_DIR/"; ln -s /Applications "$DMG_DIR/Applications"
hdiutil create -volname "RSC" -srcfolder "$DMG_DIR" -ov -format UDZO "dist/RSC-$VERSION.dmg"
echo "Built dist/RSC.app and dist/RSC-$VERSION.dmg"
