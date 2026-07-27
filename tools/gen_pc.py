#!/usr/bin/env python3
"""
gen_pc.py -- generates pc.v and pc_adder.v with a width computed exactly
for the program being built, instead of a fixed 32 bits.

WHY THE EARLIER ATTEMPT AT THIS BROKE, AND WHY THIS ONE DOESN'T:
-------------------------------------------------------------------
An earlier version of this project's pipeline_top.v generator narrowed
pc_out/pc_plus4_if to a narrow *wire*, while pc.v and pc_adder.v stayed
unmodified, always-32-bit modules. That meant pc_adder.v computed
pc_in + 4 at full 32-bit precision internally, and the correct 32-bit
result got silently truncated the moment it was captured into the
narrow wire -- proven with a real simulation: a backward-branch loop
wrapped PC around at the narrow boundary and re-executed the entire
program forever instead of halting.

The fix here is not "never narrow PC" -- it's "narrow the modules that
compute it, not just the wires connecting to them". pc.v and pc_adder.v
below both operate AT the computed width directly: the addition itself
happens at PC_WIDTH bits, with well-defined wraparound semantics at
exactly the boundary the width was sized for -- not an accidental
truncation of a wider computation.

WIDTH SIZING:
-------------
PC_WIDTH must cover: every real instruction address (0 to
(program_size-1)*4), PLUS enough headroom for pipeline_top.v's halt
detection to work -- once IF starts fetching past the end of the
program, PC keeps naturally incrementing by 4 each cycle (nothing
causes a stall once only NOPs are being fetched) for DRAIN_CYCLES
cycles before `halted` asserts. If PC_WIDTH is too tight to represent
that drain region, the same wraparound failure mode reappears. This
computes: (program_size_words + DRAIN_CYCLES + safety_margin), rounded
up to the next word-count power of two, plus 2 bits for the byte
address. DRAIN_CYCLES here MUST match pipeline_top.v's own
DRAIN_CYCLES constant (gen_pipeline_and_tb.py) -- if that ever changes,
this needs to change with it.

Legitimate branch/jump targets never need extra margin beyond this:
they always fall within the program's own address range by
construction (a well-formed compiled program never jumps outside
itself), which is already covered by the "every real instruction
address" part above.
"""
from __future__ import annotations

import argparse
from pathlib import Path

# Must match pipeline_top.v's own DRAIN_CYCLES (gen_pipeline_and_tb.py).
DRAIN_CYCLES = 6
SAFETY_MARGIN_WORDS = 4


def compute_pc_width(program_size_words: int, drain_cycles: int = DRAIN_CYCLES, margin: int = SAFETY_MARGIN_WORDS) -> int:
    required_words = max(1, program_size_words) + drain_cycles + margin
    word_bits = max(1, (required_words - 1).bit_length())
    return word_bits + 2  # word count -> byte address


def gen_pc(pc_width: int) -> str:
    return f'''// ============================================================
// Module      : Program Counter (PC)
// File        : pc.v
// Description : {pc_width}-bit program counter register, sized exactly
//               to this program (real instructions + halt-detection
//               drain margin), not a fixed 32 bits. Supports stall
//               (pc_write=0 freezes PC) and flush (branch taken
//               redirects PC). Resets to 0 on reset.
//
// IMPORTANT: this module's width must match pc_adder.v and
// instruction_memory.v's `pc` input EXACTLY, and pipeline_top.v's
// pc_out/pc_plus4_if/pc_next wires must be generated at this SAME
// width -- narrowing only some of these and not others is exactly what
// caused a proven PC wraparound bug earlier in this project. All of
// these are generated together from the same computed pc_width for
// that reason.
// ============================================================

`timescale 1ns / 1ps

module pc (
    input                    clk,
    input                    reset,
    input                    pc_write,
    input      [{pc_width - 1}:0] pc_next,
    output reg [{pc_width - 1}:0] pc_out
);

    always @(posedge clk or posedge reset) begin
        if (reset)
            pc_out <= {pc_width}'h0;
        else if (pc_write)
            pc_out <= pc_next;
        // else: pc_write=0 -> stall, hold current value
    end

endmodule
'''


def gen_pc_adder(pc_width: int) -> str:
    return f'''// ============================================================
// Module      : PC Adder
// File        : pc_adder.v
// Description : Combinational adder, computes PC+4 AT {pc_width} bits
//               directly -- not computed wide and truncated afterward.
//               See pc.v's header comment / this file's module
//               docstring in gen_pc.py for why that distinction matters.
// ============================================================

`timescale 1ns / 1ps

module pc_adder (
    input  [{pc_width - 1}:0] pc_in,
    output [{pc_width - 1}:0] pc_plus4
);
    assign pc_plus4 = pc_in + {pc_width}'d4;
endmodule
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instructions_mem", type=Path, help="instructions.mem (already includes the startup stub) to size PC width from")
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args(argv)

    program_size = sum(
        1 for line in args.instructions_mem.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("//", "#"))
    )
    pc_width = compute_pc_width(program_size)

    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "pc.v").write_text(gen_pc(pc_width), encoding="utf-8")
    (args.outdir / "pc_adder.v").write_text(gen_pc_adder(pc_width), encoding="utf-8")
    (args.outdir / "pc_width.txt").write_text(str(pc_width), encoding="utf-8")

    print(f"Generated pc.v / pc_adder.v with pc_width={pc_width} bits "
          f"(program_size={program_size} words + {DRAIN_CYCLES} drain + {SAFETY_MARGIN_WORDS} margin)")
    print(f"Wrote {args.outdir / 'pc_width.txt'} for gen_pipeline_and_tb.py / gen_instruction_memory_v2 to read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())