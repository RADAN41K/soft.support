#!/bin/bash
# Build .deb package for Ubuntu from PyInstaller binary.
# Usage: ./build-deb.sh [path-to-binary]
# Default binary: dist/SoftSupport
set -e

BINARY="${1:-dist/SoftSupport}"
VERSION=$(cat VERSION | tr -d '[:space:]')
PACKAGE="limansoft-support"
INSTALL_DIR=".local/softsupport"
ARCH="amd64"

if [ ! -f "$BINARY" ]; then
    echo "Error: binary not found: $BINARY"
    exit 1
fi

PKG_DIR="dist/${PACKAGE}_${VERSION}"
rm -rf "$PKG_DIR"

# Directory structure (installed to $HOME/.local/softsupport/)
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/_placeholder"

# Calculate installed size in KB
BINARY_SIZE=$(du -sk "$BINARY" | cut -f1)
ICON_SIZE=$(du -sk "assets/icon.png" | cut -f1)
INSTALLED_SIZE=$((BINARY_SIZE + ICON_SIZE))

# Control file
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE
Maintainer: LimanSoft <support@limansoft.com>
Homepage: https://limansoft.com
Depends: libgtk-3-0, libtk8.6, libtcl8.6, libx11-6, libxft2, libfontconfig1, libxss1, gnome-shell-extension-appindicator, gir1.2-ayatanaappindicator3-0.1
Description: LimanSoft Support - tech support utility
 Cross-platform tech support tool for retail locations.
EOF

# Copyright file (required for App Center)
mkdir -p "$PKG_DIR/usr/share/doc/$PACKAGE"
cat > "$PKG_DIR/usr/share/doc/$PACKAGE/copyright" << EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: LimanSoft Support
Upstream-Contact: support@limansoft.com

Files: *
Copyright: $(date +%Y) LimanSoft
License: Proprietary
 All rights reserved.
EOF

# Post-install: copy to user home, create desktop shortcut, autostart
cat > "$PKG_DIR/DEBIAN/postinst" << 'SCRIPT'
#!/bin/bash
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")
INSTALL_DIR="$REAL_HOME/.local/softsupport"
DESKTOP_DIR="$REAL_HOME/Desktop"
AUTOSTART_DIR="$REAL_HOME/.config/autostart"

# Copy binary
mkdir -p "$INSTALL_DIR"
cp /opt/_placeholder/SoftSupport "$INSTALL_DIR/"
cp /opt/_placeholder/icon.png "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/SoftSupport"

# Desktop shortcut
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/SoftSupport.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=LimanSoft Support
Comment=LimanSoft Tech Support
Exec=$INSTALL_DIR/SoftSupport
Icon=$INSTALL_DIR/icon.png
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESKTOP_DIR/SoftSupport.desktop"

# App launcher (shows in taskbar search and allows pinning)
cp "$DESKTOP_DIR/SoftSupport.desktop" /usr/share/applications/softsupport.desktop

# Autostart
mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_DIR/SoftSupport.desktop" "$AUTOSTART_DIR/"

# Fix ownership
chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
chown "$REAL_USER:$REAL_USER" "$DESKTOP_DIR/SoftSupport.desktop"
chown "$REAL_USER:$REAL_USER" "$AUTOSTART_DIR/SoftSupport.desktop"

# Mark desktop shortcut as trusted (GNOME 42+ / Ubuntu 22.04+)
REAL_UID=$(id -u "$REAL_USER")
if command -v gio &> /dev/null && [ -S "/run/user/$REAL_UID/bus" ]; then
    sudo -u "$REAL_USER" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_UID/bus" \
        gio set "$DESKTOP_DIR/SoftSupport.desktop" "metadata::trusted" "true" 2>/dev/null || true
fi

# Enable tray icon extension (GNOME)
if command -v gnome-extensions &> /dev/null && [ -S "/run/user/$REAL_UID/bus" ]; then
    sudo -u "$REAL_USER" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_UID/bus" \
        gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
fi

# Cleanup placeholder
rm -rf /opt/_placeholder
echo "LimanSoft Support installed to $INSTALL_DIR"
echo "NOTE: re-login required for tray icon on first install"
SCRIPT
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# Post-remove: cleanup
cat > "$PKG_DIR/DEBIAN/postrm" << 'SCRIPT'
#!/bin/bash
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")
rm -rf "$REAL_HOME/.local/softsupport"
rm -f "$REAL_HOME/Desktop/SoftSupport.desktop"
rm -f "$REAL_HOME/.config/autostart/SoftSupport.desktop"
rm -f /usr/share/applications/softsupport.desktop
echo "LimanSoft Support removed"
SCRIPT
chmod 755 "$PKG_DIR/DEBIAN/postrm"

# Copy binary and icon to placeholder
cp "$BINARY" "$PKG_DIR/opt/_placeholder/SoftSupport"
cp "assets/icon.png" "$PKG_DIR/opt/_placeholder/icon.png"
chmod 755 "$PKG_DIR/opt/_placeholder/SoftSupport"

# Build .deb
dpkg-deb --build "$PKG_DIR" "dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
rm -rf "$PKG_DIR"
echo "Done: dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
