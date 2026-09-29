#!/usr/bin/env python3
"""Build Fetelabs Desktop from the vendored upstream sources in ./upstream.

Outputs (in ./dist):
  themes/Fetelabs-Desktop[-hdpi|-xhdpi]   apps (GTK 2/3/4), GNOME Shell, Cinnamon, Metacity, Xfwm4, Plank, labwc
  icons/Fetelabs-Desktop                  icons (self-contained; falls back to Adwaita/hicolor for icons Breeze never drew)
  icons/Fetelabs-Desktop-Cursors          cursors (Xcursor)
  fetelabs-desktop-<version>.tar.xz       everything above + install.sh, ready to ship

Every colour goes through one brand mapping (fl_color). Upstream is never edited, so
a rebuild always starts from the same pristine sources.
"""
import colorsys
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

from PIL import Image

VERSION = "1.1.2"
ROOT = Path(__file__).resolve().parent
UP = ROOT / "upstream"
SRC = ROOT / "src"
DIST = ROOT / "dist"

NAME = "Fetelabs-Desktop"
PRETTY = "Fetelabs Desktop"
ICONS = "Fetelabs-Desktop"
CURSORS = "Fetelabs-Desktop-Cursors"

# Fetelabs brand kit (brand/kit/colour/fetelabs-colours.css)
BRAND = {
    "ink": "#0E0818", "glass": "#2A1F3D", "cream": "#FFF6E6", "teal": "#1FB5A8",
    "lime": "#9BE22D", "soca_pink": "#FF2E88", "gold": "#F4B400",
}
H_TEAL, H_PINK, H_GOLD, H_LIME, H_GLASS, H_CREAM = 174, 334, 44, 84, 263, 38

TEXT_EXT = {".css", ".svg", ".rc", ".xml", ".json", ".xpm", ".theme", ".ini", ".xbm"}
TEXT_NAMES = {"gtkrc", "themerc", "dock.theme", "index.theme"}


# ---------------------------------------------------------------- colour maths

def _hls(h, l, s):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, max(0, min(1, l)), max(0, min(1, s)))
    return round(r * 255), round(g * 255), round(b * 255)


def fl_color(r, g, b, mode="ui"):
    """Map one upstream colour onto the Fetelabs palette.

    ui:    blues -> teal accent, reds -> Soca Pink, orange/yellow -> gold, greens -> lime,
           dark neutrals -> ink/glass violet, light greys -> cream. Pure white/black stay.
    icons: only the Breeze blue family -> teal (folders, highlights, spinners).
    """
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    hd = h * 360
    chroma = s >= 0.25 and 0.06 < l < 0.97
    if chroma and 185 <= hd <= 250:
        # accent: darker than upstream blue so white text on it stays readable
        l2 = l * 0.74 if l <= 0.5 else 0.37 + (l - 0.5) * (0.63 / 0.5)
        return _hls(H_TEAL, l2, min(1.0, s * 0.82))
    if mode == "icons":
        return r, g, b
    if chroma:
        if hd < 15 or hd >= 345:
            return _hls(H_PINK, l, max(s, 0.8))
        if 15 <= hd < 55:
            return _hls(H_GOLD, l, s)
        if 70 <= hd < 165:
            return _hls(H_LIME, l, s)
        return r, g, b
    if s < 0.12:
        if l <= 0.004 or l >= 0.995:
            return r, g, b
        if l < 0.40:
            return _hls(H_GLASS, l, 0.20)
        if l < 0.75:
            return _hls(H_GLASS, l, 0.07)
        return _hls(H_CREAM, l, 0.30)
    return r, g, b


HEX_RE = re.compile(r'(?<![\w&])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![\w-])')
RGB_RE = re.compile(r'\brgb(a?)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(,\s*[\d.]+\s*)?\)')
# a "#abc" right after these is an id reference, not a colour
ID_CONTEXT = re.compile(r'(url\(\s*|href="|href=\'|xlink:href="|begin="|id=")$')


