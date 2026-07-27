// Auto-generated pipeline register: MEM/WB (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module mem_wb_reg (
    input clk,
    input reset,
    input [6:0] pc_plus4_in,
    input [31:0] alu_result_in,
    input [31:0] mem_read_data_in,
    input [3:0] rd_in,
    input reg_write_in,
    input [1:0] mem_to_reg_in,
    output reg [6:0] pc_plus4_out,
    output reg [31:0] alu_result_out,
    output reg [31:0] mem_read_data_out,
    output reg [3:0] rd_out,
    output reg reg_write_out,
    output reg [1:0] mem_to_reg_out
);
always @(posedge clk or posedge reset) begin
    if (reset) begin
        pc_plus4_out <= 7'h0;
        alu_result_out <= 32'h0;
        mem_read_data_out <= 32'h0;
        rd_out <= 4'h0;
        reg_write_out <= 1'b0;
        mem_to_reg_out <= 2'h0;
    end else begin
        pc_plus4_out <= pc_plus4_in;
        alu_result_out <= alu_result_in;
        mem_read_data_out <= mem_read_data_in;
        rd_out <= rd_in;
        reg_write_out <= reg_write_in;
        mem_to_reg_out <= mem_to_reg_in;
    end
end
endmodule
