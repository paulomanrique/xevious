*
* Mega Drive hardware definitions for Xevious port
*

* 68K memory map
    .equ    ROM_BASE,       0x000000
    .equ    SRAM_BASE,      0x200001            | odd bytes
    .equ    SRAM_END,       0x2003FF
    .equ    Z80_RAM,        0xA00000
    .equ    Z80_BUSREQ,     0xA11100
    .equ    Z80_RESET,      0xA11200
    .equ    IO_VERSION,     0xA10001
    .equ    IO_DATA1,       0xA10003
    .equ    IO_DATA2,       0xA10005
    .equ    IO_CTRL1,       0xA10009
    .equ    IO_CTRL2,       0xA1000B
    .equ    TMSS_REG,       0xA14000
    .equ    SRAM_CTRL,      0xA130F1
    .equ    RAM_BASE,       0xFF0000

* VDP ports
    .equ    VDP_DATA,       0xC00000
    .equ    VDP_CTRL,       0xC00004
    .equ    VDP_HV,         0xC00008
    .equ    PSG_PORT,       0xC00011

* VRAM layout
* tile patterns: 0x0000-0xAFFF (tile 0 = blank)
*   bg game patterns   from 0x0020 (generated, see graphics_md.68k)
*   sprite pool        after bg    (generated bound)
*   fg dynamic cache   below window NT
    .equ    VRAM_WINDOW_NT, 0xB000              | 64x32 window nametable (4KB)
    .equ    VRAM_SAT,       0xBC00              | sprite attribute table (640B)
    .equ    VRAM_HSCROLL,   0xBF00              | hscroll table
    .equ    VRAM_PLANE_A,   0xC000              | 64x64 nametable (8KB)
    .equ    VRAM_PLANE_B,   0xE000              | 64x64 nametable (8KB)

* VDP register values
* NOTE: '|' is the comment char in MIT syntax: use '+' in expressions!
    .equ    VDPR00, 0x8004                      | mode 1: no hint, normal ops
    .equ    VDPR01_OFF, 0x8134                  | mode 2: display off, vint, dma, V28, mode5
    .equ    VDPR01_ON,  0x8174                  | mode 2: display on
    .equ    VDPR02, 0x8200+(VRAM_PLANE_A>>10)   | plane A nametable
    .equ    VDPR03, 0x8300+(VRAM_WINDOW_NT>>10) | window nametable
    .equ    VDPR04, 0x8400+(VRAM_PLANE_B>>13)   | plane B nametable
    .equ    VDPR05, 0x8500+(VRAM_SAT>>9)        | sprite attribute table
    .equ    VDPR06, 0x8600
    .equ    VDPR07, 0x8700                      | backdrop colour = pal0 idx0
    .equ    VDPR08, 0x8800
    .equ    VDPR09, 0x8900
    .equ    VDPR10, 0x8AFF                      | hint counter
    .equ    VDPR11, 0x8B00                      | full-screen scroll
    .equ    VDPR12, 0x8C81                      | H40, no shadow/hilite, no interlace
    .equ    VDPR13, 0x8D00+(VRAM_HSCROLL>>10)   | hscroll table
    .equ    VDPR14, 0x8E00
    .equ    VDPR15, 0x8F02                      | autoincrement 2
    .equ    VDPR16, 0x9011                      | plane size 64x64
    .equ    VDPR17, 0x9191                      | window: right side, x>=272 (17*16)
    .equ    VDPR18, 0x9200                      | window Y: full height

* VDP command address macros (control port longword formats)
* vram write:  0x40000000 + (a&0x3FFF)<<16 + (a&0xC000)>>14
* cram write:  0xC0000000 + ...
* vsram write: 0x40000010 + ...

    .macro  VDP_W_VRAM   addr
    move.l  #0x40000000+((\addr&0x3FFF)<<16)+((\addr)>>14),(VDP_CTRL)
    .endm

    .macro  VDP_W_CRAM   addr
    move.l  #0xC0000000+((\addr&0x3FFF)<<16)+((\addr)>>14),(VDP_CTRL)
    .endm

    .macro  VDP_W_VSRAM  addr
    move.l  #0x40000010+((\addr&0x3FFF)<<16)+((\addr)>>14),(VDP_CTRL)
    .endm
