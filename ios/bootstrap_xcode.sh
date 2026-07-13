#!/usr/bin/env bash
# Bootstrap an Xcode project for Forge Desk (macOS + Xcode required).
set -euo pipefail
cd "$(dirname "$0")"

if command -v xcodegen >/dev/null 2>&1; then
  echo "Generating ForgeDesk.xcodeproj with XcodeGen…"
  xcodegen generate
  echo "Open: open ForgeDesk.xcodeproj"
  exit 0
fi

echo "XcodeGen not found."
echo "Install: brew install xcodegen"
echo "Or create a new iOS App in Xcode named ForgeDesk, then add all files under ios/ForgeDesk/."
exit 1
