#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PC_WIDTH = 12
DATA_WIDTH = 32
IMM_WIDTH = 32
REG_INDEX_WIDTH = 5
ALU_OP_WIDTH = 2
MEM_TO_REG_WIDTH = 2


def load_widths(profile_path: Path, outdir: Path):
    global PC_WIDTH, IMM_WIDTH, REG_INDEX_WIDTH, ALU_OP_WIDTH, MEM_TO_REG_WIDTH
    # PC_WIDTH now comes from pc_width.txt (written by gen_pc.py into the
    # same output directory), which computes it from the actual program
    # length + halt-detection drain margin -- see gen_pc.py's module
    # docstring for why pc.v / pc_adder.v / instruction_memory.v / these
    # pipeline registers / pipeline_top.v must all agree on this EXACT
    # value, or the primary addressing path reintroduces a proven
    # wraparound bug. Falls back to a conservative default if gen_pc.py
    # hasn't been run yet, so this script still works standalone.
    pc_width_path = outdir / 'pc_width.txt'
    if pc_width_path.exists():
        PC_WIDTH = max(1, int(pc_width_path.read_text(encoding='utf-8').strip()))
    else:
        PC_WIDTH = 12

    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    rec = profile.get('recommended_trim', {})
    IMM_WIDTH = max(1, int(rec.get('imm_width', 32)))
    REG_INDEX_WIDTH = max(1, int(rec.get('register_index_width', 5)))

    # alu_op / mem_to_reg widths come from encoding_plan.json (written by
    # gen_dense_control.py into the same output directory), NOT from
    # bit_profile.json -- they depend on which DISTINCT control codes are
    # exercised, which encoding_plan.py computes, not on any bit-range
    # profiling. If gen_dense_control.py hasn't been run yet (or the
    # dense-encoding mode isn't being used at all), fall back to the
    # original fixed widths (2 bits each) so this script still works
    # standalone.
    plan_path = outdir / 'encoding_plan.json'
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        ALU_OP_WIDTH = max(1, int(plan.get('alu_op_width', 2)))
        MEM_TO_REG_WIDTH = max(1, int(plan.get('mem_to_reg_width', 2)))
    else:
        ALU_OP_WIDTH = 2
        MEM_TO_REG_WIDTH = 2


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def gen_if_id() -> str:
    pcw = PC_WIDTH
    return f'''// Auto-generated pipeline register: IF/ID (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module if_id_reg (
    input clk,
    input reset,
    input if_id_write,
    input if_id_flush,
    input [{pcw-1}:0] pc_in,
    input [{pcw-1}:0] pc_plus4_in,
    input [31:0] instruction_in,
    output reg [{pcw-1}:0] pc_out,
    output reg [{pcw-1}:0] pc_plus4_out,
    output reg [31:0] instruction_out
);
always @(posedge clk or posedge reset) begin
    if (reset) begin
        pc_out <= {pcw}'h0;
        pc_plus4_out <= {pcw}'h0;
        instruction_out <= 32'h00000013;
    end else if (if_id_flush) begin
        pc_out <= {pcw}'h0;
        pc_plus4_out <= {pcw}'h0;
        instruction_out <= 32'h00000013;
    end else if (if_id_write) begin
        pc_out <= pc_in;
        pc_plus4_out <= pc_plus4_in;
        instruction_out <= instruction_in;
    end
end
endmodule
'''


def gen_id_ex() -> str:
    pcw, dw, immw, riw = PC_WIDTH, DATA_WIDTH, IMM_WIDTH, REG_INDEX_WIDTH
    aow, mtw = ALU_OP_WIDTH, MEM_TO_REG_WIDTH
    return f'''// Auto-generated pipeline register: ID/EX (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module id_ex_reg (
    input clk,
    input reset,
    input flush,
    input [{pcw-1}:0] pc_in,
    input [{pcw-1}:0] pc_plus4_in,
    input [{dw-1}:0] read_data1_in,
    input [{dw-1}:0] read_data2_in,
    input [{immw-1}:0] imm_in,
    input [31:0] instruction_in,
    input [{riw-1}:0] rs1_in,
    input [{riw-1}:0] rs2_in,
    input [{riw-1}:0] rd_in,
    input [{aow-1}:0] alu_op_in,
    input alu_src_in,
    input mem_read_in,
    input mem_write_in,
    input [2:0] funct3_in,
    input reg_write_in,
    input [{mtw-1}:0] mem_to_reg_in,
    input branch_in,
    input jump_in,
    input jalr_in,
    output reg [{pcw-1}:0] pc_out,
    output reg [{pcw-1}:0] pc_plus4_out,
    output reg [{dw-1}:0] read_data1_out,
    output reg [{dw-1}:0] read_data2_out,
    output reg [{immw-1}:0] imm_out,
    output reg [31:0] instruction_out,
    output reg [{riw-1}:0] rs1_out,
    output reg [{riw-1}:0] rs2_out,
    output reg [{riw-1}:0] rd_out,
    output reg [{aow-1}:0] alu_op_out,
    output reg alu_src_out,
    output reg mem_read_out,
    output reg mem_write_out,
    output reg [2:0] funct3_out,
    output reg reg_write_out,
    output reg [{mtw-1}:0] mem_to_reg_out,
    output reg branch_out,
    output reg jump_out,
    output reg jalr_out
);
always @(posedge clk or posedge reset) begin
    if (reset || flush) begin
        pc_out <= {pcw}'h0;
        pc_plus4_out <= {pcw}'h0;
        read_data1_out <= {dw}'h0;
        read_data2_out <= {dw}'h0;
        imm_out <= {immw}'h0;
        instruction_out <= 32'h00000013;
        rs1_out <= {riw}'h0;
        rs2_out <= {riw}'h0;
        rd_out <= {riw}'h0;
        alu_op_out <= {aow}'h0;
        alu_src_out <= 1'b0;
        mem_read_out <= 1'b0;
        mem_write_out <= 1'b0;
        funct3_out <= 3'b000;
        reg_write_out <= 1'b0;
        mem_to_reg_out <= {mtw}'h0;
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
'''


