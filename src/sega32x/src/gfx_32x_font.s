! HUD font for the 32X: the MD 1bpp fg character set (256 chars x 8 bytes,
! MSB = leftmost pixel). The SH-2 renders HUD glyphs by arcade char code
! (digits 0x00-0x09, letters A=0x0A.., CH_SHIP=0x25). The 68000 builds the
! HUD display list at arcade positions (md_build_hud); the SH-2 blits it on
! top of the sprites, because the 32X layer covers even high-priority MD.

    .global _gfx_32x_font

    .section .rodata

    .align 2
_gfx_32x_font:
    .incbin "src/megadrive/gfx_fg_chars.bin"
