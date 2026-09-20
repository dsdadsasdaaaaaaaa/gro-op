#!/usr/bin/env bash
# Archive GrowOp and upload it to TestFlight.
#
# One-time prerequisites (all in the browser / Xcode, a few minutes):
#   1. Paid Apple Developer Program membership on team BQ7RT338VC.
#   2. Xcode → Settings → Accounts → sign in with that Apple ID.
#   3. https://appstoreconnect.apple.com → Apps → "+" → New App:
#        Platform iOS, Name "GrowOp", Bundle ID com.levi.growop (register it there if asked), SKU growop.
#   4. Run this script. First upload takes ~5 min; then in App Store Connect → TestFlight
#      add yourself as an internal tester and install from the TestFlight app on your phone.
#
# Usage:  ios/scripts/testflight.sh            (bumps the build number automatically)
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_NUMBER=$(date +%Y%m%d%H%M)
ARCHIVE="build/GrowOp.xcarchive"

echo "▶ Archiving (build $BUILD_NUMBER)…"
xcodebuild -project GrowOp.xcodeproj -scheme GrowOp -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
  archive | grep -E "error:|warning: .*sign|ARCHIVE" || true

[ -d "$ARCHIVE" ] || { echo "Archive failed. Open GrowOp.xcodeproj in Xcode → Signing & Capabilities and fix signing first."; exit 1; }

echo "▶ Uploading to App Store Connect / TestFlight…"
xcodebuild -exportArchive -archivePath "$ARCHIVE" \
  -exportOptionsPlist scripts/ExportOptions.plist -exportPath build/export \
  -allowProvisioningUpdates | grep -E "error:|EXPORT|Upload" || true

echo "✅ Done. Check https://appstoreconnect.apple.com → GrowOp → TestFlight (processing takes a few minutes)."
