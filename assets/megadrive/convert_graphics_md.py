"""Convert arcade Xevious graphics to Mega Drive format.

Inputs (assets/amiga): xevious_gfx.c, bg_tile_clut.json, sprite_tile_clut.json
Outputs (src/megadrive):
  graphics_md.68k        equates, palettes, .incbin hooks
  gfx_bg_patterns.bin    resident game bg patterns (32B 4bpp tiles)
  gfx_title_patterns.bin title-mode bg patterns (loaded into the sprite pool)
  gfx_bg_combo.bin       64K words: (clut7<<9 | code9) -> nametable word (0=unused)
  gfx_sprite_frames.bin  unique 16x16 frames, 128B each (MD sprite tile order)
  gfx_sprite_combo.bin   64K words: (clut7<<9 | sprite9) -> frame descriptor (0xFFFF=unused)
  gfx_fg_chars.bin       256 x 8 bytes, 1bpp char rows
  gfx_fg_color_map.bin   64 bytes: arcade fg colour -> PAL0 slot (1..15)
Also dumps PNG preview sheets in assets/megadrive/dumps for visual checks.

Combo table word formats:
  bg:     0x8000 + (vflip<<12) + (hflip<<11) + tile_index   (tile in VRAM tiles;
          palette bits added at runtime: PAL1 fixed; 0x0000 = unused combo)
          for title combos tile_index is relative to the sprite-pool base.
  sprite: (vflip<<15) + (hflip<<14) + (pal<<13) + frame_id  (0xFFFF = unused;
          pal: 0 -> PAL2, 1 -> PAL3)
"""
import ast, json, os, re, collections
from PIL import Image

this_dir = os.path.dirname(os.path.abspath(__file__))
amiga_dir = os.path.join(this_dir, "..", "amiga")
out_dir = os.path.normpath(os.path.join(this_dir, "..", "..", "src", "megadrive"))
dump_dir = os.path.join(this_dir, "dumps")

TITLE_TILES = set(range(416, 512)) | {240, 241, 242, 243, 244, 245, 246, 247, 248, 249}
TRANSPARENT = (255, 0, 255)

# ---------------- parsing ----------------

def parse_gfx_c(path):
    block_dict = {}
    with open(path) as f:
        block, name, started = [], "", False
        for line in f:
            if "uint8" in line:
                if block:
                    block_dict[name] = ast.literal_eval("".join(block).strip().strip(";"))
                    block = []
                started = True
                name = line.split()[1].split("[")[0]
            elif started:
                line = re.sub("//.*", "", line)
                block.append(line.replace("{", "[").replace("}", "]"))
        if block:
            block_dict[name] = ast.literal_eval("".join(block).strip().strip(";"))
    return block_dict

def load_usage(path):
    with open(path) as f:
        return {int(k): sorted(v) for k, v in json.load(f).items()}

# ---------------- colour helpers ----------------

def md_round(rgb):
    """round an 8-bit RGB tuple to the nearest MD-representable colour"""
    return tuple(round(round(c * 7 / 255) * 255 / 7) for c in rgb)

def md_cram(rgb):
    """MD CRAM word 0000BBB0GGG0RRR0 from an (already rounded) RGB tuple"""
    r, g, b = (round(c * 7 / 255) for c in rgb)
    return (b << 9) | (g << 5) | (r << 1)

def quantize_colors(colors, target):
    """map a set of RGB colours onto <= target colours (PIL median cut).
    returns dict orig -> reduced (all MD-rounded)."""
    colors = sorted(set(colors))
    if len(colors) <= target:
        return {c: c for c in colors}
    strip = Image.new("RGB", (len(colors), 1))
    for i, c in enumerate(colors):
        strip.putpixel((i, 0), c)
    reduced = strip.quantize(colors=target, dither=0).convert("RGB")
    return {c: md_round(reduced.getpixel((i, 0))) for i, c in enumerate(colors)}

# ---------------- pattern helpers ----------------

def flip_h(px, w, h):
    return tuple(px[r * w + (w - 1 - c)] for r in range(h) for c in range(w))

def flip_v(px, w, h):
    return tuple(px[(h - 1 - r) * w + c] for r in range(h) for c in range(w))

