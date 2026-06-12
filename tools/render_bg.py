"""Render the full bg plane (64 rows) from dumped shadows using the title or
game palette + patterns, exactly as the VDP would, to diagnose what shows."""
import os, re, sys, struct
from PIL import Image

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md = os.path.join(root, "obj", "md")
mddir = os.path.join(root, "src", "megadrive")

def load(n): return open(os.path.join(md, n), "rb").read()
def loadmd(n): return open(os.path.join(mddir, n), "rb").read()

bgv = load("dump_bgv.bin")
bgc = load("dump_bgc.bin")
combo = loadmd("gfx_bg_combo.bin")
game_pat = loadmd("gfx_bg_patterns.bin")
title_pat = loadmd("gfx_title_patterns.bin")

# parse equates + palettes from graphics_md.68k
g = open(os.path.join(mddir, "graphics_md.68k")).read()
def eq(name): return int(re.search(rf"\.equ {name}, (\d+)", g).group(1))
BG_BASE = eq("GFX_BG_BASE_TILE")
POOL_BASE = eq("GFX_POOL_BASE_TILE")

def cram_to_rgb(w):
    b = (w >> 9) & 7; gg = (w >> 5) & 7; r = (w >> 1) & 7
    return (r * 255 // 7, gg * 255 // 7, b * 255 // 7)

def parse_pal(label):
    # find the .word line(s) after the label
    m = re.search(rf"{label}:\s*\n((?:\s*\.word [^\n]+\n)+)", g)
    words = re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))
    return [cram_to_rgb(int(w, 16)) for w in words]

title_pal = parse_pal("gfx_palette_title")[:16]
# game palettes: PAL0 fg, PAL1 bg game (2nd line of gfx_palettes_game)
gp = re.search(r"gfx_palettes_game:\s*\n((?:\s*\.word[^\n]+\n)+)", g).group(1)
gp_lines = re.findall(r"\.word ([^\|\n]+)", gp)
def line_rgb(line): return [cram_to_rgb(int(x, 16)) for x in re.findall(r"0x([0-9A-Fa-f]{4})", line)]
pal1_game = line_rgb(gp_lines[1])

def tile_pixels(tile_idx):
    if tile_idx >= POOL_BASE:
        data = title_pat; off = (tile_idx - POOL_BASE) * 32
    else:
        data = game_pat; off = (tile_idx - BG_BASE) * 32
    if off < 0 or off + 32 > len(data):
        return [0] * 64
    px = []
    for b in data[off:off + 32]:
        px += [b >> 4, b & 0x0F]
    return px

def render(pal, fname):
    img = Image.new("RGB", (32 * 8, 64 * 8), (0, 0, 0))
    for col in range(32):
        for row in range(64):
            off = col * 64 + row
            code = bgv[off]; attr = bgc[off]
            code9 = code | ((attr & 1) << 8)
            clut = ((attr >> 2) & 0x0F) | ((code & 0x80) >> 3) | ((attr & 3) << 5)
            idx = (clut << 9) | code9
            word = (combo[idx * 2] << 8) | combo[idx * 2 + 1]
            if word == 0:
                continue
            tile = word & 0x7FF
            hf = (word >> 11) & 1; vf = (word >> 12) & 1
            px = tile_pixels(tile)
            # screen col uses reversal; here just lay rows down, cols across as stored
            for y in range(8):
                for x in range(8):
                    sx = 7 - x if hf else x
                    sy = 7 - y if vf else y
                    v = px[sy * 8 + sx]
                    img.putpixel((col * 8 + x, row * 8 + y), pal[v])
    img.save(os.path.join(md, fname))
    print("wrote", fname)

render(title_pal, "bg_full_title.png")
render(pal1_game, "bg_full_game.png")

# report which rows have non-blank cells, per column band
print("non-blank cells per row (row: count):")
for row in range(64):
    c = sum(1 for col in range(32) if bgv[col*64+row] or bgc[col*64+row])
    if c: print(f"  row {row}: {c}")
