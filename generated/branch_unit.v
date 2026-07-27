`timescale 1ns / 1ps

module branch_unit (
    input      [2:0] funct3,
    input            branch,
    input            zero,
    input            negative,
    input            overflow,
    input            carry_out,
    output reg       branch_taken
);

    always @(*) begin
        if (!branch) begin
            branch_taken = 1'b0;
        end else begin
            case (funct3)














                default: branch_taken = 1'b0;
            endcase
        end
    end

endmodule