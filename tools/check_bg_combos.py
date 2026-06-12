"""Count bg cells (in dumped shadows) that reference combos missing from the JSON log."""
import os, sys, json
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md = os.path.join(root, "obj", "md")
amiga = os.path.join(root, "assets", "amiga")

bgv = open(os.path.join(md, "dump_bgv.bin"), "rb").read()
bgc = open(os.path.join(md, "dump_bgc.bin"), "rb").read()
with open(os.path.join(amiga, "bg_tile_clut.json")) as f:
    usage = {int(k): set(v) for k, v in json.load(f).items()}

missing = {}
present = 0
blank = 0
for off in range(0x800):
    code = bgv[off]
    attr = bgc[off]
    code9 = code | ((attr & 1) << 8)
    clut = ((attr >> 2) & 0x0F) | ((code & 0x80) >> 3) | ((attr & 3) << 5)
    if code9 == 0 and clut == 0:
        blank += 1
        continue
    if clut in usage.get(code9, set()):
        present += 1
    else:
        missing[(code9, clut)] = missing.get((code9, clut), 0) + 1

print(f"present(logged) cells: {present}")
print(f"blank cells: {blank}")
print(f"missing-combo cells: {sum(missing.values())} ({len(missing)} distinct)")
for k, n in sorted(missing.items(), key=lambda x: -x[1])[:15]:
    print(f"  tile {k[0]} clut {k[1]}: x{n}")
