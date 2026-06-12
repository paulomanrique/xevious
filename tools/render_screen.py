"""Composite the MD screen (plane B under plane A) from the dumped shadows,
for a range of plane-B vscroll values, to find the fg/bg alignment that
overlaps the title fg logo onto the bg logo. Usage: py render_screen.py [BGV...]
"""
import os, re, sys
from PIL import Image

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md = os.path.join(root, "obj", "md")
mddir = os.path.join(root, "src", "megadrive")
def load(n): return open(os.path.join(md, n), "rb").read()
def loadmd(n): return open(os.path.join(mddir, n), "rb").read()

bgv, bgc = load("dump_bgv.bin"), load("dump_bgc.bin")
fgv, fgc = load("dump_fgv.bin"), load("dump_fgc.bin")
combo = loadmd("gfx_bg_combo.bin")
game_pat, title_pat = loadmd("gfx_bg_patterns.bin"), loadmd("gfx_title_patterns.bin")
fg_chars = loadmd("gfx_fg_chars.bin")
fg_cmap = loadmd("gfx_fg_color_map.bin")

g = open(os.path.join(mddir, "graphics_md.68k")).read()
def eq(n): return int(re.search(rf"\.equ {n}, (\d+)", g).group(1))
BG_BASE, POOL_BASE = eq("GFX_BG_BASE_TILE"), eq("GFX_POOL_BASE_TILE")
def cram(w): return ((w>>1&7)*255//7, (w>>5&7)*255//7, (w>>9&7)*255//7)
def parse_pal(label):
    m = re.search(rf"{label}:\s*\n((?:\s*\.word [^\n]+\n)+)", g)
    return [cram(int(w,16)) for w in re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))]
title_pal = parse_pal("gfx_palette_title")[:16]
gp = re.search(r"gfx_palettes_game:\s*\n((?:\s*\.word[^\n]+\n)+)", g).group(1)
pal0 = [cram(int(x,16)) for x in re.findall(r"0x([0-9A-Fa-f]{4})", re.findall(r"\.word ([^\|\n]+)", gp)[0])]

MD_LEFT_COL = 6
def bg_tile_pixels(t):
    if t >= POOL_BASE: d, o = title_pat, (t-POOL_BASE)*32
    else: d, o = game_pat, (t-BG_BASE)*32
    if o < 0 or o+32 > len(d): return [0]*64
    px=[]
    for b in d[o:o+32]: px += [b>>4, b&0xF]
    return px

def render(BGV, FGV=56, fname="screen.png"):
    img = Image.new("RGB",(320,224),(0,0,0))
    # plane B (bg): md cell (mc, mr) ; arcade col such that 6+((29-col)&31)=mc
    # invert: (29-col)&31 = mc-6 -> col = (29-(mc-6))&31
    for sy in range(224):
        brow = ((sy + BGV)//8) & 63
        for sx in range(320):
            mc = sx//8
            if mc < MD_LEFT_COL or mc > 33: continue
            col = (29-(mc-MD_LEFT_COL)) & 31
            off = col*64 + brow
            code, attr = bgv[off], bgc[off]
            code9 = code | ((attr&1)<<8)
            clut = ((attr>>2)&0xF)|((code&0x80)>>3)|((attr&3)<<5)
            idx=(clut<<9)|code9
            word=(combo[idx*2]<<8)|combo[idx*2+1]
            if word==0: continue
            t=word&0x7FF; hf=(word>>11)&1; vf=(word>>12)&1
            px=bg_tile_pixels(t)
            x=7-(sx&7) if hf else sx&7
            y=7-((sy+BGV)&7) if vf else (sy+BGV)&7
            img.putpixel((sx,sy), title_pal[px[y*8+x]])
    # plane A (fg) overlay: plane A row = fg arcade row - 4 ; screen y = parow*8 - FGV
    for sy in range(224):
        parow = (sy + FGV)//8
        fgrow = parow + 4
        if fgrow < 0 or fgrow >= 64: continue
        for sx in range(320):
            mc = sx//8
            if mc < MD_LEFT_COL or mc > 33: continue
            col = (29-(mc-MD_LEFT_COL)) & 31
            off = col*64 + fgrow
            ch = fgv[off]
            if ch==0 or ch==0x24: continue
            attr = fgc[off]; colr = attr & 0x3F
            slot = fg_cmap[colr] if colr < len(fg_cmap) else 1
            rgb = pal0[slot] if slot < len(pal0) else (255,255,255)
            bmp = fg_chars[ch*8:(ch+1)*8]
            yy = (sy+FGV)&7
            rowbits = bmp[yy] if yy < len(bmp) else 0
            xx = sx&7
            if rowbits & (0x80>>xx):
                img.putpixel((sx,sy), rgb)
    img.save(os.path.join(md, fname))
    print("wrote", fname, "BGV", BGV)

vals = [int(a) for a in sys.argv[1:]] or [0, 48, 88]
for v in vals:
    render(v, fname=f"screen_bgv{v}.png")
