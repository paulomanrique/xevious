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
extern const unsigned int   gfx_egg_32x[];          /* 320*224 bytes (8bpp) */
extern const unsigned short gfx_egg_32x_pal[255];

#define FB_PIX_BYTE 0x200
#define DL_OFF      0x18000
#define DL ((volatile unsigned short *)((unsigned char *)&MARS_FRAMEBUFFER + DL_OFF))
#define THRU 0x8000
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

static void blit_frame(int fi, int px, int py, int flip)
{
    const unsigned char *src = gfx_32x_sprites + fi * 256;
    volatile unsigned char *fb = fb_pixels();
    int r;
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

int main(void)
{
    int egg = 0;

    MARS_SYS_COMM4 = 0;                     /* release the slave SH-2 (sound) */

    Hw32xInit(MARS_VDP_MODE_256, 0);
    MARS_VDP_DISPMODE = DISPMODE_32X;
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
            if (n > 80) n = 80;
            clear_transparent();
            for (i = n - 1; i >= 0; i--)
            {
                int x = (short)DL[1 + i * 4 + 0];
                int y = (short)DL[1 + i * 4 + 1];
                int f =         DL[1 + i * 4 + 2];
                int fl =        DL[1 + i * 4 + 3];
                blit_frame(f, x, y, fl);
            }
            Hw32xScreenFlip(1);
            MARS_SYS_COMM0 = 0;
        }
    }
    return 0;
}