def canon(px, w, h):
    """canonical form under flips: returns (canonical, hflip, vflip) where
    px == flip(canonical, hflip, vflip)"""
    fh = flip_h(px, w, h)
    fv = flip_v(px, w, h)
    fhv = flip_v(fh, w, h)
    cands = [(tuple(px), 0, 0), (fh, 1, 0), (fv, 0, 1), (fhv, 1, 1)]
    best = min(cands, key=lambda t: t[0])
    return best

def tile_4bpp(slots8x8):
    """pack 64 pixel slot values (0-15) into 32 bytes of MD 4bpp"""
    out = bytearray()
    for i in range(0, 64, 2):
        out.append((slots8x8[i] << 4) | slots8x8[i + 1])
    return bytes(out)

def frame_to_md_tiles(slots16):
    """16x16 slot values -> 128 bytes: MD sprite tile order
    (top-left, bottom-left, top-right, bottom-right)"""
    tiles = []
    for tx in (0, 1):
        for ty in (0, 1):
            t = []
            for r in range(8):
                for c in range(8):
                    t.append(slots16[(ty * 8 + r) * 16 + tx * 8 + c])
            tiles.append(tile_4bpp(t))
    return b"".join(tiles)

# ---------------- main ----------------

def main():
    os.makedirs(dump_dir, exist_ok=True)
    gfx = parse_gfx_c(os.path.join(amiga_dir, "xevious_gfx.c"))
    palette = [tuple(c) for c in gfx["palette"]]
    bg_cluts = gfx["bg_tile_clut"]
    sprite_cluts = gfx["sprite_clut"]
    bg_tiles = gfx["bg_tile"]
    sprites = gfx["sprite"]
    fg_tiles = gfx["fg_tile"]

    bg_usage = load_usage(os.path.join(amiga_dir, "bg_tile_clut.json"))
    sprite_usage = load_usage(os.path.join(amiga_dir, "sprite_tile_clut.json"))

    report = []

    # ---------- BG (game + title) ----------
    def bake_bg(tile, clut):
        cl = bg_cluts[clut]
        px = bg_tiles[tile]
        return tuple(md_round(palette[cl[p]]) for p in px)

    game_combos, title_combos = [], []
    game_colors, title_colors = set(), set()
    for tile, cluts in bg_usage.items():
        for clut in cluts:
            baked = bake_bg(tile, clut)
            if tile in TITLE_TILES:
                title_combos.append((tile, clut, baked))
                title_colors.update(baked)
            else:
                game_combos.append((tile, clut, baked))
                game_colors.update(baked)

    black = (0, 0, 0)
    gmap = quantize_colors(game_colors - {black}, 15)
    gmap[black] = black
    tmap = quantize_colors(title_colors - {black}, 15)
    tmap[black] = black

    # palette line 1, slot 0 = black (transparent -> backdrop, set black)
    def build_pal(cmap):
        cols = sorted(set(cmap.values()) - {black})
        assert len(cols) <= 15, len(cols)
        slot = {black: 0}
        for i, c in enumerate(cols, start=1):
            slot[c] = i
        return slot, [black] + cols + [black] * (15 - len(cols))

    gslot, gpal = build_pal(gmap)
    tslot, tpal = build_pal(tmap)
    report.append(f"bg game colors {len(gpal)} (quantized from {len(game_colors)})")
    report.append(f"bg title colors (from {len(title_colors)})")

    def dedup_patterns(combos, cmap, slot):
        patterns = []          # list of 32-byte tiles
        pattern_ids = {}
        combo_entries = {}     # (tile,clut) -> (idx, hf, vf)
        for tile, clut, baked in combos:
            slots = tuple(slot[cmap[c]] for c in baked)
            can, hf, vf = canon(slots, 8, 8)
            pid = pattern_ids.get(can)
            if pid is None:
                pid = len(patterns)
                pattern_ids[can] = pid
                patterns.append(tile_4bpp(can))
            combo_entries[(tile, clut)] = (pid, hf, vf)
        return patterns, combo_entries

    g_patterns, g_entries = dedup_patterns(game_combos, gmap, gslot)
    t_patterns, t_entries = dedup_patterns(title_combos, tmap, tslot)
    report.append(f"bg game: {len(game_combos)} combos -> {len(g_patterns)} patterns "
                  f"({len(g_patterns)*32} bytes)")
    report.append(f"bg title: {len(title_combos)} combos -> {len(t_patterns)} patterns "
                  f"({len(t_patterns)*32} bytes)")

    # ---------- sprites ----------
    def bake_sprite(idx, clut):
        cl = sprite_cluts[clut]
        px = sprites[idx]
        return tuple(TRANSPARENT if cl[p] >= 128 else md_round(palette[cl[p]])
                     for p in px)

    sp_combos = []
    clut_cols = collections.defaultdict(set)
    for idx, cluts in sprite_usage.items():
        if idx >= len(sprites):
            continue
        for clut in cluts:
            baked = bake_sprite(idx, clut)
            sp_combos.append((idx, clut, baked))
            clut_cols[clut].update(c for c in baked if c != TRANSPARENT)

    def greedy_split(cmap, cap=15):
        bins = [set(), set()]
        assign = {}
        for clut, cols in sorted(clut_cols.items(), key=lambda kv: -len(kv[1])):
            mapped = {cmap[c] for c in cols}
            for i in (0, 1):
                if len(bins[i] | mapped) <= cap:
                    bins[i] |= mapped
                    assign[clut] = i
                    break
            else:
                return None, None
        return bins, assign

    all_sp_colors = set().union(*clut_cols.values())
    for target in range(30, 19, -1):
        smap = quantize_colors(all_sp_colors, target)
        bins, clut_pal = greedy_split(smap)
        if bins is not None:
            break
    assert bins is not None, "sprite palette split failed at 20 colors"
    report.append(f"sprites: {len(all_sp_colors)} colors -> {target} quantized, "
                  f"split {len(bins[0])}/{len(bins[1])}")

    def build_sp_pal(cols):
        # slot 0 is the hardware-transparent entry, colours start at slot 1, so
        # the emitted palette MUST lead with black -> 16 words total. Without it
        # every slot is off by one (and PAL3 lands a CRAM entry early), which
        # turns e.g. the silver Toroid ring red. (Mirrors build_pal for bg.)
        cols = sorted(cols)
        slot = {}
        for i, c in enumerate(cols, start=1):
            slot[c] = i
        return slot, [black] + cols + [black] * (15 - len(cols))

    sslot = [None, None]
    spal = [None, None]
    sslot[0], spal[0] = build_sp_pal(bins[0])
    sslot[1], spal[1] = build_sp_pal(bins[1])

    frames = []
    frame_ids = {}
    sp_entries = {}
    for idx, clut, baked in sp_combos:
        pal = clut_pal[clut]
        slots = tuple(0 if c == TRANSPARENT else sslot[pal][smap[c]] for c in baked)
        can, hf, vf = canon(slots, 16, 16)
        key = (pal, can)
        fid = frame_ids.get(key)
        if fid is None:
            fid = len(frames)
            frame_ids[key] = fid
            frames.append(frame_to_md_tiles(can))
        sp_entries[(idx, clut)] = (fid, pal, hf, vf)
    report.append(f"sprites: {len(sp_combos)} combos -> {len(frames)} frames "
                  f"({len(frames)*128} bytes)")

    # ---------- fg ----------
    # 6-bit colour indexes the arcade palette directly
    fg_colors = [md_round(palette[c & 0x7F]) if (c & 0x7F) < len(palette) else black
                 for c in range(64)]
    fmap = quantize_colors(set(fg_colors) - {black}, 14)
    fmap[black] = black
    fcols = sorted(set(fmap.values()) - {black})
    fslot = {black: 15}                  # black text gets the last slot
    for i, c in enumerate(fcols, start=1):
        fslot[c] = i
    fg_color_map = bytes(fslot[fmap[c]] for c in fg_colors)
    fg_pal = [black] + fcols + [black] * (14 - len(fcols)) + [black]
    report.append(f"fg: {len(set(fg_colors))} distinct colors -> {len(fcols)} slots")

    fg_bits = bytearray()
    for t in fg_tiles[:256]:
        for r in range(8):
            byte = 0
            for c in range(8):
                byte = (byte << 1) | (t[r * 8 + c] & 1)
            fg_bits.append(byte)

    # ---------- VRAM layout ----------
    N_BLANK = 1
    BG_BASE_TILE = N_BLANK
    n_bg = len(g_patterns)
    POOL_BASE_TILE = BG_BASE_TILE + n_bg
    # patterns area ends at the window NT (0xA000); the fg dynamic cache
    # lives at 0xB000-0xB7FF (64 tiles) - the hscroll table sits at 0xB800
    # and the SAT at 0xBC00, so the cache must not exceed 64 tiles
    FG_CACHE_TILES = 64
    total_tiles = 0xA000 // 32
    pool_tiles = total_tiles - POOL_BASE_TILE
    FG_CACHE_BASE = 0xB000 // 32
    assert pool_tiles >= len(t_patterns), (pool_tiles, len(t_patterns))
    assert pool_tiles >= 4 * 80, f"sprite pool too small: {pool_tiles} tiles"
    report.append(f"VRAM: bg {n_bg} tiles @{BG_BASE_TILE}, pool {pool_tiles} tiles "
                  f"@{POOL_BASE_TILE} ({pool_tiles//4} frames), fg cache @{FG_CACHE_BASE}")

    # ---------- combo tables ----------
    bg_combo = bytearray(2 * 65536)
    for (tile, clut), (pid, hf, vf) in g_entries.items():
        word = 0x8000 | (vf << 12) | (hf << 11) | (BG_BASE_TILE + pid)
        idx = (clut << 9) | tile
        bg_combo[idx * 2] = word >> 8
        bg_combo[idx * 2 + 1] = word & 0xFF
    for (tile, clut), (pid, hf, vf) in t_entries.items():
        word = 0x8000 | (vf << 12) | (hf << 11) | (POOL_BASE_TILE + pid)
        idx = (clut << 9) | tile
        bg_combo[idx * 2] = word >> 8
        bg_combo[idx * 2 + 1] = word & 0xFF

    sp_combo = bytearray(b"\xFF" * (2 * 65536))
    for (idx, clut), (fid, pal, hf, vf) in sp_entries.items():
        word = (vf << 15) | (hf << 14) | (pal << 13) | fid
        i = (clut << 9) | idx
        sp_combo[i * 2] = word >> 8
        sp_combo[i * 2 + 1] = word & 0xFF

    # ---------- write outputs ----------
    def wbin(name, data):
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(bytes(data))

    wbin("gfx_bg_patterns.bin", b"".join(g_patterns))
    wbin("gfx_title_patterns.bin", b"".join(t_patterns))
    wbin("gfx_bg_combo.bin", bg_combo)
    wbin("gfx_sprite_frames.bin", b"".join(frames))
    wbin("gfx_sprite_combo.bin", sp_combo)
    wbin("gfx_fg_chars.bin", fg_bits)
    wbin("gfx_fg_color_map.bin", fg_color_map)

    # ---------- pixelpuro Konami easter-egg screen ----------
    # Compose a 320x224 screen (logo top, avatar centre, catchphrase below),
    # quantise the avatar to PAL1 and the logo/text/backdrop to PAL0, dedup the
    # 8x8 tiles (with H/V flip) and emit a 64x28 nametable. Tile indices are
    # pool-relative; the OSD adds GFX_POOL_BASE_TILE at runtime (the egg reuses
    # the sprite-pool VRAM, restored afterwards). Cols 40-63 are off-screen.
    def build_egg():
        from PIL import ImageDraw, ImageFont, ImageChops
        px_dir = os.path.join(this_dir, "..", "..", "pixelpuro")
        W, H = 320, 224
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        logo = Image.open(os.path.join(px_dir,
            "Gemini_Generated_Image_ny4pigny4pigny4p.png")).convert("RGB")
        lw = 240
        lh = max(1, round(logo.height * lw / logo.width))
        logo = logo.resize((lw, lh), Image.LANCZOS)
        # the PNG has no real alpha: its "transparent" area is a light-grey
        # checker baked into RGB. Chroma-key it out (keep the yellow letters and
        # the dark outline; drop light, low-saturation greys).
        r, gg, bb = logo.split()
        mx = ImageChops.lighter(ImageChops.lighter(r, gg), bb)
        sat = ImageChops.subtract(mx, ImageChops.darker(ImageChops.darker(r, gg), bb))
        is_light = mx.point(lambda v: 255 if v > 110 else 0)
        is_grey = sat.point(lambda v: 255 if v < 40 else 0)
        keep = ImageChops.invert(ImageChops.multiply(is_light, is_grey))
        canvas.paste(logo, ((W - lw) // 2, 16), keep)
        AV, ax, ay = 96, 112, 72                         # tile-aligned: cols 14-25, rows 9-20
        avatar = Image.open(os.path.join(px_dir, "channels4_profile.jpg")
            ).convert("RGB").resize((AV, AV), Image.LANCZOS)
        canvas.paste(avatar, (ax, ay))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
        except Exception:
            font = ImageFont.load_default()
        txt = "Eu sou cheteiro!!!"
        bb = draw.textbbox((0, 0), txt, font=font)
        draw.text(((W - (bb[2] - bb[0])) // 2, 192), txt, fill=(255, 230, 0), font=font)
        px = canvas.load()
        ac0, ac1, ar0, ar1 = ax // 8, (ax + AV) // 8 - 1, ay // 8, (ay + AV) // 8 - 1
        # per-palette colour sets
        av_cols, bg_cols = set(), set()
        for row in range(28):
            for col in range(40):
                dst = av_cols if (ac0 <= col <= ac1 and ar0 <= row <= ar1) else bg_cols
                for py in range(8):
                    for pxx in range(8):
                        dst.add(md_round(px[col * 8 + pxx, row * 8 + py]))
        m1, m0 = quantize_colors(av_cols, 14), quantize_colors(bg_cols, 14)
        s1, p1 = build_pal(m1)
        s0, p0 = build_pal(m0)
        tiles, ids, nt = [], {}, []
        def emit(slots, palbit):
            can, hf, vf = canon(slots, 8, 8)
            k = (palbit, can)
            t = ids.get(k)
            if t is None:
                t = len(tiles); ids[k] = t; tiles.append(tile_4bpp(can))
            return 0x8000 | (palbit << 13) | (vf << 12) | (hf << 11) | t
        for row in range(28):
            for col in range(64):
                if col >= 40:
                    nt.append(0); continue
                avt = ac0 <= col <= ac1 and ar0 <= row <= ar1
                cm, sl, pb = (m1, s1, 1) if avt else (m0, s0, 0)
                slots = tuple(sl[cm[md_round(px[col * 8 + pxx, row * 8 + py])]]
                              for py in range(8) for pxx in range(8))
                nt.append(emit(slots, pb))
        # preview of what the MD will show (visible cols 0-39)
        prev = Image.new("RGB", (W, H), (0, 0, 0))
        for row in range(28):
            for col in range(40):
                w = nt[row * 64 + col]
                pat, pal = tiles[w & 0x7FF], (p1 if (w >> 13) & 1 else p0)
                pix = []
                for b in pat:
                    pix += [b >> 4, b & 0xF]
                for r in range(8):
                    for c in range(8):
                        sx = 7 - c if (w >> 11) & 1 else c
                        sy = 7 - r if (w >> 12) & 1 else r
                        prev.putpixel((col * 8 + c, row * 8 + r), pal[pix[sy * 8 + sx]])
        prev.resize((W * 2, H * 2), Image.NEAREST).save(os.path.join(dump_dir, "egg_preview.png"))
        return p0, p1, tiles, nt

    egg_p0, egg_p1, egg_tiles, egg_nt = build_egg()
    assert len(egg_tiles) <= pool_tiles, f"egg tiles {len(egg_tiles)} > pool {pool_tiles}"
    report.append(f"egg: {len(egg_tiles)} tiles (pool {pool_tiles})")
    wbin("gfx_egg_tiles.bin", b"".join(egg_tiles))
    egg_nt_bytes = bytearray()
    for w in egg_nt:
        egg_nt_bytes += bytes((w >> 8, w & 0xFF))
    wbin("gfx_egg_nt.bin", egg_nt_bytes)

    def pal_words(cols):
        return [md_cram(c) for c in cols]

    with open(os.path.join(out_dir, "graphics_md.68k"), "w") as f:
        f.write("* generated by assets/megadrive/convert_graphics_md.py - DO NOT EDIT\n\n")
        for line in report:
            f.write(f"* {line}\n")
        f.write("\n")
        f.write(f"    .equ GFX_BG_BASE_TILE, {BG_BASE_TILE}\n")
        f.write(f"    .equ GFX_N_BG, {n_bg}\n")
        f.write(f"    .equ GFX_POOL_BASE_TILE, {POOL_BASE_TILE}\n")
        f.write(f"    .equ GFX_POOL_TILES, {pool_tiles}\n")
        f.write(f"    .equ GFX_POOL_FRAMES, {pool_tiles // 4}\n")
        f.write(f"    .equ GFX_N_TITLE, {len(t_patterns)}\n")
        f.write(f"    .equ GFX_N_FRAMES, {len(frames)}\n")
        f.write(f"    .equ GFX_FG_CACHE_BASE, {FG_CACHE_BASE}\n")
        f.write(f"    .equ GFX_FG_CACHE_TILES, {FG_CACHE_TILES}\n")
        f.write(f"    .equ GFX_EGG_NTILES, {len(egg_tiles)}\n\n")
        for sym in ("gfx_palettes_game", "gfx_palette_title", "gfx_bg_combo_tbl",
                    "gfx_bg_patterns", "gfx_title_patterns", "gfx_sprite_combo_tbl",
                    "gfx_sprite_frames", "gfx_fg_chars", "gfx_fg_color_map",
                    "gfx_egg_palette0", "gfx_egg_palette1", "gfx_egg_tiles", "gfx_egg_nt"):
            f.write(f"    .global {sym}\n")
        f.write("\n    .section .rodata\n\n    .align 2\n")
        f.write("gfx_palettes_game:\n")
        for name, cols in (("PAL0 fg/hud", fg_pal), ("PAL1 bg game", gpal),
                           ("PAL2 sprites", spal[0]), ("PAL3 sprites", spal[1])):
            words = ",".join(f"0x{w:04X}" for w in pal_words(cols))
            f.write(f"    .word {words}   | {name}\n")
        f.write("gfx_palette_title:\n")
        f.write("    .word " + ",".join(f"0x{w:04X}" for w in pal_words(tpal)) + "\n\n")
        f.write("    .align 2\ngfx_bg_combo_tbl:\n    .incbin \"gfx_bg_combo.bin\"\n")
        f.write("    .align 2\ngfx_bg_patterns:\n    .incbin \"gfx_bg_patterns.bin\"\n")
        f.write("    .align 2\ngfx_title_patterns:\n    .incbin \"gfx_title_patterns.bin\"\n")
        f.write("    .align 2\ngfx_sprite_combo_tbl:\n    .incbin \"gfx_sprite_combo.bin\"\n")
        # 128-byte alignment: frame DMA must not cross a 128KB source boundary
        f.write("    .balign 128\ngfx_sprite_frames:\n    .incbin \"gfx_sprite_frames.bin\"\n")
        f.write("    .align 2\ngfx_fg_chars:\n    .incbin \"gfx_fg_chars.bin\"\n")
        f.write("    .align 2\ngfx_fg_color_map:\n    .incbin \"gfx_fg_color_map.bin\"\n")
        # pixelpuro easter-egg screen
        f.write("    .align 2\ngfx_egg_palette0:\n    .word "
                + ",".join(f"0x{w:04X}" for w in pal_words(egg_p0)) + "\n")
        f.write("gfx_egg_palette1:\n    .word "
                + ",".join(f"0x{w:04X}" for w in pal_words(egg_p1)) + "\n")
        f.write("    .balign 128\ngfx_egg_tiles:\n    .incbin \"gfx_egg_tiles.bin\"\n")
        f.write("    .align 2\ngfx_egg_nt:\n    .incbin \"gfx_egg_nt.bin\"\n")

    # ---------- preview sheets ----------
    def sheet(patterns, pal_cols, w_tiles, tile_px, name, is_frame=False):
        n = len(patterns)
        rows = (n + w_tiles - 1) // w_tiles
        img = Image.new("RGB", (w_tiles * tile_px, rows * tile_px), (32, 32, 32))
        full = [black] + pal_cols if len(pal_cols) == 15 else pal_cols
        for i, pat in enumerate(patterns):
            ox, oy = (i % w_tiles) * tile_px, (i // w_tiles) * tile_px
            pix = []
            for b in pat:
                pix += [b >> 4, b & 0x0F]
            if is_frame:
                # frames stored as 4 tiles column-major
                for t in range(4):
                    tx, ty = (t // 2) * 8, (t % 2) * 8
                    for r in range(8):
                        for c in range(8):
                            v = pix[t * 64 + r * 8 + c]
                            img.putpixel((ox + tx + c, oy + ty + r), full[v])
            else:
                for r in range(8):
                    for c in range(8):
                        img.putpixel((ox + c, oy + r), full[pix[r * 8 + c]])
        img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
        img.save(os.path.join(dump_dir, name))

    sheet([bytearray(p) for p in g_patterns], gpal[1:] , 32, 8, "bg_game.png")
    sheet([bytearray(p) for p in t_patterns], tpal[1:], 32, 8, "bg_title.png")
    sheet([bytearray(p) for p in frames], spal[0], 16, 16, "sprites_pal2.png", is_frame=True)

    for line in report:
        print(line)

if __name__ == "__main__":
    main()
