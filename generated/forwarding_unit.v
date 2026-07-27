// Auto-generated forwarding_unit (register-index width matches
// REG_INDEX_WIDTH so this module's own ports genuinely narrow, instead of
// relying on the surrounding pipeline_top.v wires implicitly pruning a
// wider port -- real gate savings on top of the width match.
`timescale 1ns / 1ps

module forwarding_unit (
    input      [3:0]  id_ex_rs1,
    input      [3:0]  id_ex_rs2,
    input      [3:0]  ex_mem_rd,
    input             ex_mem_reg_write,
    input      [3:0]  mem_wb_rd,
    input             mem_wb_reg_write,
    output reg [1:0]  forward_a,
    output reg [1:0]  forward_b
);

    always @(*) begin
        forward_a = 2'b00;
        if (mem_wb_reg_write &&
            (mem_wb_rd != 4'b0000) &&
            (mem_wb_rd == id_ex_rs1))
            forward_a = 2'b01;
        if (ex_mem_reg_write &&
            (ex_mem_rd != 4'b0000) &&
            (ex_mem_rd == id_ex_rs1))
            forward_a = 2'b10;

        forward_b = 2'b00;
        if (mem_wb_reg_write &&
            (mem_wb_rd != 4'b0000) &&
            (mem_wb_rd == id_ex_rs2))
            forward_b = 2'b01;
        if (ex_mem_reg_write &&
            (ex_mem_rd != 4'b0000) &&
            (ex_mem_rd == id_ex_rs2))
            forward_b = 2'b10;
    end

endmodule
