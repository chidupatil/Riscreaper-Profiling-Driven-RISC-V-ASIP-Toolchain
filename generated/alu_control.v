// ============================================================
// Module      : alu_control
// File        : alu_control.v
// Description : Auto-generated, DENSE encoding mode. See control_unit.v's
//               header -- alu_op (1 bits) and alu_control (1 bits)
//               widths/codes come from the same encoding_plan.py computed
//               from this program's actual instructions.
// ============================================================
`timescale 1ns / 1ps

module alu_control (
    input      [0:0]  alu_op,
    input      [2:0]  funct3,
    input             funct7,
    input             is_rtype,
    output reg [0:0]  alu_control
);

    always @(*) begin
        case (alu_op)
            1'd0: alu_control = 1'd0;

            1'd1: begin
                case (funct3)
                    3'b000: alu_control = 1'd0;
                    default: alu_control = 1'd0;
                endcase
            end

            default: alu_control = 1'd0;
        endcase
    end

endmodule
