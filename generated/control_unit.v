// ============================================================
// Module      : control_unit
// File        : control_unit.v
// Description : Auto-generated, DENSE encoding mode. alu_op (1 bits)
//               and mem_to_reg (2 bits) use minimal-width codes
//               computed by encoding_plan.py for exactly the instructions
//               this program uses -- see that file's docstring. Do not
//               hand-edit the widths or codes here without regenerating
//               alu_control.v / alu.v / the pipeline registers /
//               pipeline_top.v from the SAME plan, or the codes will
//               silently disagree between modules.
// ============================================================
`timescale 1ns / 1ps

module control_unit (
    input      [6:0]  opcode,
    input      [4:0]  rd,
    output reg        branch,
    output reg        mem_read,
    output reg [1:0]  mem_to_reg,
    output reg [0:0]  alu_op,
    output reg        mem_write,
    output reg        alu_src,
    output reg        reg_write,
    output reg        jump,
    output reg        jalr
);

    reg reg_write_internal;

    always @(*) begin
        branch             = 1'b0;
        mem_read           = 1'b0;
        mem_to_reg         = 2'd0;
        alu_op             = 1'd0;
        mem_write          = 1'b0;
        alu_src            = 1'b0;
        reg_write_internal = 1'b0;
        jump               = 1'b0;
        jalr               = 1'b0;

        case (opcode)

            // I-type ALU/immediate ops: addi, andi, ori, xori, slti, ...
            7'b0010011: begin
                reg_write_internal = 1'b1;
                alu_op             = 1'd1;
                alu_src            = 1'b1;
            end

            // Loads: lw, lh, lb, lhu, lbu
            7'b0000011: begin
                reg_write_internal = 1'b1;
                mem_read           = 1'b1;
                alu_op             = 1'd0;
                alu_src            = 1'b1;
                mem_to_reg         = 2'd1;
            end

            // Stores: sw, sh, sb
            7'b0100011: begin
                mem_write          = 1'b1;
                alu_op             = 1'd0;
                alu_src            = 1'b1;
            end

            // JAL
            7'b1101111: begin
                reg_write_internal = 1'b1;
                jump               = 1'b1;
                mem_to_reg         = 2'd2;
                alu_src            = 1'b1;
            end

            // JALR
            7'b1100111: begin
                reg_write_internal = 1'b1;
                jump               = 1'b1;
                jalr               = 1'b1;
                mem_to_reg         = 2'd2;
                alu_src            = 1'b1;
                alu_op             = 1'd0;
            end

            // Custom instructions (custom_mul/mulh/mulhu/mac/reserved,
            // disambiguated by funct3 inside custom_unit.v, not here).
            // Register operands (rs1, rs2) -- alu_src stays at its
            // default 0. Result flows through ex_result -> alu_result_wb
            // regardless of alu_op (custom_en_ex selects custom_result_ex
            // directly, bypassing the ALU entirely), and write_back_data's
            // default "alu" source (mem_to_reg=0) already picks that up
            // correctly -- reg_write is the only signal this actually
            // needs. Missing this case entirely (falling through to
            // default, which never asserts reg_write) was a real,
            // previously-unresolved bug: the custom instruction's result
            // computed correctly through the datapath, but never
            // committed to the register file. Confirmed via simulation:
            // a custom_mul(6,7) computed 42 on the write-back bus every
            // time, but the destination register stayed at whatever
            // value it held before the instruction ever ran.
            7'b0001011: begin
                reg_write_internal = 1'b1;
            end

            default: begin
            end
        endcase

        reg_write = (rd == 5'b00000) ? 1'b0 : reg_write_internal;
    end

endmodule
