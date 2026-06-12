/* Mega Drive linker script: ROM at 0, work RAM at 0xFF0000 */

OUTPUT_FORMAT("elf32-m68k", "elf32-m68k", "elf32-m68k")
OUTPUT_ARCH(m68k)
ENTRY(_start)

MEMORY
{
  rom (rx)  : ORIGIN = 0x00000000, LENGTH = 0x400000
  ram (rwx) : ORIGIN = 0x00FF0000, LENGTH = 0x10000
}

SECTIONS
{
  . = 0x00000000;
  .text :
  {
    *(.vectors)
    *(.text)
    *(.text.*)
    *(.rodata)
    *(.rodata.*)
  } >rom =0x4e75
  /* no initialised-data-in-RAM support: .data must stay read-only (core has none) */
  .data :
  {
    *(.data)
    *(.data.*)
  } >rom
  _end_of_rom = .;

  . = 0x00FF0000;
  .bss :
  {
    *(.bss)
    *(.bss.*)
    *(COMMON)
    . = ALIGN(4);
  } >ram
  _end = .;
  PROVIDE (end = .);

  .comment 0 : { *(.comment) }
}
