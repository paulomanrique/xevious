"""Render the expected screen from core video shadow dumps (obj/md/dump_*.bin).

Reconstructs what the MD should display from fg/bg videoram+colorram shadows
using the same rules as convert_graphics_md.py / the OSD layer, and reports
anomalies (combos missing from the JSON logs, fg char/colour usage).
Output: obj/md/expected_screen.png (28x36 cells, arcade layout)
"""
import ast, json, os, re, sys, collections
from PIL import Image

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
amiga_dir = os.path.join(root, "assets", "amiga")
md_dir = os.path.join(root, "obj", "md")
sys.path.insert(0, os.path.join(root, "assets", "megadrive"))
from convert_graphics_md import parse_gfx_c, load_usage, md_round, TITLE_TILES

def load(name):
    with open(os.path.join(md_dir, name), "rb") as f:
        return f.read()

fgv, fgc = load("dump_fgv.bin"), load("dump_fgc.bin")
bgv, bgc = load("dump_bgv.bin"), load("dump_bgc.bin")

gfx = parse_gfx_c(os.path.join(amiga_dir, "xevious_gfx.c"))
palette = [tuple(c) for c in gfx["palette"]]
bg_cluts = gfx["bg_tile_clut"]
bg_tiles = gfx["bg_tile"]
fg_tiles = gfx["fg_tile"]
bg_usage = load_usage(os.path.join(amiga_dir, "bg_tile_clut.json"))

W, H = 28, 36   # visible cells (arcade)
img = Image.new("RGB", (W * 8, H * 8), (0, 0, 0))

missing = collections.Counter()
fg_used = collections.Counter()

for col in range(32):
    for row in range(64):
        off = col * 64 + row
        scol = (29 - col) & 31          # mirrored screen column
        if scol >= W:
            continue
        # ---- bg ----
        if 0 <= row < 64:
            code = bgv[off]
            attr = bgc[off]
            code9 = code | ((attr & 1) << 8)
            clut = ((attr >> 2) & 0x0F) | ((code & 0x80) >> 3) | ((attr & 3) << 5)
            known = clut in bg_usage.get(code9, [])
            if not known and (code9, clut) != (0, 0):
                missing[(code9, clut)] += 1
            # render bg cell only for visible fg-aligned area below
        # ---- draw (only the 36 visible rows: fg rows 4..39; bg row = fg row - 11 + scroll/8...) ----

# simpler: render the full fg layer (rows 4..39) and the aligned bg with scroll
SCROLL = 0x0004
def bg_cell(row, col):
    off = (col * 64 + row) & 0x7FF
    code = bgv[off]
    attr = bgc[off]
    code9 = code | ((attr & 1) << 8)
    clut = ((attr >> 2) & 0x0F) | ((code & 0x80) >> 3) | ((attr & 3) << 5)
    fx = (attr >> 6) & 1
    fy = (attr >> 7) & 1
    return code9, clut, fx, fy

for srow in range(H):                  # screen rows 0..35 (= fg rows 4..39)
    for scol in range(W):
        col = (29 - scol) & 31
        # bg row aligned with this screen row: b = f - 11 - S/8 (f = fg row)
        f = srow + 4
        b = (f - 11 - (SCROLL >> 3)) & 63
        code9, clut, fx, fy = bg_cell(b, col)
        tile = bg_tiles[code9]
        cl = bg_cluts[clut]
        for y in range(8):
            for x in range(8):
                px = tile[(7 - y if fy else y) * 8 + (7 - x if fx else x)]
                img.putpixel((scol * 8 + x, srow * 8 + y), md_round(palette[cl[px]]))
        # fg overlay
        off = col * 64 + f
        ch = fgv[off]
        at = fgc[off]
        colr = at & 0x3F
        fg_used[(ch, colr)] += 1
        cfx = (at >> 6) & 1
        cfy = (at >> 7) & 1
        t = fg_tiles[ch]
        rgb = md_round(palette[colr & 0x7F]) if colr < 128 else (255, 255, 255)
        for y in range(8):
            for x in range(8):
                if t[(7 - y if cfy else y) * 8 + (7 - x if cfx else x)]:
                    img.putpixel((scol * 8 + x, srow * 8 + y), rgb)

img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
img.save(os.path.join(md_dir, "expected_screen.png"))
print("bg combos missing from JSON logs:", sum(missing.values()), "cells,",
      len(missing), "distinct:", list(missing)[:10])
print("top fg (char,colour):", fg_used.most_common(8))
