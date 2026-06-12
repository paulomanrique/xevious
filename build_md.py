"""Build the Mega Drive port of Xevious.

Usage: py build_md.py [debug]
- assembles core + megadrive OSD layer with the SGDK m68k-elf toolchain
- links with src/megadrive/megadrive.x, extracts binary, pads + checksums
Output: bin/xevious_md.bin (+ xevious_md.map, listing files in obj/md)

The game core is linked in once src/megadrive/graphics_md.68k has been
generated (M2+); before that the skeleton platform layer builds alone.
debug: defines DEBUG=1 (skip splash etc. via OPT_* overrides in megadrive.68k)
"""
import os, subprocess, sys

SGDK_BIN = r"C:\Games\Sega - Mega Drive\SGDK\bin"
AS = os.path.join(SGDK_BIN, "as.exe")
LD = os.path.join(SGDK_BIN, "ld.exe")
OBJCOPY = os.path.join(SGDK_BIN, "objcopy.exe")

ROOT = os.path.dirname(os.path.abspath(__file__))
OBJ = os.path.join(ROOT, "obj", "md")
BIN = os.path.join(ROOT, "bin")
ROM = os.path.join(BIN, "xevious_md.bin")

DEBUG = "debug" in sys.argv[1:]

COMMON_FLAGS = [
    "-m68000", "--register-prefix-optional",
    "-I", "src", "-I", "src/megadrive",
    "--defsym", "__megadrive__=1",
    "--defsym", "RELEASE=1",
]
if DEBUG:
    COMMON_FLAGS += ["--defsym", "DEBUG=1"]

PLATFORM_SOURCES = [
    ("src/megadrive/header.68k", []),
    ("src/megadrive/startup.68k", []),
    ("src/megadrive/megadrive.68k", []),
    ("src/megadrive/pcm4.68k", []),
]
CORE_SOURCES = [
    ("src/xevious_main.68k", []),
    ("src/xevious_sub.68k", ["--defsym", "NO68020=1"]),
    ("src/xevious_ram.68k", []),
    ("src/map_rom.68k", []),
]
# graphics_md.68k is .include'd by megadrive.68k; sounds_md.68k links separately
GENERATED_SOURCES = [
    ("src/megadrive/sounds_md.68k", []),
]
# pcm4.68k references md_sound_table from sounds_md.68k, so the sound data
# must be present for a full link (it always is after convert_sounds_md.py)

def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(cmd))
        print(r.stdout)
        print(r.stderr)
        sys.exit(1)
    return r

def main():
    os.makedirs(OBJ, exist_ok=True)
    os.makedirs(BIN, exist_ok=True)

    sources = list(PLATFORM_SOURCES)
    if os.path.exists(os.path.join(ROOT, "src/megadrive/graphics_md.68k")):
        sources += CORE_SOURCES
        sources += [s for s in GENERATED_SOURCES
                    if os.path.exists(os.path.join(ROOT, s[0]))]

    objs = []
    for src, extra in sources:
        name = os.path.splitext(os.path.basename(src))[0]
        obj = os.path.join(OBJ, name + ".o")
        lst = os.path.join(OBJ, name + ".lst")
        run([AS, f"-a={lst}"] + COMMON_FLAGS + extra + [src, "-o", obj])
        objs.append(obj)
        print(f"as  {src}")

    elf = os.path.join(OBJ, "xevious_md.elf")
    run([LD, "-T", "src/megadrive/megadrive.x", "-N",
         "-Map=" + os.path.join(OBJ, "xevious_md.map"), "-o", elf] + objs)
    print("ld  -> xevious_md.elf")

    run([OBJCOPY, "-O", "binary", elf, ROM])
    run([sys.executable, "tools/fix_header.py", ROM])

if __name__ == "__main__":
    main()
