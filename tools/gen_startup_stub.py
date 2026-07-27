#!/usr/bin/env python3
"""
gen_startup_stub.py -- prepends stack-pointer AND return-address
initialization instructions to instructions.mem.

WHY sp NEEDS INIT: c_to_mem.sh compiles with -nostartfiles, so GCC never
emits any crt0/startup code -- there is nothing anywhere in this toolchain
that sets sp before main() runs. Since every register (including sp/x2)
resets to 0 in both the emulator and the real register file, the first
`addi sp, sp, -N` prologue in any compiled program computes sp as a huge
negative/wrapped address (e.g. sp=-32 => 0xFFFFFFE0), wildly out of range
for a small data_memory.v. This silently corrupts every stack-relative
load/store in every program that has local variables -- i.e. nearly all
of them.

WHY ra ALSO NEEDS INIT: -O0 compiles a standard prologue/epilogue for
main() even though nothing ever calls it, so main() ends with a real
`jalr x0, ra, 0` ("ret"). With ra left at its reset value of 0, that jump
lands back at address 0 -- exactly where this startup stub lives -- and
silently restarts the entire program forever. Since PC then only ever
revisits addresses already below PROGRAM_SIZE, `instruction_memory.v`'s
program_end never asserts, so pipeline_top.v's `halted` output never
fires either -- a perfectly correct program would still time out in
simulation. Fix: initialize ra to point exactly one word past the last
instruction (the same address PROGRAM_SIZE represents), so returning
from main() lands precisely in "past the program" territory and halt
detection fires immediately and correctly.

Nothing else downstream needs to change: the emulator, the control/RTL
generators, and the real hardware all just see a couple of extra
instructions at address 0 and everything shifts down accordingly -- your
program's own control flow (branches/jumps) is all PC-relative or
computed from actual register values, so this doesn't break anything
that was already correct.

STACK_TOP must match the actual size of data_memory.v (currently 64
words = 256 bytes, hence the default of 256). If data_memory.v's size
ever changes, this needs to be regenerated with a matching --stack-top.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def encode_addi(rd: int, rs1: int, imm: int) -> int:
    return ((imm & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0 << 12) | ((rd & 0x1F) << 7) | 0x13


def encode_lui(rd: int, imm20: int) -> int:
    return ((imm20 & 0xFFFFF) << 12) | ((rd & 0x1F) << 7) | 0x37


def gen_const_load_words(rd: int, value: int) -> list[int]:
    """addi if it fits in a 12-bit signed immediate, else a lui+addi pair."""
    if -2048 <= value <= 2047:
        return [encode_addi(rd, 0, value)]
    upper = (value + 0x800) >> 12
    lower = value - (upper << 12)
    return [encode_lui(rd, upper), encode_addi(rd, rd, lower)]


def encode_jal(rd: int, imm: int) -> int:
    b20 = (imm >> 20) & 1
    b19_12 = (imm >> 12) & 0xFF
    b11 = (imm >> 11) & 1
    b10_1 = (imm >> 1) & 0x3FF
    return (b20 << 31) | (b10_1 << 21) | (b11 << 20) | (b19_12 << 12) | ((rd & 0x1F) << 7) | 0x6F


def gen_startup_words(stack_top: int, real_instruction_count: int, main_offset: int) -> list[int]:
    SP, RA = 2, 1
    sp_words = gen_const_load_words(SP, stack_top)

    # ra must point exactly one word past the LAST instruction of the
    # FINAL program (startup + real code combined) -- but that depends on
    # how many startup instructions there are in total, which depends on
    # how many bits ra's own target needs. The stub now ALWAYS has
    # exactly sp_words + ra_words + 1 instructions (the trailing
    # jal-to-main -- see below). Try the common case (sp+ra fit in one
    # instruction each, total=3) first; retry assuming ra needs a
    # lui+addi pair (total=4) if that doesn't converge.
    for n_startup_guess in (len(sp_words) + 1 + 1, len(sp_words) + 2 + 1):
        target_byte = (real_instruction_count + n_startup_guess) * 4
        ra_words = gen_const_load_words(RA, target_byte)
        if len(sp_words) + len(ra_words) + 1 == n_startup_guess:
            # The jal's own immediate is always main_offset + 4,
            # regardless of the rest of the stub's length: it's always
            # the LAST stub instruction, immediately before the
            # original extracted code begins, so the distance from the
            # jal itself to main()'s shifted position is constant.
            # Proven: jal_addr = (n-1)*4, main_final_addr = n*4 +
            # main_offset, so main_final_addr - jal_addr = main_offset + 4
            # for any n.
            jal_word = encode_jal(0, main_offset + 4)
            return sp_words + ra_words + [jal_word]

    # Should be unreachable for any realistic program size, but fail
    # loudly rather than silently emitting a wrong ra target.
    raise RuntimeError(
        f"Could not converge on a startup stub length for "
        f"real_instruction_count={real_instruction_count}; program may be "
        f"unusually large. Please report this."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instructions_mem", type=Path, help="instructions.mem to prepend the startup stub to (modified in place)")
    parser.add_argument("--stack-top", type=int, default=256,
                         help="Initial sp value in bytes; must match data_memory.v's actual size. Default 256 (64 words).")
    parser.add_argument("--main-offset", type=int, default=None,
                         help="Byte offset of main() within the extracted .text, from c_to_mem.sh's nm/objdump "
                              "extraction. If omitted, reads main_offset.txt from the same directory as "
                              "instructions_mem.")
    args = parser.parse_args(argv)

    if args.main_offset is not None:
        main_offset = args.main_offset
    else:
        offset_file = args.instructions_mem.parent / "main_offset.txt"
        if not offset_file.exists():
            print(f"ERROR: no --main-offset given and {offset_file} doesn't exist.")
            print("c_to_mem.sh should have written this -- did you run it before this script?")
            return 1
        main_offset = int(offset_file.read_text(encoding="utf-8").strip())

    # NOTE: this assumes instructions_mem is FRESH (not already stubbed),
    # which is always true in the normal c_to_mem.sh flow (it runs this
    # right after bin_to_mem.py writes a brand-new instructions.mem from
    # the current compile). An earlier version tried to guard against
    # re-running on an already-stubbed file by inserting a `//` comment
    # marker to detect/strip a prior stub -- that was actively dangerous:
    # verified with iverilog that $readmemh does NOT consume an address
    # slot for a comment line, but emulator.py's line-based parser DOES
    # (it enumerates every line including comments), so a comment
    # anywhere in this file would silently misalign every instruction
    # address between the emulator's profiling and real hardware. If you
    # need to re-run this on an already-stubbed file, regenerate
    # instructions.mem from scratch first instead.
    existing_lines = [
        line.strip() for line in args.instructions_mem.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("//", "#"))
    ]

    real_count = len(existing_lines)
    startup_words = gen_startup_words(args.stack_top, real_count, main_offset)
    startup_hex = [f"{w:08x}" for w in startup_words]

    new_lines = startup_hex + existing_lines
    args.instructions_mem.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    total_words = len(startup_words) + real_count
    print(f"Prepended {len(startup_words)}-instruction startup stub "
          f"(sp={args.stack_top}, ra=0x{total_words * 4:x}, jumps to main() at "
          f"offset {main_offset} within the original extracted code) to {args.instructions_mem}")
    print(f"Program now has {total_words} total instructions "
          f"({real_count} real + {len(startup_words)} startup)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())