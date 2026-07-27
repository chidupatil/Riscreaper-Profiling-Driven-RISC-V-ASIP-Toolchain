// Trim applied: ALU result carries only 7 significant bits (sign-extended internally; a/b/result ports stay 32-bit; a/b themselves are never narrowed, so overflow's a[31]/b[31] stay valid)
// ============================================================
// Module      : ALU
// File        : alu.v
// Description : Auto-generated, DENSE encoding mode. alu_control is
//               1 bits, using codes computed by encoding_plan.py for
//               exactly the operations this program's instructions
//               require -- see control_unit.v's header for why these
//               must stay in sync with alu_control.v.
//
// Included operations: ADD
// ============================================================
`timescale 1ns / 1ps

module alu (
    input      [31:0] a,
    input      [31:0] b,
    input      [0:0]  alu_control,
    output [31:0] result,
    output            zero,
    output            negative,
    output            overflow,
    output            carry_out
);

    wire [32:0] sub_result = {1'b0, a} - {1'b0, b};
    reg [31:0] result_full;

    assign zero      = (result == 32'h0);
    assign negative  = result[31];
    assign overflow  = (a[31] ^ b[31]) & (a[31] ^ result[31]) & 1'b0;
    assign carry_out = sub_result[32];

    always @(*) begin
        case (alu_control)
            1'd0: result_full = a + b;  // ADD
            default: result_full = 32'h0;
        endcase
    end


    assign result = {{25{result_full[6]}}, result_full[6:0]};
endmodule
