/*
 * Xevious 32X - master SH-2 sprite renderer (Phase 2: the flicker fix).
 *
 * The 68000 game builds a sprite display list from obj_tbl every frame and
 * hands it over through the back frame-buffer bank (handshake via COMM0). The
 * SH-2 blits every sprite into the framebuffer - no per-scanline limit, so the
 * Andor-Genesis flicker is gone.
 *
 * Compositing (see the sega-32x-compositing notes): PRI = 0 and each sprite
 * colour carries the through-bit (CRAM bit 15), so sprites draw IN FRONT of the
 * Mega Drive terrain/HUD while pixel value 0 stays transparent (MD shows).
 *
 * COMM2 != 0 -> the "modo cheteiro" Konami egg: a full-screen 255-colour image.
 *
 * The marsdev boot fails to release the slave SH-2 (it clears the wrong
 * address), so we clear COMM4 here to let the slave's sound code run.
 */
#include "types.h"
#include "32x.h"
#include "hw_32x.h"

extern const unsigned short gfx_32x_palette[128];
extern const unsigned char  gfx_32x_sprites[];
extern const unsigned char  gfx_32x_font[];         /* 256 chars * 8 bytes, 1bpp */
extern const unsigned int   gfx_egg_32x[];          /* 320*224 bytes (8bpp) */
extern const unsigned short gfx_egg_32x_pal[255];
extern const unsigned int   gfx_namco_32x[];        /* 320*224 bytes: 1=black, 2=red */

#define SPLASH_FRAMES 180                           /* boot logo: ~3s at 60Hz */

#define FB_PIX_BYTE 0x200
#define DL_OFF      0x18000
#define HUD_OFF     0x19000
#define DL  ((volatile unsigned short *)((unsigned char *)&MARS_FRAMEBUFFER + DL_OFF))
#define HUD ((volatile unsigned short *)((unsigned char *)&MARS_FRAMEBUFFER + HUD_OFF))
#define THRU 0x8000
#define HUD_WHITE 200                               /* CRAM slot: HUD scores */
#define HUD_RED   201                               /* CRAM slot: HUD labels */
#define DISPMODE_32X (MARS_VDP_PRIO_68K | MARS_224_LINES | MARS_VDP_MODE_256)

static volatile unsigned char *fb_pixels(void)
{
    return (volatile unsigned char *)&MARS_FRAMEBUFFER + FB_PIX_BYTE;
}

static void load_sprite_palette(void)
{
    volatile unsigned short *cram = &MARS_CRAM;
    int i;
    cram[0] = COLOR(0, 0, 0);
    for (i = 0; i < 128; i++)
        cram[i + 1] = gfx_32x_palette[i] | THRU;
    cram[HUD_WHITE] = COLOR(31, 31, 31) | THRU;     /* HUD scores/digits */
    cram[HUD_RED]   = COLOR(31,  0,  0) | THRU;     /* HUD arcade labels */
}

static void load_egg_palette(void)
{
    volatile unsigned short *cram = &MARS_CRAM;
    int i;
    cram[0] = COLOR(0, 0, 0);
    for (i = 0; i < 255; i++)
        cram[i + 1] = gfx_egg_32x_pal[i] | THRU;
}

static void clear_transparent(void)
{
    volatile unsigned int *fb32 = (volatile unsigned int *)fb_pixels();
    int i;
    for (i = 0; i < 320 * 224 / 4; i++)
        fb32[i] = 0;
}

static void blit_egg(void)
{
    volatile unsigned int *fb32 = (volatile unsigned int *)fb_pixels();
    int i;
    for (i = 0; i < 320 * 224 / 4; i++)
        fb32[i] = gfx_egg_32x[i];
}

static void load_namco_palette(void)
{
    volatile unsigned short *cram = &MARS_CRAM;
    cram[0] = COLOR(0, 0, 0);
    cram[1] = COLOR(0, 0, 0) | THRU;                /* opaque black background */
    cram[2] = COLOR(11, 0, 2) | THRU;               /* Namco red ramp (AA edges) */
    cram[3] = COLOR(19, 0, 3) | THRU;
    cram[4] = COLOR(28, 0, 4) | THRU;               /* full Namco red (224,0,32) */
}

static void blit_namco(void)
{
    volatile unsigned int *fb32 = (volatile unsigned int *)fb_pixels();
    int i;
    for (i = 0; i < 320 * 224 / 4; i++)
        fb32[i] = gfx_namco_32x[i];
}

