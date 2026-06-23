# Mega Drive / Genesis build for Xevious.
# Orchestrates asset conversion + assembly/link via the Python helpers.
# (The heavy lifting lives in build_md.py so the same logic is usable directly.)

PY = py

.PHONY: all assets clean run

all: bin/xevious_md.bin

assets: src/megadrive/graphics_md.68k src/megadrive/sounds_md.68k src/megadrive/tab_vol.bin src/megadrive/gfx_namco_md.68k

src/megadrive/graphics_md.68k: assets/amiga/xevious_gfx.c assets/megadrive/convert_graphics_md.py
	$(PY) assets/megadrive/convert_graphics_md.py

src/megadrive/gfx_namco_md.68k: src/sega32x/src/gfx_namco_32x.bin assets/megadrive/make_namco_logo_md.py
	$(PY) assets/megadrive/make_namco_logo_md.py

src/megadrive/sounds_md.68k: assets/megadrive/convert_sounds_md.py
	$(PY) assets/megadrive/convert_sounds_md.py

src/megadrive/tab_vol.bin: tools/extract_tabvol.py
	$(PY) tools/extract_tabvol.py

bin/xevious_md.bin: assets src/megadrive/megadrive.68k src/megadrive/pcm4.68k \
                    src/megadrive/startup.68k src/megadrive/header.68k \
                    src/xevious_main.68k src/xevious_sub.68k src/xevious_ram.68k src/map_rom.68k
	$(PY) build_md.py
	$(PY) tools/fix_header.py bin/xevious_md.bin

clean:
	$(PY) -c "import shutil,os; shutil.rmtree('obj/md',ignore_errors=True)"

run: all
	"C:/Games/Sega - Mega Drive/Blastem/blastem.exe" bin/xevious_md.bin
