"""Extract SGDK tab_vol.c into a 4096-byte binary for the PCM4 driver."""
import re, os
src = r"C:\Games\Sega - Mega Drive\SGDK\src\snd\pcm\tab_vol.c"
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "src", "megadrive", "tab_vol.bin")
text = open(src).read()
body = text[text.index("{") + 1: text.rindex("}")]
vals = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+", body)]
assert len(vals) == 0x1000, len(vals)
open(out, "wb").write(bytes(vals))
print(f"{out}: {len(vals)} bytes")