def gen_ex_mem() -> str:
    pcw, dw, riw = PC_WIDTH, DATA_WIDTH, REG_INDEX_WIDTH
    mtw = MEM_TO_REG_WIDTH
    return f'''// Auto-generated pipeline register: EX/MEM (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module ex_mem_reg (
    input clk,
    input reset,
    input flush,
    input [{pcw-1}:0] pc_plus4_in,
    input [31:0] alu_result_in,
    input [{dw-1}:0] write_data_in,
    input [{pcw-1}:0] branch_target_in,
    input zero_in,
    input branch_taken_in,
    input [{riw-1}:0] rd_in,
    input mem_read_in,
    input mem_write_in,
    input [2:0] funct3_in,
    input reg_write_in,
    input [{mtw-1}:0] mem_to_reg_in,
    input jump_in,
    output reg [{pcw-1}:0] pc_plus4_out,
    output reg [31:0] alu_result_out,
    output reg [{dw-1}:0] write_data_out,
    output reg [{pcw-1}:0] branch_target_out,
    output reg zero_out,
    output reg branch_taken_out,
    output reg [{riw-1}:0] rd_out,
    output reg mem_read_out,
    output reg mem_write_out,
    output reg [2:0] funct3_out,
    output reg reg_write_out,
    output reg [{mtw-1}:0] mem_to_reg_out,
    output reg jump_out
);
always @(posedge clk or posedge reset) begin
    if (reset || flush) begin
        pc_plus4_out <= {pcw}'h0;
        alu_result_out <= 32'h0;
        write_data_out <= {dw}'h0;
        branch_target_out <= {pcw}'h0;
        zero_out <= 1'b0;
        branch_taken_out <= 1'b0;
        rd_out <= {riw}'h0;
        mem_read_out <= 1'b0;
        mem_write_out <= 1'b0;
        funct3_out <= 3'b000;
        reg_write_out <= 1'b0;
        mem_to_reg_out <= {mtw}'h0;
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
'''


def gen_mem_wb() -> str:
    pcw, dw, riw = PC_WIDTH, DATA_WIDTH, REG_INDEX_WIDTH
    mtw = MEM_TO_REG_WIDTH
    return f'''// Auto-generated pipeline register: MEM/WB (strict-mode profile-driven widths)
`timescale 1ns / 1ps
module mem_wb_reg (
    input clk,
    input reset,
    input [{pcw-1}:0] pc_plus4_in,
    input [31:0] alu_result_in,
    input [{dw-1}:0] mem_read_data_in,
    input [{riw-1}:0] rd_in,
    input reg_write_in,
    input [{mtw-1}:0] mem_to_reg_in,
    output reg [{pcw-1}:0] pc_plus4_out,
    output reg [31:0] alu_result_out,
    output reg [{dw-1}:0] mem_read_data_out,
    output reg [{riw-1}:0] rd_out,
    output reg reg_write_out,
    output reg [{mtw-1}:0] mem_to_reg_out
);
always @(posedge clk or posedge reset) begin
    if (reset) begin
        pc_plus4_out <= {pcw}'h0;
        alu_result_out <= 32'h0;
        mem_read_data_out <= {dw}'h0;
        rd_out <= {riw}'h0;
        reg_write_out <= 1'b0;
        mem_to_reg_out <= {mtw}'h0;
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
'''