static void blit_frame(int fi, int px, int py, int flip)
{
    const unsigned char *src = gfx_32x_sprites + fi * 256;
    volatile unsigned char *fb = fb_pixels();
    int r;

    if (px >= 0 && px <= 304)
    {
        /* fast path: fully on-screen horizontally - no per-pixel x clip, and
         * the H-flip is hoisted out of the inner loop. This is the common case
         * and keeps the busy Andor-Genesis scene inside the 60Hz budget. */
        for (r = 0; r < 16; r++)
        {
            int sy = py + r;
            const unsigned char *srow;
            volatile unsigned char *row;
            int c;
            if (sy < 0 || sy >= 224) continue;
            srow = src + ((flip & 2) ? (15 - r) : r) * 16;
            row = fb + sy * 320 + px;
            if (flip & 1)
                for (c = 0; c < 16; c++) { unsigned char v = srow[15 - c]; if (v) row[c] = v; }
            else
                for (c = 0; c < 16; c++) { unsigned char v = srow[c];      if (v) row[c] = v; }
        }
        return;
    }

    /* slow path: spans a screen edge, clip each pixel */
    for (r = 0; r < 16; r++)
    {
        int sy = py + r;
        const unsigned char *srow;
        volatile unsigned char *row;
        int c;
        if (sy < 0 || sy >= 224) continue;
        srow = src + ((flip & 2) ? (15 - r) : r) * 16;
        row = fb + sy * 320;
        for (c = 0; c < 16; c++)
        {
            int sx = px + c;
            unsigned char v = srow[(flip & 1) ? (15 - c) : c];
            if (v && sx >= 0 && sx < 320)
                row[sx] = v;
        }
    }
}

/* render an 8x8 1bpp glyph (arcade char code) in a solid colour; clear pixels
 * stay transparent so the playfield shows through the text gaps */
static void blit_char(int ch, int px, int py, unsigned char color)
{
    const unsigned char *src = gfx_32x_font + ch * 8;
    volatile unsigned char *fb = fb_pixels();
    int r;
    for (r = 0; r < 8; r++)
    {
        int sy = py + r;
        unsigned char bits = src[r];
        volatile unsigned char *row;
        int c;
        if (sy < 0 || sy >= 224) continue;
        row = fb + sy * 320 + px;
        for (c = 0; c < 8; c++)
            if (bits & (0x80 >> c))
                row[c] = color;
    }
}

int main(void)
{
    int egg = 0;
    int s;

    MARS_SYS_COMM4 = 0;                     /* release the slave SH-2 (sound) */

    Hw32xInit(MARS_VDP_MODE_256, 0);
    MARS_VDP_DISPMODE = DISPMODE_32X;

    /* Boot splash: cover the load/init screens with the Namco logo while the
     * 68000 boots the game in parallel. The logo is opaque (through-bit on a
     * full-screen image), so it hides whatever the MD shows underneath. */
    load_namco_palette();
    for (s = 0; s < SPLASH_FRAMES; s++)
    {
        blit_namco();
        Hw32xScreenFlip(1);
    }

    load_sprite_palette();
    MARS_SYS_COMM0 = 0;

    while (1)
    {
        if (MARS_SYS_COMM2 != 0)                /* modo cheteiro egg */
        {
            if (!egg) { load_egg_palette(); egg = 1; }
            blit_egg();
            Hw32xScreenFlip(1);
            continue;
        }
        if (egg) { load_sprite_palette(); egg = 0; }

        {
            int n, i;
            while (MARS_SYS_COMM0 == 0)
                if (MARS_SYS_COMM2 != 0) break;
            if (MARS_SYS_COMM2 != 0) continue;

            n = DL[0];
            if (n > 256) n = 256;
            clear_transparent();
            for (i = n - 1; i >= 0; i--)
            {
                int x = (short)DL[1 + i * 4 + 0];
                int y = (short)DL[1 + i * 4 + 1];
                int f =         DL[1 + i * 4 + 2];
                int fl =        DL[1 + i * 4 + 3];
                blit_frame(f, x, y, fl);
            }
            /* arcade HUD: text on top of the sprites (the 32X layer covers the
             * MD, so the HUD cannot live on the Mega Drive planes) */
            {
                int hn = HUD[0], j;
                if (hn > 80) hn = 80;
                for (j = 0; j < hn; j++)
                {
                    int hx = (short)HUD[1 + j * 3 + 0];
                    int hy = (short)HUD[1 + j * 3 + 1];
                    int hw =         HUD[1 + j * 3 + 2];  /* high byte = colour */
                    blit_char(hw & 0xFF, hx, hy, hw >> 8);
                }
            }
            Hw32xScreenFlip(1);
            MARS_SYS_COMM0 = 0;
        }
    }
    return 0;
}
