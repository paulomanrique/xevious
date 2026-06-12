"""Pad a Mega Drive ROM to a power-of-two size and fix the header.

Usage: py tools/fix_header.py <rom.bin>
- pads with 0xFF to the next power of two (min 128KB)
- writes ROM end address at 0x1A4
- computes the standard checksum (word sum from 0x200) at 0x18E
"""
import sys, struct

def main(path):
    with open(path, "rb") as f:
        data = bytearray(f.read())

    size = 1 << 17
    while size < len(data):
        size <<= 1
    data += b"\xFF" * (size - len(data))

    struct.pack_into(">I", data, 0x1A4, size - 1)

    csum = 0
    for off in range(0x200, size, 2):
        csum = (csum + struct.unpack_from(">H", data, off)[0]) & 0xFFFF
    struct.pack_into(">H", data, 0x18E, csum)

    with open(path, "wb") as f:
        f.write(data)
    print(f"{path}: {size//1024}KB, checksum 0x{csum:04X}")

if __name__ == "__main__":
    main(sys.argv[1])
