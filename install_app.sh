#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Chain Gambler — Install as macOS App
# Copies the .app bundle to /Applications for dock/spotlight launch
# ═══════════════════════════════════════

APP_NAME="ChainGambler"
SOURCE_APP="$(cd "$(dirname "$0")" && pwd)/${APP_NAME}.app"
DEST_APP="/Applications/${APP_NAME}.app"

if [ ! -d "$SOURCE_APP" ]; then
    echo "ERROR: ${APP_NAME}.app not found in project directory."
    exit 1
fi

# Remove old copy if exists
if [ -d "$DEST_APP" ]; then
    echo "Removing old copy in /Applications..."
    rm -rf "$DEST_APP"
fi

# Copy to Applications
echo "Installing Chain Gambler to /Applications..."
cp -R "$SOURCE_APP" "$DEST_APP"

# Sign the app with an ad-hoc signature (required for Gatekeeper on macOS)
codesign --force --deep --sign - "$DEST_APP" 2>/dev/null || true

echo ""
echo "Done! You can now:"
echo "  • Press Cmd+Space and type 'Chain Gambler' to launch"
echo "  • Drag ${APP_NAME}.app to the Dock for one-click access"
echo "  • Right-click the Dock icon → Options → Keep in Dock"
echo ""
echo "To uninstall: rm -rf /Applications/${APP_NAME}.app"