def recolor_text(text, mode):
    def hex_sub(m):
        if ID_CONTEXT.search(text[max(0, m.start() - 12):m.start()]):
            return m.group(0)
        v = m.group(1)
        if len(v) == 3:
            rgb = tuple(int(c * 2, 16) for c in v)
            alpha = ""
        else:
            rgb = tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
            alpha = v[6:8]
        nr = fl_color(*rgb, mode=mode)
        if nr == rgb:
            return m.group(0)
        out = "#%02x%02x%02x" % nr + alpha
        return out if v.islower() or v.isdigit() else out.upper()

    def rgb_sub(m):
        rgb = tuple(int(x) for x in m.group(2, 3, 4))
        nr = fl_color(*rgb, mode=mode)
        if nr == rgb:
            return m.group(0)
        return "rgb%s(%d, %d, %d%s)" % (m.group(1), *nr, m.group(5) or "")

    # CSS selectors such as "#panel" never match (non-hex letters), but a selector like
    # "#fade" would; limit hex rewriting to declaration values in CSS.
    return RGB_RE.sub(rgb_sub, HEX_RE.sub(hex_sub, text))


# GNOME's named palette (blue_1 ... dark_5) must keep meaning what its name says
PALETTE_DEF = re.compile(r'@define-color\s+(blue|green|yellow|orange|red|purple|brown|light|dark)_\d\b')


def recolor_css(text, mode):
    # only rewrite inside { ... } blocks (values) and @define-color lines, never selectors
    out, depth = [], 0
    for part in re.split(r'([{}])', text):
        if part == "{":
            depth += 1
            out.append(part)
        elif part == "}":
            depth = max(0, depth - 1)
            out.append(part)
        elif depth > 0:
            out.append(recolor_text(part, mode))
        else:
            out.append(re.sub(
                r'(@define-color[^;]*;)',
                lambda m: m.group(1) if PALETTE_DEF.match(m.group(1)) else recolor_text(m.group(1), mode),
                part))
    return "".join(out)


_px_cache = {}


def recolor_png(path, mode):
    im = Image.open(path)
    fmt_mode = im.mode
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    changed = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            key = (r, g, b, mode)
            n = _px_cache.get(key)
            if n is None:
                n = _px_cache[key] = fl_color(r, g, b, mode)
            if n != (r, g, b):
                px[x, y] = (*n, a)
                changed = True
    if changed:
        if fmt_mode not in ("RGBA", "RGB", "LA", "L"):
            fmt_mode = "RGBA"
        im.convert(fmt_mode if fmt_mode in ("RGBA", "RGB") else "RGBA").save(path)


def recolor_tree(root, mode, skip_dirs=()):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in skip_dirs]
        for fn in fns:
            p = Path(dp) / fn
            if p.is_symlink():
                continue
            ext = p.suffix.lower()
            if ext == ".png":
                recolor_png(p, mode)
            elif ext in TEXT_EXT or fn in TEXT_NAMES:
                try:
                    t = p.read_text()
                except UnicodeDecodeError:
                    continue
                n = recolor_css(t, mode) if ext == ".css" else recolor_text(t, mode)
                if n != t:
                    p.write_text(n)


# ---------------------------------------------------------------- rebranding

def rebrand_text(t):
    t = t.replace("WhiteSur-cursors", CURSORS)
    t = re.sub(r"WhiteSur-Dark(-solid)?", NAME, t)
    t = re.sub(r"WhiteSur-Light(-solid)?", NAME, t)
    t = t.replace("WhiteSur", PRETTY)
    return t


def rebrand_tree(root):
    for p in Path(root).rglob("*"):
        if p.is_file() and not p.is_symlink() and (p.suffix in TEXT_EXT or p.name in TEXT_NAMES):
            try:
                t = p.read_text()
            except UnicodeDecodeError:
                continue
            n = rebrand_text(t)
            if n != t:
                p.write_text(n)


# ---------------------------------------------------------------- themes

THEME_INDEX = f"""[Desktop Entry]
Type=X-GNOME-Metatheme
Name={NAME}
Comment={PRETTY}: dark Fetelabs theme for GNOME (Zorin OS), Cinnamon (Linux Mint), MATE and Xfce
Encoding=UTF-8

[X-GNOME-Metatheme]
GtkTheme={NAME}
MetacityTheme={NAME}
IconTheme={ICONS}
CursorTheme={CURSORS}
ButtonLayout=menu:minimize,maximize,close
"""


