# M0 Audit — Xevious Mega Drive port

## Toolchain (validated)
- All 4 core files assemble with SGDK `as.exe` (m68k-elf):
  `-m68000 --register-prefix-optional -I src --defsym __megadrive__=1 --defsym RELEASE=1`
- `xevious_sub.68k` additionally needs `--defsym NO68020=1` (NO68020 is only defined
  inside xevious_main.68k; sub has two 68020-addressing-mode fallbacks behind .ifdef).
- `.align 0x1000` = BYTE semantics on m68k-elf gas (obj_tbl lands at 0x1000). OK.
- Core sizes: main text 19.5KB, sub 10.3KB, map_rom 16KB, RAM bss **16512 bytes** (+130 sub).
- PCM4 Z80 driver (SGDK src/snd/pcm/drv_pcm4.s80) assembles with sjasm → 2669 bytes.
  Includes z80_def/z80_mac/z80_fct.i80 copied from SGDK/inc/snd (committed in src/megadrive).

## OSD contracts (from xevious_osd_interface_spec.pdf + neogeo.68k + amiga.68k)
- videoram/colorram offset (d0.w): **byte offset = col*64 + row** (column-major),
  col 0-31, row 0-63. Screen col = (29 - col) & 31, 28 visible. FG visible rows 4..39
  (core "screen row" = videoram row - 4, rows 0..35 of 288px).
- osd_w_fg_colorram: d1 = FlipY<<7|FlipX<<6|color[3:0]<<2|color[5:4]. Preserve d0-d3/a0/a1.
- osd_w_bg_colorram: d1 = FlipY|FlipX|color[3:0]<<2|color[6:5]; attr bit0 = tile code bit8;
  color bit4 = videoram bit7. Must write BOTH tile+attr (read companion shadow). Preserve d0-d4/a0/a1.
- Core keeps its own shadows in RAM: fg/bg_colorram/videoram (0x800 each) — osd writes them first.
- osd_update_scroll_hw: d6.w = 0..0x1FF (bg wraps at 512px along long axis).
- osd_update_sprite_shadow: a5=obj_tbl, 64 entries. _STATE 1=skip, 0=deactivate (zero _X/_Y,
  set STATE=1, hide hw sprite), else active. _X 9 bits in word[13:5] (long axis, down=+),
  _Y 8 bits in word[12:5]. _ATTR: b7=bank, b3=yflip, b2=xflip, b1=dbl height, b0=dbl width.
  Double-size tile codes: dw: code&~1 -> {c,c+1}; dh: code&~2 -> {c+2,c}; dwh: code&~3.
  MUST fill sprite_shadow_msb (core RAM, 64×2): [2n]=0xEF-Y[7:0], [2n+1]=(X[8:0]+8)>>1.
- osd_update_32_sprite_hw: d0 = 0 (MAIN ISR, ground objs+bacura sprites 0-31) or
  32 (SUB loop: solvalou/bombs/bullets/flying 32-63).
- osd_read_dipswitches: returns d0=DSWA, d1=DSWB. Amiga model: d0 = 0x1F|lives<<5,
  d1 = 0x1F-ish|difficulty<<5, bit1=flags-award (set=yes), bit0 = P1 bomb ACTIVE LOW
  merged per-frame from live input. NeoGeo also merges P2 bomb into bit4.
- osd_read_p1_inputs: d0 = direction ordinal 0xF0..0xF8 (table from UDLR nibble),
  bit5 = fire level (active low), bit4 = fire edge one-shot (active low).
- osd_read_coin: d0 nonzero + Z flag = new coin (edge). osd_read_start: bit0=1P, bit1=2P.
- osd_read_high_scores: a0 = dest table (0x50: 5 × [3 BCD + 10 name + 3 pad]),
  a1 = dest current high score (3 BCD, copy of entry 1). Caller: lea high_score_1st_msb,a0 /
  lea RAM_high_score,a1. osd_write_high_scores: a0 = source table (skip save if cheats).
