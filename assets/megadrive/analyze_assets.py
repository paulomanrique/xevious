"""M0 audit: count used (tile,clut) combos and unique MD patterns/colors.

Reads assets/amiga/xevious_gfx.c + the in-game CLUT usage JSONs and reports:
- bg: used combos, unique color-baked 4bpp patterns (with H/V flip dedup),
  distinct RGB colors (game vs title tiles)
- sprites: used combos, unique 16x16 frames, distinct RGB colors,
  greedy 2-palette split feasibility
This decides static vs streaming tile budgets for the Mega Drive port.
"""
import ast, json, os, re, collections

this_dir = os.path.dirname(os.path.abspath(__file__))
amiga_dir = os.path.join(this_dir, "..", "amiga")

def parse_gfx_c(path):
    block_dict = {}
    with open(path) as f:
        block, block_name, start_block, size = [], "", False, 0
        for line in f:
            if "uint8" in line:
                if block:
                    txt = "".join(block).strip().strip(";")
                    block_dict[block_name] = ast.literal_eval(txt)
                    block = []
                start_block = True
                block_name = line.split()[1].split("[")[0]
            elif start_block:
                line = re.sub("//.*", "", line)
                block.append(line.replace("{", "[").replace("}", "]"))
        if block:
            txt = "".join(block).strip().strip(";")
            block_dict[block_name] = ast.literal_eval(txt)
    return block_dict

def load_usage(path):
    with open(path) as f:
        return {int(k): sorted(v) for k, v in json.load(f).items()}

gfx = parse_gfx_c(os.path.join(amiga_dir, "xevious_gfx.c"))
for name, data in gfx.items():
    print(f"{name}: {len(data)} entries x {len(data[0])} bytes")

palette = [tuple(c) for c in gfx["palette"]]
bg_cluts = gfx["bg_tile_clut"]          # [n][4] palette indices
sprite_cluts = gfx["sprite_clut"]       # [n][8] palette indices
bg_tiles = gfx["bg_tile"]               # [512][64] pixel values 0-3
sprites = gfx["sprite"]                 # [320][256] pixel values 0-7
fg_tiles = gfx["fg_tile"]               # [512][64] pixel values 0-1

bg_usage = load_usage(os.path.join(amiga_dir, "bg_tile_clut.json"))
sprite_usage = load_usage(os.path.join(amiga_dir, "sprite_tile_clut.json"))

TITLE_TILES = set(range(416, 512)) | {240,241,242,243,244,245,246,247,248,249}

# ---------------- BG analysis ----------------
def flip_h(px, w, h):
    return tuple(px[r*w + (w-1-c)] for r in range(h) for c in range(w))
def flip_v(px, w, h):
    return tuple(px[(h-1-r)*w + c] for r in range(h) for c in range(w))

def canon(px, w, h):
    """canonical form under H/V flips -> (key, hflip, vflip) of chosen rep"""
    cands = [(tuple(px), 0, 0)]
    fh = flip_h(px, w, h); cands.append((fh, 1, 0))
    fv = flip_v(px, w, h); cands.append((fv, 0, 1))
    cands.append((flip_v(fh, w, h), 1, 1))
    best = min(cands, key=lambda t: t[0])
    return best[0]

bg_combos = 0
bg_pat_exact = set()
bg_pat_flip = set()
bg_colors_game = set()
bg_colors_title = set()
transparent = (255, 0, 255)

for tile, cluts in bg_usage.items():
    px = bg_tiles[tile]
    for clut in cluts:
        bg_combos += 1
        cl = bg_cluts[clut]
        baked = tuple(palette[cl[p]] for p in px)   # 64 RGB values
        bg_pat_exact.add(baked)
        bg_pat_flip.add(canon(baked, 8, 8))
        tgt = bg_colors_title if tile in TITLE_TILES else bg_colors_game
        for p in px:
            tgt.add(palette[cl[p]])

print("\n=== BG ===")
print(f"used (tile,clut) combos: {bg_combos}")
print(f"unique patterns exact: {len(bg_pat_exact)}; after flip dedup: {len(bg_pat_flip)}")
print(f"distinct colors in game tiles: {len(bg_colors_game)}; title tiles: {len(bg_colors_title)}")
print(f"VRAM if all resident: {len(bg_pat_flip)*32} bytes")

# ---------------- Sprite analysis ----------------
sp_combos = 0
sp_pat_flip = set()
sp_colors = set()
clut_colors = {}   # used sprite clut -> frozenset of opaque RGB
sp_clut_used = set()

for tile, cluts in sprite_usage.items():
    if tile >= len(sprites):
        continue
    px = sprites[tile]
    for clut in cluts:
        sp_combos += 1
        sp_clut_used.add(clut)
        cl = sprite_cluts[clut]
        # pixel 0 = transparent on sprites? Amiga used palette_trans idx -> magenta
        baked = tuple(transparent if cl[p] == 0x80 or p == 0 else palette[cl[p] & 0x7f]
                      for p in px)
        sp_pat_flip.add(canon(baked, 16, 16))
        for v in baked:
            if v != transparent:
                sp_colors.add(v)
        clut_colors[clut] = frozenset(v for v in baked if v != transparent) | clut_colors.get(clut, frozenset())

print("\n=== SPRITES ===")
print(f"used (frame,clut) combos: {sp_combos}; used cluts: {len(sp_clut_used)}")
print(f"unique 16x16 frames after flip dedup: {len(sp_pat_flip)}")
print(f"distinct opaque colors: {len(sp_colors)}")
print(f"VRAM if all resident: {len(sp_pat_flip)*128} bytes")

# greedy 2-palette split: can sprite cluts be partitioned into 2 sets of <=15 colors?
def greedy_split(cluts_cols, nbins, cap):
    bins = [set() for _ in range(nbins)]
    members = [[] for _ in range(nbins)]
    for clut, cols in sorted(cluts_cols.items(), key=lambda kv: -len(kv[1])):
        placed = False
        for i in range(nbins):
            if len(bins[i] | cols) <= cap:
                bins[i] |= cols; members[i].append(clut); placed = True
                break
        if not placed:
            return None, None
    return bins, members

bins, members = greedy_split(clut_colors, 2, 15)
if bins:
    print(f"2-palette split OK: pal sizes {[len(b) for b in bins]}, cluts {[len(m) for m in members]}")
else:
    print("2-palette split FAILED with exact colors (quantization needed)")

# ---------------- FG analysis ----------------
used_fg = sum(1 for t in fg_tiles[:256] if any(t))
print(f"\n=== FG ===\nnon-blank fg chars (bank 0): {used_fg}")
