# Xevious — Sega Mega Drive / Genesis target

A third target for the [jotd666/xevious](https://github.com/jotd666/xevious)
68000 transcode of arcade Xevious, alongside the existing NeoGeo and Amiga
ports. The platform-agnostic game core is reused unmodified (one small
`__megadrive__`-guarded clamp aside); everything Mega Drive-specific lives in
`src/megadrive/` and `assets/megadrive/`.

## What works

- Full attract mode, title, hi-score table, 1P/2P play, death/respawn, game over.
- Background map, foreground text, hardware sprites, scrolling.
- Score/lives/area/credits HUD on a right-side panel (the arcade screen is
  taller than the MD display, so the HUD is relocated off the playfield).
- 4-channel PCM sound (music + SFX) via the SGDK PCM4 Z80 driver.
- High scores saved to battery SRAM.
- Runs on Blastem, Genesis Plus GX, Kega Fusion and PicoDrive (NTSC, 60 Hz).

## Display

Arcade Xevious is a 224×288 vertical screen; the MD shows 320×224. The port
runs in H40 (320×224): the 224-px-wide playfield is centred and the game is
viewed through a fixed 224-line window onto the 288-line logical field. The
HUD that the arcade draws top/bottom is redirected to a 48-px panel on the
right (Window plane). Background scroll maps to the VDP's vertical scroll.

## Controls (3-button pad)

| Input | Action |
|-------|--------|
| D-pad | move |
| B | zapper (air) |
| A | blaster (bomb) |
| C | insert coin |
| Start | start game (also coins up when there are no credits) |

## Building

Requires the SGDK m68k-elf toolchain (assumed at
`C:\Games\Sega - Mega Drive\SGDK`) and Python 3 with Pillow.

```
py assets/megadrive/convert_graphics_md.py   # arcade gfx -> MD tiles/palettes
py assets/megadrive/convert_sounds_md.py     # WAVs -> 16 kHz PCM samples
py tools/extract_tabvol.py                   # PCM4 volume table (once)
py build_md.py                               # assemble + link + checksum
```

`make -f makefile.md` runs all of the above. Output: `bin/xevious_md.bin`
(1 MB, region JUE / region-free). `py build_md.py debug` builds a faster-to-
inspect variant; `--defsym MD_AUTOPLAY=1` auto-starts a real game for testing.

## How it is put together

- `src/megadrive/startup.68k` — reset, TMSS, VDP/Z80/PSG init, RAM clear.
- `src/megadrive/header.68k` — 68000 vectors + Sega header (SRAM declared).
- `src/megadrive/megadrive.68k` — the OSD layer: the 23 `osd_*` functions the
  core calls. Tilemap writes go through per-cell VDP-command lookup (fg) or an
  inline address computation (bg); the foreground is a dynamic 1bpp→4bpp tile
  cache; sprites build a full SAT shadow each frame with an LRU streaming
  allocator for the 695 sprite frames over a resident VRAM pool.
- `src/megadrive/pcm4.68k` — uploads the PCM4 Z80 driver and implements the
  sound dispatch (the NeoGeo priority/timer logic driving 4 PCM channels).
- `assets/megadrive/convert_graphics_md.py` — parses `xevious_gfx.c` + the
  CLUT-usage JSON logs, quantises the arcade palette into 4 MD palettes, and
  emits deduplicated 4bpp tiles + combo→nametable lookup tables.
- `assets/megadrive/convert_sounds_md.py` — pure-Python WAV → 8-bit/16 kHz PCM.

## Notes / limitations

- PCM is 16 kHz mono (vs the Amiga's 24 kHz) — a deliberate trade for the
  simple, robust PCM4 protocol.
- On a PAL console the game runs at 50 Hz (slower), as is normal for a
  region-free NTSC-timed build.
- Super Xevious is present in the core but not exposed by this target.
