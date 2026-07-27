// Auto-generated pipeline register: ID/EX (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module id_ex_reg (
    input clk,
    input reset,
    input flush,
    input [6:0] pc_in,
    input [6:0] pc_plus4_in,
    input [31:0] read_data1_in,
    input [31:0] read_data2_in,
    input [6:0] imm_in,
    input [31:0] instruction_in,
    input [3:0] rs1_in,
    input [3:0] rs2_in,
    input [3:0] rd_in,
    input [0:0] alu_op_in,
    input alu_src_in,
    input mem_read_in,
    input mem_write_in,
    input [2:0] funct3_in,
    input reg_write_in,
    input [1:0] mem_to_reg_in,
    input branch_in,
    input jump_in,
    input jalr_in,
    output reg [6:0] pc_out,
    output reg [6:0] pc_plus4_out,
    output reg [31:0] read_data1_out,
    output reg [31:0] read_data2_out,
    output reg [6:0] imm_out,
    output reg [31:0] instruction_out,
    output reg [3:0] rs1_out,
    output reg [3:0] rs2_out,
    output reg [3:0] rd_out,
    output reg [0:0] alu_op_out,
    output reg alu_src_out,
    output reg mem_read_out,
    output reg mem_write_out,
    output reg [2:0] funct3_out,
    output reg reg_write_out,
    output reg [1:0] mem_to_reg_out,
    output reg branch_out,
    output reg jump_out,
    output reg jalr_out
);
always @(posedge clk or posedge reset) begin
    if (reset || flush) begin
        pc_out <= 7'h0;
        pc_plus4_out <= 7'h0;
        read_data1_out <= 32'h0;
        read_data2_out <= 32'h0;
        imm_out <= 7'h0;
        instruction_out <= 32'h00000013;
        rs1_out <= 4'h0;
        rs2_out <= 4'h0;
        rd_out <= 4'h0;
        alu_op_out <= 1'h0;
        alu_src_out <= 1'b0;
        mem_read_out <= 1'b0;
        mem_write_out <= 1'b0;
        funct3_out <= 3'b000;
        reg_write_out <= 1'b0;
        mem_to_reg_out <= 2'h0;
        branch_out <= 1'b0;
        jump_out <= 1'b0;
        jalr_out <= 1'b0;
    end else begin
        pc_out <= pc_in;
        pc_plus4_out <= pc_plus4_in;
        read_data1_out <= read_data1_in;
        read_data2_out <= read_data2_in;
        imm_out <= imm_in;
        instruction_out <= instruction_in;
        rs1_out <= rs1_in;
        rs2_out <= rs2_in;
        rd_out <= rd_in;
        alu_op_out <= alu_op_in;
        alu_src_out <= alu_src_in;
        mem_read_out <= mem_read_in;
        mem_write_out <= mem_write_in;
        funct3_out <= funct3_in;
        reg_write_out <= reg_write_in;
        mem_to_reg_out <= mem_to_reg_in;
        branch_out <= branch_in;
        jump_out <= jump_in;
        jalr_out <= jalr_in;
    end
end
endmodule
