#!/usr/bin/env bash
# Fetelabs Desktop installer: Zorin OS / GNOME, Linux Mint (Cinnamon, MATE, Xfce) and friends.
#
#   ./install.sh                     install for this user and make it the default look
#   ./install.sh --system            install into /usr/share for every user (asks for sudo)
#   ./install.sh --with-extensions   also install Fetelabs Task Bar, Water Panel built in (GNOME 46+)
#   ./install.sh --no-guard          do not keep the theme enforced after install
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SYSTEM=0 EXTENSIONS=0 GUARD=1
for a in "$@"; do
  case "$a" in
    --system) SYSTEM=1 ;;
    --with-extensions) EXTENSIONS=1 ;;
    --no-guard) GUARD=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 1 ;;
  esac
done

say() { printf '\033[38;2;31;181;168m▸\033[0m %s\n' "$*"; }

if [ "$SYSTEM" = 1 ]; then
  THEMES=/usr/share/themes ICONS=/usr/share/icons SUDO=sudo
else
  THEMES="${XDG_DATA_HOME:-$HOME/.local/share}/themes"
  ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons"
  SUDO=
fi
$SUDO mkdir -p "$THEMES" "$ICONS"

for t in "$HERE"/themes/*; do
  say "theme  $(basename "$t") -> $THEMES"
  $SUDO rm -rf "$THEMES/$(basename "$t")"
  $SUDO cp -a "$t" "$THEMES/"
done
for i in "$HERE"/icons/*; do
  say "icons  $(basename "$i") -> $ICONS"
  $SUDO rm -rf "$ICONS/$(basename "$i")"
  $SUDO cp -a "$i" "$ICONS/"
done
if command -v gtk-update-icon-cache >/dev/null; then
  $SUDO gtk-update-icon-cache -q -f -t "$ICONS/Fetelabs-Desktop" || true
fi

BIN="$HOME/.local/bin"
mkdir -p "$BIN"
install -m 755 "$HERE/bin/fetelabs-desktop" "$BIN/fetelabs-desktop"
say "command $BIN/fetelabs-desktop"

if [ "$EXTENSIONS" = 1 ]; then
  if command -v gnome-extensions >/dev/null && [ -d "$HERE/extensions" ]; then
    for z in "$HERE"/extensions/*.zip; do
      say "extension $(basename "$z" .shell-extension.zip)"
      gnome-extensions install --force "$z"
    done
    say "extensions installed; enable Fetelabs Task Bar after logging back in (Extensions app)"
  else
    say "skipping extensions (needs GNOME Shell 46+)"
  fi
fi

"$BIN/fetelabs-desktop" apply

if [ "$GUARD" = 1 ]; then
  desk="${XDG_CURRENT_DESKTOP:-}"
  if [[ "$desk" == *GNOME* ]] && systemctl --user show-environment >/dev/null 2>&1; then
    mkdir -p "$HOME/.config/systemd/user"
    install -m 644 "$HERE/packaging/fetelabs-desktop-guard.service" "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
    systemctl --user enable --now fetelabs-desktop-guard.service >/dev/null 2>&1 || true
    say "guard: systemd user service (fetelabs-desktop guard-off to stop)"
  else
    mkdir -p "$HOME/.config/autostart"
    install -m 644 "$HERE/packaging/fetelabs-desktop-guard.desktop" "$HOME/.config/autostart/"
    nohup "$BIN/fetelabs-desktop" guard >/dev/null 2>&1 &
    say "guard: runs at login (remove ~/.config/autostart/fetelabs-desktop-guard.desktop to stop)"
  fi
fi

say "Fetelabs Desktop is on. Apps opened before now pick it up after a restart of the app;"
say "on Wayland, log out and back in once so every part of the shell reloads."
