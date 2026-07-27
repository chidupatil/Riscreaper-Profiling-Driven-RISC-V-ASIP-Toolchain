// ============================================================
// Module      : Instruction Memory
// File        : instruction_memory.v
// Description : 15-word ROM, sized exactly to this program
//               (auto-generated -- was a fixed 128-word allocation
//               regardless of actual program size). Combinational read.
//               Loaded from instructions.mem via $readmemh.
//
// pc input is 7 bits, matching gen_pc.py's computed PC_WIDTH
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
    input  [6:0] pc,
    output [31:0] instruction,
    output        program_end
);

    parameter PROGRAM_SIZE = 15; // Number of instructions in .mem file

    reg [31:0] mem [0:14];
    integer i;

    initial begin
        for (i = 0; i < 15; i = i + 1)
            mem[i] = 32'h00000013; // NOP
        $readmemh("instructions.mem", mem);
    end

    assign instruction = (pc[6:2] < PROGRAM_SIZE) ?
                          mem[pc[6:2]] :
                          32'h00000013; // NOP - safe program end

    assign program_end = (pc[6:2] >= PROGRAM_SIZE);

endmodule