def build_theme(variant_suffix=""):
    src = UP / "themes" / ("WhiteSur-Dark" + variant_suffix)
    dst = DIST / "themes" / (NAME + variant_suffix)
    shutil.copytree(src, dst, symlinks=True)
    recolor_tree(dst, "ui")
    rebrand_tree(dst)
    (dst / "index.theme").write_text(THEME_INDEX.replace(f"Name={NAME}", f"Name={NAME}{variant_suffix}", 1))
    if variant_suffix:
        return dst

    # GNOME Shell: remove the forced 28px top-bar height (it squashed the taskbar,
    # which reuses #panel at 40-64px), then append the Fetelabs layer.
    shell = dst / "gnome-shell" / "gnome-shell.css"
    css = shell.read_text()
    css, n = re.subn(r"(#panel \{[^}]*?)\n\s*height: 28px !important;", r"\1", css, count=1)
    if n != 1:
        sys.exit("build: could not find the #panel height rule to drop")
    shell.write_text(css + "\n" + (SRC / "gnome-shell" / "fetelabs.css").read_text())
    # Cinnamon (Linux Mint) gets its own Fetelabs layer too
    cin = dst / "cinnamon" / "cinnamon.css"
    cin.write_text(cin.read_text() + "\n" + (SRC / "cinnamon" / "fetelabs.css").read_text())
    # GTK 3/4: brand layer on top (accent names used by apps + libadwaita)
    for gv in ("gtk-3.0", "gtk-4.0"):
        layer = (SRC / "gtk" / f"fetelabs-{gv}.css").read_text()
        for f in ("gtk.css", "gtk-dark.css"):
            p = dst / gv / f
            p.write_text(p.read_text() + "\n" + layer)
    for f in ("thumbnail.png",):
        for gv in ("gtk-3.0", "gtk-4.0", "cinnamon"):
            if (SRC / "preview" / f).exists() and (dst / gv / f).exists():
                shutil.copy(SRC / "preview" / f, dst / gv / f)
    return dst


# ---------------------------------------------------------------- icons

def build_icons():
    dst = DIST / "icons" / ICONS
    base, dark = UP / "icons" / "breeze", UP / "icons" / "breeze-dark"
    shutil.copytree(base, dst, symlinks=True)
    # overlay breeze-dark on top of breeze (same as runtime inheritance, but self-contained)
    # breeze-dark links into ../../../breeze/... are "unsafe" (leave the tree): copy
    # their files in instead, so the result never depends on a Breeze install
    subprocess.run(["rsync", "-a", "--copy-unsafe-links", "--exclude", "index.theme",
                    f"{dark}/", f"{dst}/"], check=True)
    # dangling-link check
    bad = [p for p in dst.rglob("*") if p.is_symlink() and not p.exists()]
    if bad:
        sys.exit(f"build: {len(bad)} dangling icon links, e.g. {bad[0]}")
    for sub in ("places", "actions", "status", "emblems", "animations", "applets", "preferences", "categories"):
        if (dst / sub).exists():
            recolor_tree(dst / sub, "icons")
    # "Highlight" is Breeze's accent class; recolour it everywhere (mimetypes, devices...)
    for p in dst.rglob("*.svg"):
        if p.is_symlink():
            continue
        t = p.read_text(errors="ignore")
        if "ColorScheme-Highlight" in t or "#3daee9" in t.lower():
            n = recolor_text(t, "icons")
            if n != t:
                p.write_text(n)
    # icons GNOME/Zorin ask for that Breeze never had (e.g. the desktop-icons stack emblem)
    for extra in (SRC / "icons").rglob("*.svg"):
        ctx = extra.parent.name
        for size in ("16", "22"):
            d = dst / ctx / size
            if d.is_dir() and not (d / extra.name).exists():
                shutil.copy(extra, d / extra.name)
    # index.theme: union of both directory lists, one name
    def parse(path):
        secs, cur = {}, None
        for line in path.read_text().splitlines():
            if line.startswith("[") and line.endswith("]"):
                cur = line[1:-1]
                secs.setdefault(cur, [])
            elif cur:
                secs[cur].append(line)
        return secs
    a, b = parse(base / "index.theme"), parse(dark / "index.theme")
    def dirs(secs, key):
        for l in secs["Icon Theme"]:
            if l.startswith(key + "="):
                return [d for d in l.split("=", 1)[1].split(",") if d]
        return []
    alld = []
    for d in dirs(a, "Directories") + dirs(b, "Directories"):
        if d not in alld and (dst / d).exists():
            alld.append(d)
    scaled = []
    for d in dirs(a, "ScaledDirectories") + dirs(b, "ScaledDirectories"):
        if d not in scaled and (dst / d).exists():
            scaled.append(d)
    out = ["[Icon Theme]", f"Name={PRETTY} Icons",
           f"Comment=Dark Fetelabs icons for {PRETTY} (forked from Breeze Dark, LGPL-3.0)",
           "Inherits=Adwaita,hicolor", "DisplayDepth=32", "Example=folder",
           "FollowsColorScheme=true", "DesktopDefault=48", "DesktopSizes=16,22,32,48,64,128,256",
           "ToolbarDefault=22", "ToolbarSizes=16,22,32,48", "MainToolbarDefault=22",
           "MainToolbarSizes=16,22,32,48", "SmallDefault=16", "SmallSizes=16,22,32,48",
           "PanelDefault=48", "PanelSizes=16,22,32,48,64,128,256", "DialogDefault=32",
           "DialogSizes=16,22,32,48,64,128,256", "KDE-Extensions=.svg",
           "Directories=" + ",".join(alld)]
    if scaled:
        out.append("ScaledDirectories=" + ",".join(scaled))
    out.append("")
    for secs in (b, a):
        for name, lines in secs.items():
            if name == "Icon Theme" or name not in alld + scaled or f"[{name}]" in out:
                continue
            out.append(f"[{name}]")
            out += [l for l in lines if l.strip()]
            out.append("")
    (dst / "index.theme").write_text("\n".join(out))
    subprocess.run(["gtk-update-icon-cache", "-q", "-f", "-t", str(dst)], check=False)
    return dst


