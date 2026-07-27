/*
 * riscv_harvard.ld
 *
 * WHY THIS EXISTS: this project's RTL models a Harvard architecture --
 * instruction_memory.v and data_memory.v are physically separate
 * memories, each addressed independently starting at 0. Without a
 * linker script, the default RISC-V toolchain link places .text at
 * some nonzero default address and .data/.bss right after it in ONE
 * shared address space -- correct for a real, unified-memory machine,
 * but wrong for this design. Any global/static variable then gets an
 * absolute or gp-relative address computed against that real linked
 * address, not against data_memory.v's actual address-0-based
 * addressing -- silently reading/writing the wrong offset into
 * data.mem. Purely local (stack-relative) variables were never
 * affected by this, which is why every program tested so far (none of
 * which used a global) never hit it.
 *
 * This script defines two SEPARATE memory regions, both nominally
 * starting at address 0 -- IMEM for code (matching
 * instructions.mem's addressing) and DMEM for data (matching
 * data.mem's addressing) -- so the compiler emits addresses that are
 * already correct for how this hardware actually works, with no
 * post-hoc address translation needed.
 *
 * UNTESTED: I don't have the real riscv32-unknown-elf toolchain in my
 * own environment to verify this compiles/links cleanly end-to-end.
 * Verify with a real program that declares a global variable, checking
 * both that the link succeeds and that the disassembly shows small,
 * near-zero addresses for .data/.bss accesses (auipc/lui sequences
 * targeting something like 0x0-0x100, not a large absolute address).
 */

MEMORY
{
    IMEM (rx)  : ORIGIN = 0x00000000, LENGTH = 0x00100000  /* 1MB, generous upper bound for instructions.mem */
    DMEM (rwx) : ORIGIN = 0x00000000, LENGTH = 0x00100000  /* 1MB, generous upper bound for data.mem */
}

SECTIONS
{
    .text : {
        *(.text.init)
        *(.text .text.*)
    } > IMEM

    /* Explicitly reset the location counter for the data region --
       without this, output section placement would continue from
       wherever .text left off (in IMEM's address range), not restart
       at DMEM's own base. */
    . = ORIGIN(DMEM);

    .rodata : {
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
    } > DMEM

    .data : {
        *(.data .data.*)
        *(.sdata .sdata.*)
    } > DMEM

    .bss (NOLOAD) : {
        *(.bss .bss.*)
        *(.sbss .sbss.*)
        *(COMMON)
    } > DMEM

    _end = .;

    /DISCARD/ : {
        *(.comment)
        *(.riscv.attributes)
    }
}