- Sound: NeoGeo priority logic to replicate: snd_playing[32] flags;
  MAIN_THEME starts cnt=380, while playing only SOLVALOU_SND calls tick it down (no other
  sound starts); at 0 -> engine sound starts. ANDOR_GENESIS cnt=4 reset on every call, ticked
  by SOLVALOU_SND. HIGH(EST)_SCORE play until stop. osd_sound_stop ignores BOMB_SND.
  Amiga channels: ch1 shot/bomb/bacura_hit/coin; ch2 flying_enemy_hit/teleport;
  ch3 the rest; music+solvalou engine = mutually exclusive -> PCM4 ch0.

## Display design (settled)
- H40 320×224 NTSC. Plane A=fg, Plane B=bg, both 64×64. Window plane = right side panel
  (x>=272, 6 cells) for relocated HUD. Left 48px = black (plane A border).
- Playfield 224px wide at columns 6..33 (hscroll -48 equivalent).
- bg: arcade row r -> plane B row r, vscroll = (bg_scroll + WINDOW_BIAS[mode]) & 511.
- fg: arcade (col,row) -> plane A fixed cells; window shift per mode via plane A vscroll.
- Mode detection (palette + window): core sentinel `bg_videoram+0x60E == 0xCD` -> title mode
  (Amiga amiga.68k:1277 trick). Title window shows screen rows ~6..33 (title credits rows
  33-34, hiscore table rows 21..32); game window rows ~4..31.
- HUD relocation (fg lookup table entries redirect): top rows 0-1 (1UP col27->2, HIGH SCORE
  center, 2UP col8->21, score digits), bottom row 35 (lives col27, flags col9->20).
- Solvalou clamp patch (only core patch): update_solvalou_sprite_XY xevious_main.68k:2119
  clamps _X to [144*32, 304*32] -> MD reduces max to ~272*32 under .ifdef __megadrive__
  (combined span crosshair+ship = 256px > 224 window). Tune in M4.
- Sprites: y = X/32 - window_base, x = (29*8+7 - Y/32)?? (mirror: verify in M5) + 48 panel offset.

## Asset analysis (analyze_assets.py)
- bg: 1394 used (tile,clut) combos -> 1075 unique color-baked patterns (flip dedup) = 34.4KB.
  Game tiles use 27 distinct colors; title tiles 12. Plan: quantize game bg -> 15 (PAL1),
  title palette swapped into PAL1 during title mode. Title patterns live in sprite-pool
  VRAM region during title (game/title bg never coexist).
- sprites: 1030 combos, 50 cluts -> 833 unique frames = 106KB -> streaming mandatory.
  50 distinct colors -> quantize to 30 across PAL2+PAL3 (greedy split with quantization in M2).
- fg: 239 non-blank chars; monochrome 1bpp × 6-bit color -> DYNAMIC 1bpp->4bpp expansion
  cache in VRAM (128-256 slots), pixel value = color slot in PAL0. No logs needed.
- VRAM map v2: 0x0000 bg game patterns (~25KB) | sprite pool + title bg (~18KB) |
  fg cache 4-8KB | 0xB000 Window NT 4KB | 0xBC00 SAT | 0xBF00 hscroll | 0xC000 A NT | 0xE000 B NT.

## Misc
- xevious.inc OPT_*: identical dev/release; OPT_SUB_HAS_IRQ=1 (sub irq calls
  osd_update_32_sprite_hw(32) + osd_update_scroll_hw from MAIN ISR).
- Super Xevious: maps+logic present (is_super_xevious, set via Amiga WHDLoad tooltype).
  MD: defer (default off); possible button-held-at-boot toggle later.
- Easter egg credit string: core uses __neogeo__/__amiga__ ifdefs, generic fallback OK.
- Sounds: all WAVs exist incl. music (main_theme/high_score/highest_score/solvalou).
  Total raw 2.7MB -> 8-bit mono 16kHz fits ROM. sox NOT needed (pure Python wave+resample;
  Python 3.13 has no audioop).
- Coordinates: arcade X axis = LONG axis (vertical on screen, rotated monitor). dir_delta_tbl
  U = dX=-16 (x scale <<5). Solvalou spawn X=0x2500 (296). Solvalou range X 144..304+16,
  crosshair ~64..80 ahead (above).
