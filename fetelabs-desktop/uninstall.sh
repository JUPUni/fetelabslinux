#!/usr/bin/env bash
# Remove Fetelabs Desktop for this user and restore the GTK 4 files it replaced.
set -uo pipefail
systemctl --user disable --now fetelabs-desktop-guard.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/fetelabs-desktop-guard.service" "$HOME/.config/autostart/fetelabs-desktop-guard.desktop"
pkill -f "fetelabs-desktop guard" 2>/dev/null
D="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$D"/themes/Fetelabs-Desktop{,-hdpi,-xhdpi} "$D"/icons/Fetelabs-Desktop{,-Cursors}
# The link GNOME Shell needs to find the cursors, and the default cursor pointer.
[ -L "$HOME/.icons/Fetelabs-Desktop-Cursors" ] && rm "$HOME/.icons/Fetelabs-Desktop-Cursors"
grep -qs "Inherits=Fetelabs-Desktop-Cursors" "$HOME/.icons/default/index.theme" && rm "$HOME/.icons/default/index.theme"
G4="$HOME/.config/gtk-4.0"
for f in gtk.css gtk-dark.css assets; do
  if [ -L "$G4/$f" ] && readlink "$G4/$f" | grep -q Fetelabs-Desktop; then rm "$G4/$f"; fi
  [ -e "$G4/$f.before-fetelabs" ] && mv "$G4/$f.before-fetelabs" "$G4/$f"
done
rm -f "$HOME/.local/bin/fetelabs-desktop"
for k in gtk-theme icon-theme cursor-theme; do gsettings reset org.gnome.desktop.interface $k 2>/dev/null; done
gsettings reset org.gnome.shell.extensions.user-theme name 2>/dev/null
for k in gtk-theme icon-theme cursor-theme; do gsettings reset org.cinnamon.desktop.interface $k 2>/dev/null; done
gsettings reset org.cinnamon.theme name 2>/dev/null
echo "Fetelabs Desktop removed; your desktop's default theme is back."