def gen_forwarding_unit() -> str:
    riw = REG_INDEX_WIDTH
    zero = f"{riw}'b" + "0" * riw
    return f'''// Auto-generated forwarding_unit (register-index width matches
// REG_INDEX_WIDTH so this module's own ports genuinely narrow, instead of
// relying on the surrounding pipeline_top.v wires implicitly pruning a
// wider port -- real gate savings on top of the width match.
`timescale 1ns / 1ps

module forwarding_unit (
    input      [{riw-1}:0]  id_ex_rs1,
    input      [{riw-1}:0]  id_ex_rs2,
    input      [{riw-1}:0]  ex_mem_rd,
    input             ex_mem_reg_write,
    input      [{riw-1}:0]  mem_wb_rd,
    input             mem_wb_reg_write,
    output reg [1:0]  forward_a,
    output reg [1:0]  forward_b
);

    always @(*) begin
        forward_a = 2'b00;
        if (mem_wb_reg_write &&
            (mem_wb_rd != {zero}) &&
            (mem_wb_rd == id_ex_rs1))
            forward_a = 2'b01;
        if (ex_mem_reg_write &&
            (ex_mem_rd != {zero}) &&
            (ex_mem_rd == id_ex_rs1))
            forward_a = 2'b10;

        forward_b = 2'b00;
        if (mem_wb_reg_write &&
            (mem_wb_rd != {zero}) &&
            (mem_wb_rd == id_ex_rs2))
            forward_b = 2'b01;
        if (ex_mem_reg_write &&
            (ex_mem_rd != {zero}) &&
            (ex_mem_rd == id_ex_rs2))
            forward_b = 2'b10;
    end

endmodule
'''


def gen_hazard_unit() -> str:
    riw = REG_INDEX_WIDTH
    zero = f"{riw}'b" + "0" * riw
    return f'''// Auto-generated hazard_unit (register-index width matches REG_INDEX_WIDTH,
// same reasoning as forwarding_unit above). Logic is otherwise identical
// to the original hand-written version (3-stage branch/jump flush).
`timescale 1ns / 1ps

module hazard_unit (
    input             id_ex_mem_read,
    input      [{riw-1}:0]  id_ex_rd,
    input      [{riw-1}:0]  if_id_rs1,
    input      [{riw-1}:0]  if_id_rs2,
    input             branch_taken,
    input             jump,
    output reg        pc_write,
    output reg        if_id_write,
    output reg        if_id_flush,
    output reg        id_ex_flush,
    output reg        ex_mem_flush
);

    always @(*) begin
        pc_write     = 1'b1;
        if_id_write  = 1'b1;
        if_id_flush  = 1'b0;
        id_ex_flush  = 1'b0;
        ex_mem_flush = 1'b0;

        if (id_ex_mem_read &&
            (id_ex_rd != {zero}) &&
            ((id_ex_rd == if_id_rs1) ||
             (id_ex_rd == if_id_rs2))) begin
            pc_write    = 1'b0;
            if_id_write = 1'b0;
            id_ex_flush = 1'b1;
        end

        // NOTE: ex_mem_flush is deliberately NOT asserted here, even
        // though an earlier version of this module did. At the cycle
        // branch_taken/jump resolves, EX holds the branch/jump
        // instruction ITSELF -- valid, and (for jal/jalr) about to
        // write a real return address to rd. Asserting ex_mem_flush at
        // this same cycle discards that instruction's own transition
        // into MEM, silently dropping its write-back before it ever
        // reaches the register file. Proven via simulation: a nested
        // function call's `jal ra, callee` had its return-address
        // write to ra discarded this way, so the caller's own later
        // `ret` used a stale, pre-call ra value instead and jumped to
        // the wrong place. Branches never exposed this because a
        // branch never has reg_write=1 in the first place, so
        // discarding its own MEM transition was always harmless by
        // coincidence -- jal/jalr do, so it wasn't. Only if_id_flush
        // and id_ex_flush are needed: they discard the two
        // speculatively-fetched, genuinely wrong-path instructions
        // that were fetched sequentially before the redirect was known
        // (currently sitting in IF and ID), which is the only actual
        // misprediction to clean up.
        if ((branch_taken || jump) && pc_write) begin
            if_id_flush  = 1'b1;
            id_ex_flush  = 1'b1;
        end
    end

endmodule
'''


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) != 3:
        print('Usage: python3 tools/gen_pipeline_regs.py <bit_profile.json> <outdir>')
        return 1
    profile_path = Path(argv[1])
    outdir = Path(argv[2])
    load_widths(profile_path, outdir)
    write(outdir / 'if_id_reg.v', gen_if_id())
    write(outdir / 'id_ex_reg.v', gen_id_ex())
    write(outdir / 'ex_mem_reg.v', gen_ex_mem())
    write(outdir / 'mem_wb_reg.v', gen_mem_wb())
    write(outdir / 'forwarding_unit.v', gen_forwarding_unit())
    write(outdir / 'hazard_unit.v', gen_hazard_unit())
    print(f'Generated (strict profile-driven widths, pc={PC_WIDTH} data={DATA_WIDTH} imm={IMM_WIDTH} reg_index={REG_INDEX_WIDTH}):')
    print(f"  {outdir / 'if_id_reg.v'}")
    print(f"  {outdir / 'id_ex_reg.v'}")
    print(f"  {outdir / 'ex_mem_reg.v'}")
    print(f"  {outdir / 'mem_wb_reg.v'}")
    print(f"  {outdir / 'forwarding_unit.v'}")
    print(f"  {outdir / 'hazard_unit.v'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())