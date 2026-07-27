// Auto-generated pipeline register: EX/MEM (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module ex_mem_reg (
    input clk,
    input reset,
    input flush,
    input [6:0] pc_plus4_in,
    input [31:0] alu_result_in,
    input [31:0] write_data_in,
    input [6:0] branch_target_in,
    input zero_in,
    input branch_taken_in,
    input [3:0] rd_in,
    input mem_read_in,
    input mem_write_in,
    input [2:0] funct3_in,
    input reg_write_in,
    input [1:0] mem_to_reg_in,
    input jump_in,
    output reg [6:0] pc_plus4_out,
    output reg [31:0] alu_result_out,
    output reg [31:0] write_data_out,
    output reg [6:0] branch_target_out,
    output reg zero_out,
    output reg branch_taken_out,
    output reg [3:0] rd_out,
    output reg mem_read_out,
    output reg mem_write_out,
    output reg [2:0] funct3_out,
    output reg reg_write_out,
    output reg [1:0] mem_to_reg_out,
    output reg jump_out
);
always @(posedge clk or posedge reset) begin
    if (reset || flush) begin
        pc_plus4_out <= 7'h0;
        alu_result_out <= 32'h0;
        write_data_out <= 32'h0;
        branch_target_out <= 7'h0;
        zero_out <= 1'b0;
        branch_taken_out <= 1'b0;
        rd_out <= 4'h0;
        mem_read_out <= 1'b0;
        mem_write_out <= 1'b0;
        funct3_out <= 3'b000;
        reg_write_out <= 1'b0;
        mem_to_reg_out <= 2'h0;
        jump_out <= 1'b0;
    end else begin
        pc_plus4_out <= pc_plus4_in;
        alu_result_out <= alu_result_in;
        write_data_out <= write_data_in;
        branch_target_out <= branch_target_in;
        zero_out <= zero_in;
        branch_taken_out <= branch_taken_in;
        rd_out <= rd_in;
        mem_read_out <= mem_read_in;
        mem_write_out <= mem_write_in;
        funct3_out <= funct3_in;
        reg_write_out <= reg_write_in;
        mem_to_reg_out <= mem_to_reg_in;
        jump_out <= jump_in;
    end
end
endmodule
