"""Build the Sega 32X port of Xevious (dual-CPU ROM, via marsdev in WSL).

One .32x ROM holds two programs:

* 68000 (Genesis side): the real platform-agnostic Xevious core + the Mega
  Drive OSD layer (megadrive.68k) running on the Genesis VDP. It boots through
  the 32X security blob in src/sega32x/m68k_crt1.s, whose shim hands off to the
  MD init (startup.68k) -> md_main -> the game. Sound is stubbed (Phase 1);
  sprites still use the MD VDP (moved to the 32X framebuffer in Phase 2).
  Linked low (ROM 0x3F0) and run from the 0x000000 window, exactly like the MD.

* SH-2 (32X side): boot.s (which incbins the two 68000 binaries) + the master
  m_main / slave. Phase 1 keeps the framebuffer OFF so the MD video shows.

The toolchain (m68k-elf + sh-elf, gcc 15.2.0) lives in WSL Arch under ~/mars
(see the sega-32x-toolchain memory). Output: bin/xevious_32x.32x

Usage: py build_32x.py [debug]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEBUG = "debug" in sys.argv[1:]


def wsl(cmd, capture=False):
    return subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd],
                          capture_output=capture, text=True)


# project root as a WSL /mnt path
PROJ = wsl('wslpath -a "%s"' % HERE, capture=True).stdout.strip()
OBJ = PROJ + "/obj/32x"
SEGA = PROJ + "/src/sega32x"

# --- toolchain (sourced from ~/mars/mars.sh) ---
ENV = "source ~/mars/mars.sh && "
MDAS = "m68k-elf-as"
MDLD = "m68k-elf-ld"
SHAS = "sh-elf-as"
SHCC = "sh-elf-gcc"
SHOBJC = "sh-elf-objcopy"

MDFLAGS = ("-m68000 --register-prefix-optional "
           "-I src -I src/megadrive "
           "--defsym __megadrive__=1 --defsym __sega32x__=1 --defsym RELEASE=1")
if DEBUG:
    MDFLAGS += " --defsym DEBUG=1"

# 68000 program: m68k_crt1 (blob+shim) MUST be first so the blob lands at 0x3F0
M68K_SOURCES = [
    ("src/sega32x/m68k_crt1.s", ""),
    ("src/megadrive/startup.68k", ""),
    ("src/megadrive/megadrive.68k", ""),
    ("src/sega32x/sega32x_sound.68k", ""),   # osd_sound_* -> slave IPC (near megadrive: bsr PC16)
    ("src/sega32x/sega32x_video.68k", ""),   # md_flush_32x + the display-list buffer
    ("src/xevious_main.68k", ""),
    ("src/xevious_sub.68k", "--defsym NO68020=1"),
    ("src/xevious_ram.68k", ""),
    ("src/map_rom.68k", ""),
]

# SH-2 program: master renderer + slave + the framebuffer driver and sprite gfx
SH_CFILES = ["src/main.c", "src/hw_32x.c", "src/string.c", "src/font.c",
             "src/shared_objects.c", "src/slave.c"]
SH_SFILES = ["src/gfx_32x_data.s",    # incbins gfx_32x_palette/sprites
             "src/gfx_egg_32x.s",     # incbins the 255-colour "cheteiro" egg image
             "src/snd_32x.s"]         # incbins the PCM sample blob + table
SHCC_FLAGS = ("-m2 -mb -std=c99 -ffreestanding -Wall -O2 -fomit-frame-pointer "
              "-I src/sega32x/src -I src/sega32x/inc")
if DEBUG:
    SHCC_FLAGS = SHCC_FLAGS.replace("-O2", "-Og -g -DDEBUG")


def run(label, cmd):
    r = wsl(ENV + "cd '%s' && " % PROJ + cmd)
    if r.returncode != 0:
        sys.exit("[32x] FAILED: %s" % label)


def main():
    wsl("mkdir -p '%s'" % OBJ)
    print("[32x] building Xevious 32X (%s)" % ("debug" if DEBUG else "release"))

    # ---- 68000: crt0 (vectors + MD header) ----
    run("crt0 as", "%s %s '%s/m68k_crt0.s' -o '%s/m68k_crt0.o'" % (MDAS, MDFLAGS, SEGA, OBJ))
    run("crt0 ld", "%s -T '%s/m68k_crt0.ld' -nostdlib --oformat=binary "
        "'%s/m68k_crt0.o' -o '%s/m68k_crt0.bin'" % (MDLD, SEGA, OBJ, SEGA))

    # ---- 68000: crt1 (security blob + shim + startup + OSD + core + stubs) ----
    objs = []
    for src, extra in M68K_SOURCES:
        name = os.path.splitext(os.path.basename(src))[0]
        o = "%s/%s.o" % (OBJ, name)
        run("as " + src, "%s %s %s '%s/%s' -o '%s'" % (MDAS, MDFLAGS, extra, PROJ, src, o))
        objs.append(o)
        print("  m68k  " + src)
    run("crt1 ld", "%s -T '%s/m68k_crt1.ld' -nostdlib --oformat=binary %s "
        "-o '%s/m68k_crt1.bin'" % (MDLD, SEGA, " ".join("'%s'" % o for o in objs), SEGA))
    print("  m68k  -> m68k_crt1.bin")

    # ---- SH-2: boot.s (incbins the 68000 binaries) + C ----
    run("boot as", "%s --small -I '%s' '%s/boot.s' -o '%s/boot.o'" % (SHAS, SEGA, SEGA, OBJ))
    sh_objs = ["%s/boot.o" % OBJ]
    for s in SH_SFILES:
        name = os.path.splitext(os.path.basename(s))[0]
        o = "%s/%s.o" % (OBJ, name)
        run("shas " + s, "%s --small -I '%s' '%s/%s' -o '%s'" % (SHAS, SEGA, SEGA, s, o))
        sh_objs.append(o)
        print("  sh-2  " + s)
    for c in SH_CFILES:
        name = os.path.splitext(os.path.basename(c))[0]
        o = "%s/%s.o" % (OBJ, name)
        run("shcc " + c, "%s %s -c '%s/%s' -o '%s'" % (SHCC, SHCC_FLAGS, SEGA, c, o))
        sh_objs.append(o)
        print("  sh-2  " + c)
    run("sh ld", "%s -T '%s/mars.ld' -nostdlib %s -lgcc -o '%s/xevious_32x.elf'"
        % (SHCC, SEGA, " ".join("'%s'" % o for o in sh_objs), OBJ))
    print("  sh-2  -> xevious_32x.elf")

    # ---- pack the ROM ----
    run("objcopy", "%s -O binary '%s/xevious_32x.elf' '%s/temp.bin'" % (SHOBJC, OBJ, OBJ))
    run("pad", "dd if='%s/temp.bin' of='%s/bin/xevious_32x-alpha-0.01.32x' bs=8192 conv=sync 2>/dev/null"
        % (OBJ, PROJ))
    sz = wsl("stat -c%%s '%s/bin/xevious_32x-alpha-0.01.32x'" % PROJ, capture=True).stdout.strip()
    print("[32x] -> bin/xevious_32x-alpha-0.01.32x  (%s bytes)" % sz)


if __name__ == "__main__":
    main()
