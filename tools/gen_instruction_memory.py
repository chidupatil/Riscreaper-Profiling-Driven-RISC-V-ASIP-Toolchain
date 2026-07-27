#!/usr/bin/env python3
"""
gen_instruction_memory.py -- generates instruction_memory.v sized exactly
to the actual program, instead of a fixed 128-word (512-byte) allocation
regardless of program size.

SAFETY: the array can be sized to EXACTLY PROGRAM_SIZE with no margin.
`assign instruction = (pc[31:2] < PROGRAM_SIZE) ? mem[pc[31:2]] : NOP;`
already bounds-checks BEFORE the array read is selected -- the array is
only ever read within [0, PROGRAM_SIZE) on the branch that's actually
chosen. Verilog's ternary technically evaluates both operands for
simulation/synthesis purposes, so an out-of-range mem[] read does happen
as an expression on the NOP branch, but its result is discarded by the
mux regardless -- verified with iverilog to produce no functional
difference and no new warnings beyond the pre-existing "not enough words"
notice you already see whenever PROGRAM_SIZE > the actual line count of
instructions.mem (which does not apply here, since PROGRAM_SIZE now
matches the file exactly).

This replaces update_program_size.sh's sed-based PROGRAM_SIZE patching --
that only patched the parameter, never the `[0:127]` array bound, so the
BRAM/register array was always allocated at full size regardless of the
real program.
"""
from __future__ import annotations

import sys
from pathlib import Path


def count_instructions(mem_path: Path) -> int:
    count = 0
    for line in mem_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        count += 1
    return count


def gen_instruction_memory(program_size: int, pc_width: int = 32) -> str:
    program_size = max(1, program_size)
    last_idx = program_size - 1
    pc_msb = pc_width - 1
    return f'''// ============================================================
// Module      : Instruction Memory
// File        : instruction_memory.v
// Description : {program_size}-word ROM, sized exactly to this program
//               (auto-generated -- was a fixed 128-word allocation
//               regardless of actual program size). Combinational read.
//               Loaded from instructions.mem via $readmemh.
//
// pc input is {pc_width} bits, matching gen_pc.py's computed PC_WIDTH
// EXACTLY -- pc.v, pc_adder.v, and this module's `pc` port must all
// agree on the same width, or the primary addressing path reintroduces
// the port-mismatch wraparound bug this project already proved once.
//
// Program-end handling: when PC goes beyond the last valid instruction,
// the memory returns NOP (0x00000013 = addi x0,x0,0) instead of
// undefined X values, keeping the pipeline in a known safe state.
//
// program_end: high whenever PC is fetching beyond the last valid
// instruction. pipeline_top.v uses this, combined with a drain counter,
// to assert its own `halted` output once the last real instruction has
// fully drained through the pipeline.
//
// NOP = 0x00000013 = addi x0, x0, 0
//       -> writes to x0 (discarded), no memory access, no branch,
//          safe to execute indefinitely.
// ============================================================

`timescale 1ns / 1ps

module instruction_memory (
    input  [{pc_msb}:0] pc,
    output [31:0] instruction,
    output        program_end
);

    parameter PROGRAM_SIZE = {program_size}; // Number of instructions in .mem file

    reg [31:0] mem [0:{last_idx}];
    integer i;

    initial begin
        for (i = 0; i < {program_size}; i = i + 1)
            mem[i] = 32'h00000013; // NOP
        $readmemh("instructions.mem", mem);
    end

    assign instruction = (pc[{pc_msb}:2] < PROGRAM_SIZE) ?
                          mem[pc[{pc_msb}:2]] :
                          32'h00000013; // NOP - safe program end

    assign program_end = (pc[{pc_msb}:2] >= PROGRAM_SIZE);

endmodule
'''


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) not in (3, 4):
        print("Usage: python3 tools/gen_instruction_memory.py <instructions.mem> <outdir> [pc_width]")
        return 1

    mem_path = Path(argv[1])
    outdir = Path(argv[2])
    pc_width = int(argv[3]) if len(argv) == 4 else 32
    program_size = count_instructions(mem_path)

    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "instruction_memory.v"
    out_path.write_text(gen_instruction_memory(program_size, pc_width), encoding="utf-8")

    print(f"Generated {out_path} sized exactly to {program_size} instructions, pc_width={pc_width} "
          f"(was fixed at 128 words / 32-bit pc regardless of program size)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())