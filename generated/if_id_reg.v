// Auto-generated pipeline register: IF/ID (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module if_id_reg (
    input clk,
    input reset,
    input if_id_write,
    input if_id_flush,
    input [6:0] pc_in,
    input [6:0] pc_plus4_in,
    input [31:0] instruction_in,
    output reg [6:0] pc_out,
    output reg [6:0] pc_plus4_out,
    output reg [31:0] instruction_out
);
always @(posedge clk or posedge reset) begin
    if (reset) begin
        pc_out <= 7'h0;
        pc_plus4_out <= 7'h0;
        instruction_out <= 32'h00000013;
    end else if (if_id_flush) begin
        pc_out <= 7'h0;
        pc_plus4_out <= 7'h0;
        instruction_out <= 32'h00000013;
    end else if (if_id_write) begin
        pc_out <= pc_in;
        pc_plus4_out <= pc_plus4_in;
        instruction_out <= instruction_in;
    end
end
endmodule
