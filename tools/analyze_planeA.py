"""Analyze the plane A nametable dump vs the fg shadows.

Reconstructs which NT word SHOULD be at each plane A cell given the fg shadows
and the OSD mapping rules, and diffs against the real dump (obj/md/dump_planeA.bin).
"""
import os, sys, collections

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md_dir = os.path.join(root, "obj", "md")
sys.path.insert(0, os.path.join(root, "assets", "megadrive"))

def load(name):
    with open(os.path.join(md_dir, name), "rb") as f:
        return f.read()

planeA = load("dump_planeA.bin")          # 64x64 words
fgv = load("dump_fgv.bin")
fgc = load("dump_fgc.bin")

def nt(row, col):
    off = (row * 64 + col) * 2
    return (planeA[off] << 8) | planeA[off + 1]

# survey: which tiles appear in the visible window (rows 0..35, cols 6..33)
tiles = collections.Counter()
for r in range(36):
    for c in range(6, 34):
        w = nt(r, c)
        tiles[w] += 1
print("top NT words in visible area:")
for w, n in tiles.most_common(12):
    print(f"  {w:04X} x{n}  (tile {w & 0x7FF}, pal {(w>>13)&3}, pri {w>>15}, "
          f"hf {(w>>11)&1}, vf {(w>>12)&1}")

# check a few rows fully
print("\nrow 20 cols 6..33:", " ".join(f"{nt(20,c):04X}" for c in range(6, 34)))
print("row 34 cols 6..33:", " ".join(f"{nt(34,c):04X}" for c in range(6, 34)))
print("row 44 cols 6..33:", " ".join(f"{nt(44,c):04X}" for c in range(6, 34)))

# columns outside playfield
print("\nrow 10 cols 0..5: ", " ".join(f"{nt(10,c):04X}" for c in range(0, 6)))
print("row 10 cols 34..39:", " ".join(f"{nt(10,c):04X}" for c in range(34, 40)))

# what the shadows say should be on screen rows (fg rows 4..39)
print("\nfg shadow row 24 (screen row 20), cols arcade 0..31 (char,attr):")
f = 24
row_data = []
for col in range(32):
    off = col * 64 + f
    row_data.append(f"{fgv[off]:02X}/{fgc[off]:02X}")
print(" ".join(row_data))

shadow_chars = collections.Counter(fgv)
print("\nfgv byte histogram (top 8):", shadow_chars.most_common(8))
