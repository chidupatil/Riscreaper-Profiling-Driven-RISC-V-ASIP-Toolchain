// ============================================================
// Module      : PC Adder
// File        : pc_adder.v
// Description : Combinational adder, computes PC+4 AT 7 bits
//               directly -- not computed wide and truncated afterward.
//               See pc.v's header comment / this file's module
//               docstring in gen_pc.py for why that distinction matters.
// ============================================================

`timescale 1ns / 1ps

module pc_adder (
    input  [6:0] pc_in,
    output [6:0] pc_plus4
);
    assign pc_plus4 = pc_in + 7'd4;
endmodule