# ---------------------------------------------------------------- cursors

XC_MAGIC, XC_IMAGE = b"Xcur", 0xFFFD0002


def recolor_xcursor(path):
    data = bytearray(path.read_bytes())
    if data[:4] != XC_MAGIC:
        return False
    _, _, ntoc = struct.unpack_from("<III", data, 4)
    changed = False
    for i in range(ntoc):
        typ, _sub, pos = struct.unpack_from("<III", data, 16 + i * 12)
        if typ != XC_IMAGE:
            continue
        hdr, _t, _s, _v, w, h = struct.unpack_from("<IIIIII", data, pos)
        off = pos + hdr
        for k in range(w * h):
            o = off + k * 4
            v = struct.unpack_from("<I", data, o)[0]
            a = v >> 24
            if a == 0:
                continue
            # premultiplied ARGB
            r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
            ur, ug, ub = (min(255, round(c * 255 / a)) for c in (r, g, b))
            n = fl_color(ur, ug, ub, "ui")
            if n != (ur, ug, ub):
                nr, ng, nb = (round(c * a / 255) for c in n)
                struct.pack_into("<I", data, o, (a << 24) | (nr << 16) | (ng << 8) | nb)
                changed = True
    if changed:
        path.write_bytes(bytes(data))
    return changed


def build_cursors():
    dst = DIST / "icons" / CURSORS
    shutil.copytree(UP / "icons" / "breeze_cursors", dst, symlinks=True)
    for p in (dst / "cursors").iterdir():
        if not p.is_symlink():
            recolor_xcursor(p)
    (dst / "index.theme").write_text(
        f"[Icon Theme]\nName={PRETTY} Cursors\n"
        f"Comment=Dark Fetelabs cursors for {PRETTY} (forked from Breeze, LGPL-3.0)\n")
    (dst / "cursor.theme").write_text(f"[Icon Theme]\nInherits={CURSORS}\n")
    return dst


# ---------------------------------------------------------------- package

def package():
    pkg = f"fetelabs-desktop-{VERSION}"
    stage = DIST / pkg
    stage.mkdir()
    shutil.copytree(DIST / "themes", stage / "themes", symlinks=True)
    shutil.copytree(DIST / "icons", stage / "icons", symlinks=True)
    for f in ("install.sh", "uninstall.sh", "README.md", "CREDITS.md", "LICENSE"):
        shutil.copy(ROOT / f, stage / f)
    shutil.copytree(ROOT / "bin", stage / "bin", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "packaging", stage / "packaging")
    if (ROOT / "extensions").is_dir():
        shutil.copytree(ROOT / "extensions", stage / "extensions")
    shutil.copytree(UP / "licenses", stage / "licenses")
    tar = DIST / f"{pkg}.tar.xz"
    with tarfile.open(tar, "w:xz") as tf:
        tf.add(stage, arcname=pkg)
    shutil.rmtree(stage)
    return tar


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "themes").mkdir(parents=True)
    (DIST / "icons").mkdir(parents=True)
    for v in ("", "-hdpi", "-xhdpi"):
        print("theme ", build_theme(v).name)
    print("icons ", build_icons().name)
    print("cursor", build_cursors().name)
    if "--no-package" not in sys.argv:
        print("pkg   ", package().name)


if __name__ == "__main__":
    main()
