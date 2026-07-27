// ============================================================
// Module      : Program Counter (PC)
// File        : pc.v
// Description : 7-bit program counter register, sized exactly
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
    input      [6:0] pc_next,
    output reg [6:0] pc_out
);

    always @(posedge clk or posedge reset) begin
        if (reset)
            pc_out <= 7'h0;
        else if (pc_write)
            pc_out <= pc_next;
        // else: pc_write=0 -> stall, hold current value
    end

endmodule
