# Fetelabs Desktop

A complete dark desktop theme in Fetelabs colours for Zorin OS, Linux Mint and other GTK desktops.

| Part | Name | What it covers |
|---|---|---|
| Apps + shell | `Fetelabs-Desktop` | GTK 2, GTK 3, GTK 4 / libadwaita, GNOME Shell, Cinnamon, Metacity, Xfwm4 (plus `-hdpi` and `-xhdpi` window borders), Plank, labwc |
| Icons | `Fetelabs-Desktop` | Full icon set. Teal folders and accents, and it works without any other icon theme installed |
| Cursors | `Fetelabs-Desktop-Cursors` | Dark cursors with teal accents |

The palette comes from the Fetelabs brand kit: ink `#0E0818`, glass `#2A1F3D`, cream `#FFF6E6`,
teal `#1FB5A8` (accent), lime `#9BE22D` (success), Soca Pink `#FF2E88` (close and destructive
buttons), gold `#F4B400` (warnings). Window buttons are Soca Pink, gold and lime.

## Install

Download `fetelabs-desktop-<version>.tar.xz` from the releases page, then:

```sh
tar xf fetelabs-desktop-*.tar.xz
cd fetelabs-desktop-*/
./install.sh                     # for your user, and make it the default look
./install.sh --system            # for every user (asks for sudo)
./install.sh --with-extensions   # also add Fetelabs Task Bar, Water Panel built in (GNOME 46+)
```

`install.sh` works out which desktop you're on (GNOME, Cinnamon, MATE or Xfce) and sets the app
theme, shell theme, window borders, icons and cursors. It also points libadwaita apps at the
theme through `~/.config/gtk-4.0` and gives Flatpak apps read access to it.

On Wayland, log out and back in once afterwards.

### Keeping it applied

The installer starts a small guard. If Zorin Appearance, Mint's Themes tool or a light/dark toggle
changes the look, the guard puts Fetelabs Desktop back.

```sh
fetelabs-desktop status      # what is set and whether it matches
fetelabs-desktop apply       # set everything again
fetelabs-desktop guard-off   # stop the guard so you can pick another theme
```

To remove everything, run `./uninstall.sh`. Any GTK 4 files the installer replaced are put back.

## Taskbar and visualizer (GNOME)

On GNOME the theme is made to run with **Fetelabs Task Bar**, a floating taskbar with **Water Panel**
built in (the bar doubles as a liquid music visualizer; tune or turn it off on the Water tab of its
settings). It is in `extensions/`, and `--with-extensions` installs it. The visualizer needs
`python3-numpy` and `pulseaudio-utils`. Water Panel on its own, for Zorin Taskbar or Dash to Panel,
is on extensions.gnome.org and fetelabs.ai.

The upstream shell theme forced the top bar to 28px. Any taskbar that reuses the GNOME panel
(Fetelabs Task Bar, Zorin Taskbar, Dash to Panel) sits in that same panel, so its background and
icons came apart. Fetelabs Desktop drops that rule and styles the taskbar's hover, focus and badge
states in the brand colours.

## Build from source

```sh
python3 build.py              # -> dist/themes, dist/icons and dist/fetelabs-desktop-<version>.tar.xz
python3 build.py --no-package
```

`upstream/` holds pristine copies of the projects this is forked from, and `build.py` never edits
them. The script runs every colour through one brand mapping (`fl_color`), adds the Fetelabs
layers from `src/`, renames everything to Fetelabs Desktop, merges the icons into one standalone
theme and recolours the Xcursor files. Requires Python 3 with Pillow, plus `rsync` and
`gtk-update-icon-cache`.

## Credits and licence

Fetelabs Desktop is a fork. See [CREDITS.md](CREDITS.md). The app and shell theme is GPL-3.0. The
icons and cursors are LGPL-3.0. Full texts are in `licenses/`.

By Fetelabs: [fetelabs.ai](https://fetelabs.ai) · X [@mostlyjola](https://x.com/mostlyjola) · Instagram [@fetelabs](https://instagram.com/fetelabs)
