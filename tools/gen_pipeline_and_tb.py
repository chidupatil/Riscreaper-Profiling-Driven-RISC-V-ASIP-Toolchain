#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def sanitize(name: str) -> str:
    s = re.sub(r'[^A-Za-z0-9]+', '_', str(name).strip())
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'program'


def infer_program_name(summary: dict, json_path: Path) -> str:
    for key in ('program', 'name', 'basename', 'source', 'elf', 'input'):
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).stem
    return json_path.stem.replace('_insts', '')


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Instruction summary must be a JSON object')
    return data


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def load_trim_profile(inst_json_path: Path, summary: dict) -> dict:
    rec = summary.get('recommended_trim')
    if not isinstance(rec, dict):
        profile_path = inst_json_path.with_name(inst_json_path.name.replace('_insts.json', '_bit_profile.json'))
        if profile_path.exists():
            prof = load_json(profile_path)
            rec = prof.get('recommended_trim', {})
        else:
            rec = {}

    alu_width = max(1, min(int(rec.get('alu_width', 32)), 32))
    imm_width = max(1, min(int(rec.get('imm_width', 32)), 32))
    reg_idx_width = max(1, min(int(rec.get('register_index_width', 5)), 5))

    return {
        'alu_width': alu_width,
        'imm_width': imm_width,
        'reg_index_width': reg_idx_width,
    }


def sext_expr(signal: str, width: int) -> str:
    """Reconstruct a narrowed SIGNED value (immediates, ALU results) back to
    32 bits. Only correct for genuinely signed quantities."""
    if width >= 32:
        return signal
    sign = f'{signal}[{width - 1}]'
    return f'{{{{{32 - width}{{{sign}}}}}, {signal}}}'


def zext_expr(signal: str, width: int) -> str:
    """Reconstruct a narrowed UNSIGNED value (PC / addresses) back to 32
    bits. PC is never negative -- using sext_expr here would be a real bug:
    any PC value >= 2**(width-1) has its top representable bit set purely
    because it's a large-but-valid address, not because it's negative.
    Sign-extending it would corrupt roughly half of all representable PC
    values into large bogus numbers (verified: PC=20 at width=5 sign-
    extends to -12 instead of 20)."""
    if width >= 32:
        return signal
    return f'{{{{{32 - width}{{1\'b0}}}}, {signal}}}'


def make_pipeline_top(alu_width: int, imm_width: int, reg_index_width: int, pc_width: int, has_custom: bool = True, has_branch: bool = True, has_hazard: bool = True, plan: dict | None = None) -> str:
    """
    DESIGN NOTE ON PC WIDTH:
    -------------------------
    pc_width is now computed by gen_pc.py and passed in here, and MUST be
    the exact same value used to generate pc.v and pc_adder.v (via
    gen_pc.py) and instruction_memory.v's `pc` port (via
    gen_instruction_memory.py). All four must agree, or the primary
    addressing path reintroduces a proven bug.

    An earlier version of this project narrowed pc_out/pc_plus4_if to a
    narrow WIRE while pc.v/pc_adder.v stayed unmodified, always-32-bit
    modules. That meant pc_adder.v computed pc_in + 4 at full 32-bit
    precision internally, and the correct result got silently truncated
    the moment it was captured into the narrow wire -- proven with a
    real simulation: a backward-branch loop wrapped PC around at the
    narrow boundary and re-executed the entire program forever instead
    of halting.

    The fix is not "never narrow PC" -- it's "narrow the modules that
    compute it too, consistently, so the addition happens AT the narrow
    width with well-defined wraparound semantics at exactly the
    boundary it was sized for, not an accidental truncation of a wider
    computation." gen_pc.py's pc.v/pc_adder.v do exactly that, and this
    function's pc_out/pc_plus4_if/pc_next wires (and the pc.v/
    pc_adder.v/instruction_memory.v instantiations below) are generated
    at that SAME width, so there is no mismatch anywhere on the primary
    path. See gen_pc.py's module docstring for how pc_width is sized
    (program length + halt-detection drain margin).

    The SAME pc_width is also used for the pipeline-carried PC copies
    (pc_id, pc_ex, pc_plus4_id/ex/mem/wb) used for branch/AUIPC target
    arithmetic and the JAL/JALR link-register value. Both are
    reconstructed back to 32 bits at the point of use via explicit
    ZERO-extension (PC is unsigned) -- not sign-extension, which was a
    second bug found: reconstructing a narrowed PC value via
    sign-extension corrupts any PC whose top representable bit happens
    to be 1 (roughly half of all valid addresses in range), regardless
    of whether that PC is anywhere near the "end" of the program.
    Verified: PC=20 at 5-bit width sign-extended to -12 instead of 20.

    DESIGN NOTE ON alu_op / alu_control / mem_to_reg WIDTHS:
    -----------------------------------------------------------
    `plan` (from encoding_plan.compute_plan(), also consumed by
    gen_dense_control.py and gen_pipeline_regs.py) supplies DENSE widths
    and codes for these three control signals. If `plan` is None, this
    falls back to the ORIGINAL fixed widths (alu_op=2, alu_control=4,
    mem_to_reg=2) with the ORIGINAL codes, matching what
    gen_control_from_insts.py's template-based control_unit.v /
    alu_control.v / alu.v produce -- i.e. this function still works
    correctly if you are NOT using the dense-encoding generators. If you
    ARE using them (gen_dense_control.py), `plan` MUST be the exact same
    plan passed to that script, or the codes will not match.
    """
    if plan is None:
        alu_op_width = 2
        alu_control_width = 4
        mem_to_reg_width = 2
        mem_to_reg_codes = {"alu": 0, "mem": 1, "pcplus4": 2}
    else:
        alu_op_width = plan["alu_op_width"]
        alu_control_width = plan["alu_control_width"]
        mem_to_reg_width = plan["mem_to_reg_width"]
        mem_to_reg_codes = plan["mem_to_reg_codes"]

    alu_msb = alu_width - 1
    imm_msb = imm_width - 1
    reg_msb = reg_index_width - 1
    aop_msb = alu_op_width - 1
    actl_msb = alu_control_width - 1
    mtr_msb = mem_to_reg_width - 1
    pc_msb = pc_width - 1

    imm_id_sext_expr = sext_expr('imm_id', imm_width)
    imm_ex_sext_expr = sext_expr('imm_ex', imm_width)
    pc_ex_zext_expr = zext_expr('pc_ex', pc_width)
    pc_plus4_wb_zext_expr = zext_expr('pc_plus4_wb', pc_width)
    # NOTE: jalr_target and branch_target_ex are NOT zero-extended here.
    # pc_next is generated at the SAME pc_width as both of them (all
    # part of the consistently-narrowed primary addressing path), so no
    # extension is needed for THIS use -- unlike pc_ex/pc_plus4_wb above,
    # which feed into the still-32-bit ALU/register-file data path and
    # genuinely need zero-extending back up.

    # write_back_data: built from whichever mem_to_reg sources are
    # actually in the plan. If only "alu" is ever needed (no loads, no
    # jal/jalr in this program), the mux collapses entirely -- not just
    # narrower control bits, but the 3:1 write-back mux itself is gone.
    has_mem_src = "mem" in mem_to_reg_codes
    has_pcplus4_src = "pcplus4" in mem_to_reg_codes
    if not has_mem_src and not has_pcplus4_src:
        write_back_data_expr = "alu_result_wb"
    else:
        mtw = mem_to_reg_width
        arms = []
        if has_mem_src:
            arms.append(f"(mem_to_reg_wb == {mtw}'d{mem_to_reg_codes['mem']}) ? mem_read_data_wb :")
        if has_pcplus4_src:
            arms.append(f"(mem_to_reg_wb == {mtw}'d{mem_to_reg_codes['pcplus4']}) ? {pc_plus4_wb_zext_expr} :")
        write_back_data_expr = "\n        " + "\n        ".join(arms) + "\n                                   alu_result_wb"

    rs1_hi = 14 + reg_index_width
    rs2_hi = 19 + reg_index_width
    rd_hi = 6 + reg_index_width

    text = f'''// ============================================================
// Module      : RISC-V 5-Stage Pipeline Top
// File        : pipeline_top.v
// Description : Top-level module connecting all pipeline stages.
//               STRICT MODE: immediate / ALU / register-index paths are
//               profile-driven per program. PC stays full-width at the
//               primary fetch/address level (pc.v/pc_adder.v/
//               instruction_memory.v are unmodified); only the
//               pipeline-carried PC copies used for branch/JAL(R)
//               arithmetic are narrowed, and reconstructed via
//               zero-extension (PC is unsigned) at the point of use.
// ============================================================

`timescale 1ns / 1ps

module pipeline_top (
    input         clk,
    input         reset,

    output        halted,
    output [31:0] dbg_pc,
    output [31:0] dbg_instr_if,
    output [31:0] dbg_instr_id,
    output [{alu_msb}:0] dbg_alu_result_ex,
    output        dbg_branch_taken_ex,
    output        dbg_mem_write_mem,
    output [{alu_msb}:0] dbg_mem_addr_mem,
    output [{alu_msb}:0] dbg_mem_wdata_mem,
    output        dbg_reg_write_wb,
    output [{reg_msb}:0] dbg_rd_wb,
    output [{alu_msb}:0] dbg_wb_data
);

    // IF stage -- pc_width bits, matching pc.v/pc_adder.v/instruction_memory.v
    // exactly (all generated together from the same computed pc_width).
    wire [{pc_msb}:0] pc_out;
    wire [{pc_msb}:0] pc_plus4_if;
    wire [31:0] instruction_if;
    wire [{pc_msb}:0] pc_next;
    wire        program_end_if;
    reg  [3:0]  drain_count;
    reg         halted_r;

    // IF/ID -- pipeline-carried PC copy, narrowed
    wire [{pc_msb}:0] pc_id;
    wire [{pc_msb}:0] pc_plus4_id;
    wire [31:0] instruction_id;

    // ID
    wire [31:0] read_data1_id;
    wire [31:0] read_data2_id;
    wire [{imm_msb}:0] imm_id;

    wire branch_id;
    wire mem_read_id;
    wire [{mtr_msb}:0] mem_to_reg_id;
    wire [{aop_msb}:0] alu_op_id;
    wire mem_write_id;
    wire alu_src_id;
    wire reg_write_id;
    wire jump_id;
    wire jalr_id;

    wire [{reg_msb}:0] rs1_id;
    wire [{reg_msb}:0] rs2_id;
    wire [{reg_msb}:0] rd_id;

    // ID/EX
    wire [{pc_msb}:0] pc_ex;
    wire [{pc_msb}:0] pc_plus4_ex;
    wire [31:0] read_data1_ex;
    wire [31:0] read_data2_ex;
    wire [{imm_msb}:0] imm_ex;
    wire [31:0] instruction_ex;
    wire [{reg_msb}:0] rs1_ex;
    wire [{reg_msb}:0] rs2_ex;
    wire [{reg_msb}:0] rd_ex;
    wire [{aop_msb}:0] alu_op_ex;
    wire alu_src_ex;
    wire mem_read_ex;
    wire mem_write_ex;
    wire [2:0] funct3_ex;
    wire reg_write_ex;
    wire [{mtr_msb}:0] mem_to_reg_ex;
    wire branch_ex;
    wire jump_ex;
    wire jalr_ex;

    // EX
    wire [{actl_msb}:0] alu_control_ex;
    wire is_rtype_ex;
    wire [31:0] alu_input_a;
    wire [31:0] alu_input_b_pre;
    wire [31:0] alu_input_b;
    wire [31:0] alu_result_ex;
    wire zero_ex;
    wire negative_ex;
    wire overflow_ex;
    wire carry_out_ex;
    wire branch_taken_ex;
    wire [{pc_msb}:0] branch_target_ex;
    wire [1:0] forward_a;
    wire [1:0] forward_b;

    wire custom_en_ex;
    wire [31:0] custom_result_ex;
    wire [31:0] ex_result;
    wire custom_valid_ex;
    wire custom_stall_ex;
    wire [31:0] auipc_result;

    // EX/MEM -- pipeline-carried PC copy stays narrow; but nothing after
    // WB needs pc_plus4 for addressing, only for the JAL(R) link value.
    wire [{pc_msb}:0] pc_plus4_mem;
    wire [31:0] alu_result_mem;
    wire [31:0] write_data_mem;
    wire [{pc_msb}:0] branch_target_mem;
    wire zero_mem;
    wire branch_taken_mem;
    wire [{reg_msb}:0] rd_mem;
    wire mem_read_mem;
    wire mem_write_mem;
    wire [2:0] funct3_mem;
    wire reg_write_mem;
    wire [{mtr_msb}:0] mem_to_reg_mem;
    wire jump_mem;

    // MEM
    wire [31:0] mem_read_data_mem;

    // MEM/WB
    wire [{pc_msb}:0] pc_plus4_wb;
    wire [31:0] alu_result_wb;
    wire [31:0] mem_read_data_wb;
    wire [{reg_msb}:0] rd_wb;
    wire reg_write_wb;
    wire [{mtr_msb}:0] mem_to_reg_wb;

    // WB
    wire [31:0] write_back_data;

    // Hazard control
    wire pc_write;
    wire if_id_write;
    wire if_id_flush;
    wire id_ex_flush;
    wire ex_mem_flush;

    wire [{pc_msb}:0] jalr_target;
    wire is_auipc;

    wire [31:0] imm_id_sext;
    wire [31:0] imm_ex_sext;

    assign imm_id_sext = {imm_id_sext_expr};
    assign imm_ex_sext = {imm_ex_sext_expr};

    // jalr_target: computed at full 32-bit precision (read_data1_ex is a
    // real, potentially large register value -- e.g. a computed pointer),
    // THEN truncated to pc_width bits for storage, since the target
    // address itself is expected to be within the profiled program's
    // range. Truncating after the full-precision add, rather than
    // truncating the operands first, avoids losing carry information.
    wire [31:0] jalr_target_full;
    assign jalr_target_full = (read_data1_ex + imm_ex_sext) & ~32'h1;
    assign jalr_target = jalr_target_full[{pc_msb}:0];

    assign pc_next =
        (jump_ex && jalr_ex) ? jalr_target :
        (jump_ex)            ? branch_target_ex :
        (branch_taken_ex)    ? branch_target_ex :
                               pc_plus4_if;

    pc u_pc (
        .clk(clk),
        .reset(reset),
        .pc_write(pc_write),
        .pc_next(pc_next),
        .pc_out(pc_out)
    );

    pc_adder u_pc_adder (
        .pc_in(pc_out),
        .pc_plus4(pc_plus4_if)
    );

    instruction_memory u_imem (
        .pc(pc_out),
        .instruction(instruction_if),
        .program_end(program_end_if)
    );

    // Halt detection: once IF has been continuously fetching past the end
    // of the program (not just a transient fetch that a branch/jump flush
    // later discards) for DRAIN_CYCLES cycles, the last real instruction
    // has had time to fully drain through ID/EX/MEM/WB, so it is safe to
    // declare the program complete. If program_end_if ever goes back low
    // (a flushed speculative fetch past the end, later corrected by a
    // taken backward branch), the counter resets rather than firing early.
    // This operates entirely on the untouched, full-width pc_out ->
    // instruction_memory.v path, so it is unaffected by any of the
    // pipeline-register narrowing above.
    localparam DRAIN_CYCLES = 4'd6;
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            drain_count <= 4'd0;
            halted_r    <= 1'b0;
        end else if (halted_r) begin
            // stay halted
        end else if (program_end_if) begin
            if (drain_count >= DRAIN_CYCLES)
                halted_r <= 1'b1;
            else
                drain_count <= drain_count + 4'd1;
        end else begin
            drain_count <= 4'd0;
        end
    end
    assign halted = halted_r;

    if_id_reg u_if_id (
        .clk(clk),
        .reset(reset),
        .if_id_write(if_id_write),
        .if_id_flush(if_id_flush),
        .pc_in(pc_out[{pc_msb}:0]),
        .pc_plus4_in(pc_plus4_if[{pc_msb}:0]),
        .instruction_in(instruction_if),
        .pc_out(pc_id),
        .pc_plus4_out(pc_plus4_id),
        .instruction_out(instruction_id)
    );

    assign rs1_id = instruction_id[{rs1_hi}:15];
    assign rs2_id = instruction_id[{rs2_hi}:20];
    assign rd_id  = instruction_id[{rd_hi}:7];

    control_unit u_control (
        .opcode(instruction_id[6:0]),
        .rd(instruction_id[11:7]),
        .branch(branch_id),
        .mem_read(mem_read_id),
        .mem_to_reg(mem_to_reg_id),
        .alu_op(alu_op_id),
        .mem_write(mem_write_id),
        .alu_src(alu_src_id),
        .reg_write(reg_write_id),
        .jump(jump_id),
        .jalr(jalr_id)
    );

    register_file u_reg_file (
        .clk(clk),
        .reg_write(reg_write_wb),
        .rs1(rs1_id),
        .rs2(rs2_id),
        .rd(rd_wb),
        .write_data(write_back_data),
        .read_data1(read_data1_id),
        .read_data2(read_data2_id)
    );

    imm_gen u_imm_gen (
        .instruction(instruction_id),
        .imm_out(imm_id)
    );

    id_ex_reg u_id_ex (
        .clk(clk),
        .reset(reset),
        .flush(id_ex_flush),
        .pc_in(pc_id),
        .pc_plus4_in(pc_plus4_id),
        .read_data1_in(read_data1_id),
        .read_data2_in(read_data2_id),
        .imm_in(imm_id),
        .instruction_in(instruction_id),
        .rs1_in(rs1_id),
        .rs2_in(rs2_id),
        .rd_in(rd_id),
        .alu_op_in(alu_op_id),
        .alu_src_in(alu_src_id),
        .mem_read_in(mem_read_id),
        .mem_write_in(mem_write_id),
        .funct3_in(instruction_id[14:12]),
        .reg_write_in(reg_write_id),
        .mem_to_reg_in(mem_to_reg_id),
        .branch_in(branch_id),
        .jump_in(jump_id),
        .jalr_in(jalr_id),
        .pc_out(pc_ex),
        .pc_plus4_out(pc_plus4_ex),
        .read_data1_out(read_data1_ex),
        .read_data2_out(read_data2_ex),
        .imm_out(imm_ex),
        .instruction_out(instruction_ex),
        .rs1_out(rs1_ex),
        .rs2_out(rs2_ex),
        .rd_out(rd_ex),
        .alu_op_out(alu_op_ex),
        .alu_src_out(alu_src_ex),
        .mem_read_out(mem_read_ex),
        .mem_write_out(mem_write_ex),
        .funct3_out(funct3_ex),
        .reg_write_out(reg_write_ex),
        .mem_to_reg_out(mem_to_reg_ex),
        .branch_out(branch_ex),
        .jump_out(jump_ex),
        .jalr_out(jalr_ex)
    );

    forwarding_unit u_fwd (
        .id_ex_rs1(rs1_ex),
        .id_ex_rs2(rs2_ex),
        .ex_mem_rd(rd_mem),
        .ex_mem_reg_write(reg_write_mem),
        .mem_wb_rd(rd_wb),
        .mem_wb_reg_write(reg_write_wb),
        .forward_a(forward_a),
        .forward_b(forward_b)
    );

    wire [31:0] fwd_a_result =
        (forward_a == 2'b10) ? alu_result_mem  :
        (forward_a == 2'b01) ? write_back_data :
                               read_data1_ex;

    assign is_auipc    = (instruction_ex[6:0] == 7'b0010111);
    assign is_rtype_ex = (instruction_ex[6:0] == 7'b0110011);
    assign alu_input_a = is_auipc ? {pc_ex_zext_expr} : fwd_a_result;

    assign alu_input_b_pre =
        (forward_b == 2'b10) ? alu_result_mem  :
        (forward_b == 2'b01) ? write_back_data :
                               read_data2_ex;

    assign alu_input_b  = alu_src_ex ? imm_ex_sext : alu_input_b_pre;
    assign auipc_result = {pc_ex_zext_expr} + imm_ex_sext;

    alu_control u_alu_ctrl (
        .alu_op(alu_op_ex),
        .funct3(funct3_ex),
        .funct7(instruction_ex[30]),
        .is_rtype(is_rtype_ex),
        .alu_control(alu_control_ex)
    );

    alu u_alu (
        .a(alu_input_a),
        .b(alu_input_b),
        .alu_control(alu_control_ex),
        .result(alu_result_ex),
        .zero(zero_ex),
        .negative(negative_ex),
        .overflow(overflow_ex),
        .carry_out(carry_out_ex)
    );
'''

    if has_branch:
        text += '''
    branch_unit u_branch (
        .funct3(funct3_ex),
        .branch(branch_ex),
        .zero(zero_ex),
        .negative(negative_ex),
        .overflow(overflow_ex),
        .carry_out(carry_out_ex),
        .branch_taken(branch_taken_ex)
    );
'''
    else:
        text += '''
    // branch_unit omitted: no branch instruction (beq/bne/blt/bge/bltu/
    // bgeu) was used by this program. Its output is gated by the
    // `branch` control signal (see branch_unit_v.j2's `if (!branch)
    // branch_taken = 1'b0`), which control_unit.v never asserts when no
    // branch instruction exists at all -- so branch_taken would always
    // be 0 regardless. Tying it directly is equivalent and costs zero
    // hardware instead of an always-0 module.
    assign branch_taken_ex = 1'b0;
'''

    text += f'''
    // branch_target_ex: same full-precision-then-truncate pattern as
    // jalr_target above.
    wire [31:0] branch_target_ex_full;
    assign branch_target_ex_full = {pc_ex_zext_expr} + imm_ex_sext;
    assign branch_target_ex = branch_target_ex_full[{pc_msb}:0];
'''

    if has_custom:
        text += '''
    assign custom_en_ex = (instruction_ex[6:0] == 7'b0001011);
    assign ex_result    = custom_en_ex ? custom_result_ex : alu_result_ex;

    custom_unit u_custom (
        .clk(clk),
        .custom_en(custom_en_ex),
        .funct3(funct3_ex),
        .rs1_val(alu_input_a),
        .rs2_val(alu_input_b_pre),
        .custom_result(custom_result_ex),
        .custom_valid(custom_valid_ex),
        .custom_stall(custom_stall_ex)
    );
'''
    else:
        text += '''
    // custom_unit omitted: no custom_* instructions were used by this
    // program. Not instantiated anywhere, so Vivado's elaboration never
    // pulls custom_unit.v into the design -- it costs zero resources even
    // though the file can stay present in generated/ to satisfy
    // build.tcl's source list.
    assign ex_result = alu_result_ex;
'''

    text += f'''
    ex_mem_reg u_ex_mem (
        .clk(clk),
        .reset(reset),
        .flush(ex_mem_flush),
        .pc_plus4_in(pc_plus4_ex),
        .alu_result_in(ex_result),
        .write_data_in(alu_input_b_pre),
        .branch_target_in(branch_target_ex),
        .zero_in(zero_ex),
        .branch_taken_in(branch_taken_ex),
        .rd_in(rd_ex),
        .mem_read_in(mem_read_ex),
        .mem_write_in(mem_write_ex),
        .funct3_in(funct3_ex),
        .reg_write_in(reg_write_ex),
        .mem_to_reg_in(mem_to_reg_ex),
        .jump_in(jump_ex),
        .pc_plus4_out(pc_plus4_mem),
        .alu_result_out(alu_result_mem),
        .write_data_out(write_data_mem),
        .branch_target_out(branch_target_mem),
        .zero_out(zero_mem),
        .branch_taken_out(branch_taken_mem),
        .rd_out(rd_mem),
        .mem_read_out(mem_read_mem),
        .mem_write_out(mem_write_mem),
        .funct3_out(funct3_mem),
        .reg_write_out(reg_write_mem),
        .mem_to_reg_out(mem_to_reg_mem),
        .jump_out(jump_mem)
    );

    data_memory u_dmem (
        .clk(clk),
        .mem_read(mem_read_mem),
        .mem_write(mem_write_mem),
        .funct3(funct3_mem),
        .address(alu_result_mem),
        .write_data(write_data_mem),
        .read_data(mem_read_data_mem)
    );

    mem_wb_reg u_mem_wb (
        .clk(clk),
        .reset(reset),
        .pc_plus4_in(pc_plus4_mem),
        .alu_result_in(alu_result_mem),
        .mem_read_data_in(mem_read_data_mem),
        .rd_in(rd_mem),
        .reg_write_in(reg_write_mem),
        .mem_to_reg_in(mem_to_reg_mem),
        .pc_plus4_out(pc_plus4_wb),
        .alu_result_out(alu_result_wb),
        .mem_read_data_out(mem_read_data_wb),
        .rd_out(rd_wb),
        .reg_write_out(reg_write_wb),
        .mem_to_reg_out(mem_to_reg_wb)
    );

    assign write_back_data = {write_back_data_expr};
'''

    if has_hazard:
        text += '''
    hazard_unit u_hazard (
        .id_ex_mem_read(mem_read_ex),
        .id_ex_rd(rd_ex),
        .if_id_rs1(rs1_id),
        .if_id_rs2(rs2_id),
        .branch_taken(branch_taken_ex),
        .jump(jump_ex),
        .pc_write(pc_write),
        .if_id_write(if_id_write),
        .if_id_flush(if_id_flush),
        .id_ex_flush(id_ex_flush),
        .ex_mem_flush(ex_mem_flush)
    );
'''
    else:
        text += '''
    // hazard_unit omitted: this program uses neither a load instruction
    // (lb/lh/lw/lbu/lhu -- the only source of a load-use stall) nor a
    // branch or jump (beq/bne/blt/bge/bltu/bgeu/jal/jalr -- the only
    // source of a flush). hazard_unit.v's own logic defaults to
    // pc_write=1, if_id_write=1, and all flush signals=0 unless one of
    // those two conditions fires (see gen_pipeline_regs.py's
    // gen_hazard_unit) -- with neither ever possible here, its output
    // would always be exactly these defaults, so they're tied directly.
    assign pc_write     = 1'b1;
    assign if_id_write  = 1'b1;
    assign if_id_flush  = 1'b0;
    assign id_ex_flush  = 1'b0;
    assign ex_mem_flush = 1'b0;
'''

    text += f'''
    assign dbg_pc              = pc_out;
    assign dbg_instr_if        = instruction_if;
    assign dbg_instr_id        = instruction_id;
    assign dbg_alu_result_ex   = alu_result_ex[{alu_msb}:0];
    assign dbg_branch_taken_ex = branch_taken_ex;
    assign dbg_mem_write_mem   = mem_write_mem;
    assign dbg_mem_addr_mem    = alu_result_mem[{alu_msb}:0];
    assign dbg_mem_wdata_mem   = write_data_mem[{alu_msb}:0];
    assign dbg_reg_write_wb    = reg_write_wb;
    assign dbg_rd_wb           = rd_wb;
    assign dbg_wb_data         = write_back_data[{alu_msb}:0];

endmodule
'''
    return text


def _latch_decls_and_logic(alu_width: int, reg_index_width: int) -> tuple[str, str]:
    """Returns (declarations, always-block body) for latching the last
    REAL register writeback and memory write, so the final-result block
    can report them even after the pipeline has drained into trailing
    NOPs by the time `halted` asserts. See _final_results_block's
    docstring for why this is necessary.

    Also separately latches the last write to x10 (a0) specifically.
    Generic "last real write" is technically correct but practically
    useless for any compiled C function with a standard prologue/
    epilogue: the chronologically last register write is always the
    epilogue restoring sp, never the function's actual result. By RISC-V
    calling convention, a0/x10 holds the return value, and the LAST
    write to it before `ret` reliably IS that return value (any earlier
    use of a0 as scratch gets overwritten before a well-formed function
    returns). Verified against a real prologue/epilogue/return
    sequence: generic last-write reported sp being restored to 256;
    a0-specific tracking correctly reported 7."""
    decls = f'''    reg [{alu_width - 1}:0] last_wb_data;
    reg [{reg_index_width - 1}:0] last_wb_rd;
    reg last_wb_seen;
    reg [{alu_width - 1}:0] last_mem_addr;
    reg [{alu_width - 1}:0] last_mem_wdata;
    reg last_mem_seen;
    reg [{alu_width - 1}:0] last_a0_data;
    reg last_a0_seen;'''
    logic = '''    initial begin
        last_wb_seen = 1'b0;
        last_mem_seen = 1'b0;
        last_a0_seen = 1'b0;
    end
    always @(posedge clk) begin
        if (dbg_reg_write_wb && (dbg_rd_wb != 0)) begin
            last_wb_data <= dbg_wb_data;
            last_wb_rd   <= dbg_rd_wb;
            last_wb_seen <= 1'b1;
        end
        if (dbg_reg_write_wb && (dbg_rd_wb == 10)) begin
            last_a0_data <= dbg_wb_data;
            last_a0_seen <= 1'b1;
        end
        if (dbg_mem_write_mem) begin
            last_mem_addr  <= dbg_mem_addr_mem;
            last_mem_wdata <= dbg_mem_wdata_mem;
            last_mem_seen  <= 1'b1;
        end
    end'''
    return decls, logic


def _final_results_block(stored_registers) -> str:
    """Builds a loud, unmissable final-summary block, printed right before
    $finish, using ONLY pipeline_top's own top-level ports (dbg_pc, etc.)
    -- not hierarchical references into submodule internals, which do
    not survive build.tcl's post-synthesis functional simulation (see
    the long comment this replaced, in git history / prior turns, for
    the full "'r1' is not declared under prefix" story).

    IMPORTANT: this reads LATCHED registers (last_wb_*, last_mem_*,
    last_a0_*), not the live dbg_wb_data/dbg_mem_*_mem wires directly.
    Those wires show whatever's CURRENTLY in the write-back/memory
    stage -- but `halted` only fires several cycles after the drain
    counter waits out the pipeline, by which point the real
    computation's result has already passed through and what's left on
    the wires is just the trailing NOP flush (rd=x0, reg_write=0,
    everything zero). The testbench body latches these on every cycle
    where a real write actually happens, so this block reports the last
    MEANINGFUL writeback, not whatever happened to be on the wire at the
    instant of halt. Verified: without this, adding 3+4 reported
    "rd=x0 data=0x0" instead of the real result.

    last_a0_* is tracked SEPARATELY from the generic last_wb_* because
    the generic version, while technically correct, is reliably
    misleading for any compiled C function with a standard prologue/
    epilogue: the chronologically last register write is always the
    epilogue restoring sp (or fp), never the function's actual result.
    Verified against a real prologue/epilogue/return sequence: generic
    last-write reported sp being restored to its original value; a0
    tracking correctly reported the real computed result instead.
    """
    stored_registers = stored_registers or []
    return f'''
        $display("");
        $display("############################################################");
        $display("###                  FINAL RESULT                       ###");
        $display("############################################################");
        $display("halted=%b at cycle=%0d", halted, cyclecount);
        if (last_a0_seen)
            $display("Return value (a0/x10) : 0x%0h (%0d)  <- last write to x10, per RISC-V calling convention",
                     last_a0_data, $signed(last_a0_data));
        else
            $display("Return value (a0/x10) : (x10 was never written this run -- this program may not follow the standard calling convention, or doesn't use a0 for its result)");
        if (last_wb_seen)
            $display("Last REAL writeback   : rd=x%0d data=0x%0h (%0d)  (often just epilogue sp/fp restoration -- NOT necessarily the answer, see a0 above)",
                     last_wb_rd, last_wb_data, $signed(last_wb_data));
        else
            $display("Last REAL writeback   : (no register was ever written this run)");
        if (last_mem_seen)
            $display("Last REAL mem write   : addr=0x%0h wdata=0x%0h (%0d)",
                     last_mem_addr, last_mem_wdata, $signed(last_mem_wdata));
        else
            $display("Last REAL mem write   : (no memory write occurred this run)");
        $display("Final PC              : 0x%0h", dbg_pc);
        $display("");
        $display("NOTE: this build only exposes the last REAL writeback/memory");
        $display("write, not a full register/memory dump -- hierarchical internal");
        $display("signal access (e.g. u_reg_file.r1) doesn't survive synthesis.");
        $display("This testbench instantiates pipeline_top directly for full debug");
        $display("visibility -- RTL/behavioral simulation ONLY, not valid for");
        $display("post-synthesis sim (use tb_pipeline_top.v for that instead).");
        $display("This build stores these registers: {stored_registers}");
        $display("############################################################");
        $display("");
'''


def make_program_tb(program_name: str, alu_width: int, reg_index_width: int, stored_registers=None) -> str:
    mod = sanitize(program_name)
    result_banner = _final_results_block(stored_registers or [])
    latch_decls, latch_logic = _latch_decls_and_logic(alu_width, reg_index_width)
    return f'''// ============================================================
// Module      : tb_pipeline_top_{mod}
// Description : Program-specific RICH-DEBUG testbench for {program_name}
//               Instantiates pipeline_top DIRECTLY (full dbg_* trace:
//               PC, instruction, ALU result, memory access, every
//               cycle). RTL/BEHAVIORAL SIMULATION ONLY -- do not use
//               this for post-synthesis simulation. synth_1's actual
//               top is pipeline_top_hw (see build.tcl), which leaves
//               most of pipeline_top's dbg_* ports unconnected; trying
//               to instantiate pipeline_top directly against that
//               synthesized netlist risks the same
//               "port not declared" failures hierarchical signal
//               access hit earlier in this project. For a testbench
//               that's valid in both RTL and post-synthesis contexts,
//               use tb_pipeline_top.v (make_stable_tb) instead, which
//               instantiates pipeline_top_hw to match what's actually
//               synthesized.
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top_{mod};
    reg clk;
    reg reset;
    integer cyclecount;

    wire        halted;
    wire [31:0] dbg_pc;
    wire [31:0] dbg_instr_if;
    wire [31:0] dbg_instr_id;
    wire [{alu_width - 1}:0] dbg_alu_result_ex;
    wire dbg_branch_taken_ex;
    wire dbg_mem_write_mem;
    wire [{alu_width - 1}:0] dbg_mem_addr_mem;
    wire [{alu_width - 1}:0] dbg_mem_wdata_mem;
    wire dbg_reg_write_wb;
    wire [{reg_index_width - 1}:0] dbg_rd_wb;
    wire [{alu_width - 1}:0] dbg_wb_data;

{latch_decls}

    pipeline_top u_dut (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .dbg_pc(dbg_pc),
        .dbg_instr_if(dbg_instr_if),
        .dbg_instr_id(dbg_instr_id),
        .dbg_alu_result_ex(dbg_alu_result_ex),
        .dbg_branch_taken_ex(dbg_branch_taken_ex),
        .dbg_mem_write_mem(dbg_mem_write_mem),
        .dbg_mem_addr_mem(dbg_mem_addr_mem),
        .dbg_mem_wdata_mem(dbg_mem_wdata_mem),
        .dbg_reg_write_wb(dbg_reg_write_wb),
        .dbg_rd_wb(dbg_rd_wb),
        .dbg_wb_data(dbg_wb_data)
    );

{latch_logic}

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_pipeline_top_{mod}.vcd");
        $dumpvars(0, tb_pipeline_top_{mod});
    end

    localparam MAX_CYCLES = 200000;  // generous margin for real loops (e.g. 128 iterations easily needs several thousand cycles)

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("============================================================");
        $display(" Program-specific pipeline_top simulation start");
        $display(" Program: {program_name}");
        $display("============================================================");

        repeat (5) @(posedge clk);
        reset = 1'b0;
        $display("%0t Reset deasserted", $time);

        while (!halted && cyclecount < MAX_CYCLES) begin
            @(posedge clk);
            cyclecount = cyclecount + 1;
            $display("Cycle %0d | PC=0x%0h | InstrIF=0x%08h | WB reg_write=%b rd=x%0d data=0x%0h (%0d) | MEM write=%b addr=0x%0h wdata=0x%0h",
                     cyclecount, dbg_pc, dbg_instr_if, dbg_reg_write_wb, dbg_rd_wb, dbg_wb_data, dbg_wb_data,
                     dbg_mem_write_mem, dbg_mem_addr_mem, dbg_mem_wdata_mem);
        end

{result_banner}
        $finish;
    end

    initial begin
        #2000000;  // matches MAX_CYCLES=200000 at 10ns/cycle
        $display("FAIL absolute timeout in tb_pipeline_top_{mod}.v");
        $finish;
    end
endmodule
'''


def make_stable_tb(alu_width: int, reg_index_width: int, stored_registers=None, max_result_bits: int = 14) -> str:
    alu_msb = alu_width - 1
    # MUST match make_pipeline_top_hw's own result_width calculation
    # exactly -- this testbench instantiates that module's actual
    # result_data port, which is capped at max_result_bits, not the
    # full alu_width. Confirmed via a real Vivado post-synthesis run:
    # declaring this wire at the uncapped alu_msb width (e.g. 32 bits
    # when the real port is only 14) produces "VRFC 10-3091 actual bit
    # length 32 differs from formal bit length 14 for port
    # 'result_data'" and Z-pads the extra, genuinely nonexistent bits
    # in any display of this signal -- not a computation error, just a
    # testbench-side width mismatch against the real synthesized port.
    result_width = min(alu_width, max_result_bits)
    result_msb = result_width - 1
    return f'''// ============================================================
// Module      : tb_pipeline_top
// Description : Testbench for pipeline_top_hw -- the SAME module used
//               as the synthesis/implementation top (see build.tcl).
//               This is deliberate: post-synthesis simulation runs
//               against whatever synth_1 actually built, so this
//               testbench must instantiate the identical hierarchy, or
//               the simulation isn't actually testing what got
//               synthesized. For full per-cycle debug visibility
//               (PC/instruction/ALU/memory trace) in RTL/behavioral-only
//               simulation, use tb_pipeline_top_<program>.v instead,
//               which instantiates pipeline_top directly -- that
//               testbench is NOT valid for post-synthesis simulation.
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top;
    reg clk;
    reg reset;
    integer cyclecount;

    wire halted;
    wire result_valid;
    wire [{result_msb}:0] result_data;

    pipeline_top_hw u_dut (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .result_valid(result_valid),
        .result_data(result_data)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_pipeline_top.vcd");
        $dumpvars(0, tb_pipeline_top);
    end

    // No fixed cycle count: this testbench decides for itself, via
    // `halted`, exactly when the program is done. Note this is about
    // DYNAMIC execution length, not the STATIC instruction count -- an
    // 18-instruction program with no loops stops in ~18 + a handful of
    // drain cycles, but an 18-instruction program containing a
    // 128-iteration loop can easily need several thousand cycles, since
    // the same small set of instructions gets fetched over and over.
    // MAX_CYCLES below is a generous upper bound covering that, not a
    // per-instruction-count estimate. Pair with `run -all` in the
    // Vivado sim Tcl (not `run <fixed time>`), so XSim actually stops
    // here instead of waiting out a fixed wall-clock duration
    // regardless of $finish.
    localparam MAX_CYCLES = 200000;  // generous margin for real loops (e.g. 128 iterations easily needs several thousand cycles)

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("============================================================");
        $display(" pipeline_top_hw simulation start (matches synthesis top)");
        $display("============================================================");

        repeat (5) @(posedge clk);
        reset = 1'b0;

        while (!halted && cyclecount < MAX_CYCLES) begin
            @(posedge clk);
            cyclecount = cyclecount + 1;
        end

        $display("");
        $display("############################################################");
        $display("###                  FINAL RESULT                       ###");
        $display("############################################################");
        $display("halted=%b at cycle=%0d", halted, cyclecount);
        if (result_valid)
            $display("Return value (a0/x10) : 0x%0h (%0d)  <- latched in real hardware logic, per RISC-V calling convention",
                     result_data, $signed(result_data));
        else
            $display("Return value (a0/x10) : (x10 was never written this run -- this program may not follow the standard calling convention)");
        $display("############################################################");
        $display("");

        if (halted)
            $display("PASS: halted cleanly after %0d cycles", cyclecount);
        else
            $display("FAIL: halted never asserted within %0d cycles", MAX_CYCLES);
        $finish;
    end

    initial begin
        #2000000;  // matches MAX_CYCLES=200000 at 10ns/cycle
        $display("FAIL simulation timeout");
        $finish;
    end
endmodule
'''


def make_pipeline_top_hw(alu_width: int, reg_index_width: int, max_result_bits: int = 14) -> str:
    """
    Thin(ner) wrapper around pipeline_top for real implementation builds.
    Exposes clk/reset/halted plus a NARROW, MEANINGFUL result output
    (result_valid/result_data), NOT the full ~dozens-of-bits dbg_* pile
    -- but also deliberately NOT just clk/reset/halted alone.

    WHY NOT JUST clk/reset/halted (an earlier version of this function
    did exactly that, and was wrong): halted only depends on
    CONTROL-FLOW logic -- whatever determines PC's trajectory (branch/
    jump decisions, load-use stalls). It does NOT depend on the actual
    VALUES the ALU computes, what's sitting in the register file, or
    what's in data memory, for any instruction that isn't itself a
    branch condition. If halted were the only observable output,
    synthesis's dead-logic elimination would correctly conclude that
    all of that real computation has zero effect on anything observable,
    and strip it out entirely -- giving a utilization report that
    reflects almost nothing, and a bitstream that can prove a program
    finished but can never report what it actually computed.

    result_data is the latched value of the last write to x10 (a0), the
    RISC-V calling-convention return-value register -- same design as
    the testbench's a0-tracking (see _final_results_block), but
    implemented here as real synthesizable logic, not a testbench
    construct, so it's a permanent part of the actual hardware. Because
    result_data's value genuinely depends on the ALU, register file,
    forwarding, and (if loads are used) data memory, synthesis has a
    real reason to keep all of that -- the utilization report reflects
    the real design, and a real user reading these pins after `halted`
    asserts gets the actual answer, not just "done: yes/no".

    result_valid mirrors the testbench's last_a0_seen: stays 0 if this
    program never writes x10 at all (e.g. a bare-metal program not
    following the standard calling convention), so it's honest about
    when result_data isn't meaningful rather than reporting a bogus 0.

    max_result_bits CAPS result_data's actual port width, taking only
    the LOW max_result_bits bits of the full computed value, instead of
    always exposing the full alu_width. This matters because alu_width
    isn't bounded by what a real board can physically expose as pins --
    e.g. any program using slli+srai to sign-extend a byte (the
    standard way RV32I handles `char`/`unsigned char`, since it has no
    dedicated sign-extension instruction) genuinely needs the full
    32-bit range for that INTERMEDIATE value, so alu_width stays 32
    regardless of how small the program's actual values are. Exposing
    all 32 bits as raw LEDs is infeasible on something like a Basys3
    (16 LEDs total, 14 left after halted/result_valid) -- confirmed via
    a real placement failure: "IO placement is infeasible. Number of
    unplaced IO Ports (18) is greater than number of available pins
    (12)" when alu_width=32 was exposed directly. An earlier version of
    this function only WARNED about this and left the excess bits
    unconstrained, which doesn't actually work: an unconstrained
    top-level port still has to be placed SOMEWHERE, so Vivado's
    placer fails outright rather than silently dropping it. Capping
    the port width itself, in the RTL, is the only fix that actually
    prevents the problem instead of just describing it. Default of 14
    matches Basys3 specifically; pass a different value for other
    boards / a different number of reserved status LEDs.

    Pin count: 3 (clk/reset/halted) + 1 (result_valid) + min(alu_width,
    max_result_bits) (result_data) -- always fits within max_result_bits
    + 4 total pins, regardless of what alu_width the profiled program
    needed internally.

    IMPORTANT: this module (not pipeline_top directly) must be BOTH the
    synthesis/implementation top AND what tb_pipeline_top.v instantiates
    for post-synthesis simulation to work at all -- post-synthesis
    simulation runs against whatever synth_1 actually built, and if the
    testbench tries to instantiate pipeline_top directly with all its
    dbg_* ports while synth_1 was rooted at pipeline_top_hw (where those
    ports are never connected to anything), there's a real risk they get
    optimized out of the synthesized pipeline_top entirely, breaking the
    testbench's connections the same way hierarchical signal references
    did earlier. See make_stable_tb, which instantiates THIS module.
    """
    alu_msb = alu_width - 1
    result_width = min(alu_width, max_result_bits)
    result_msb = result_width - 1
    return f'''// ============================================================
// Module      : pipeline_top_hw
// File        : pipeline_top_hw.v
// Description : Hardware-implementation wrapper around pipeline_top.
//               Exposes clk/reset/halted plus a narrow, MEANINGFUL
//               result output (result_valid/result_data = the low
//               {result_width} bits of the last write to x10/a0,
//               latched in real synthesizable logic) -- not the full
//               dbg_* debug interface, but also not NOTHING beyond
//               halted, and capped to a width any real board's LEDs
//               can actually hold. See this file's generator
//               (gen_pipeline_and_tb.py's make_pipeline_top_hw) for the
//               full reasoning, including why alu_width itself (here:
//               {alu_width} bits) can't just be exposed directly.
//
// Use THIS as the synthesis/implementation top AND as what
// tb_pipeline_top.v instantiates -- both need to agree on the same
// hierarchy for post-synthesis simulation to be valid at all.
// ============================================================

`timescale 1ns / 1ps

module pipeline_top_hw (
    input  clk,
    input  reset,
    output halted,
    output result_valid,
    output [{result_msb}:0] result_data
);

    wire dbg_reg_write_wb;
    wire [{reg_index_width - 1}:0] dbg_rd_wb;
    wire [{alu_msb}:0] dbg_wb_data;

    pipeline_top u_core (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .dbg_reg_write_wb(dbg_reg_write_wb),
        .dbg_rd_wb(dbg_rd_wb),
        .dbg_wb_data(dbg_wb_data)
        // Remaining dbg_* ports (dbg_pc, dbg_instr_if, dbg_instr_id,
        // dbg_alu_result_ex, dbg_branch_taken_ex, dbg_mem_write_mem,
        // dbg_mem_addr_mem, dbg_mem_wdata_mem) intentionally left
        // unconnected -- these are per-cycle trace signals with no
        // meaningful "final" value to latch and report as a real
        // hardware output. Full per-cycle visibility is still available
        // in RTL/behavioral-only simulation via tb_pipeline_top_<program>.v,
        // which instantiates pipeline_top directly (documented there as
        // not valid for post-synthesis use).
    );

    // Real synthesizable latch, not a testbench construct: holds the
    // low {result_width} bits of the last value written to x10/a0 for
    // as long as the design is powered, so a real user reading these
    // pins after `halted` asserts sees the actual computed result, not
    // a live wire that's already gone stale from epilogue/drain-cycle
    // activity by the time they look. Only the low {result_width} bits
    // of dbg_wb_data are captured -- see this function's docstring for
    // why the full {alu_width}-bit value can't be exposed as pins
    // directly.
    reg result_valid_r;
    reg [{result_msb}:0] result_data_r;

    initial begin
        result_valid_r = 1'b0;
    end

    always @(posedge clk) begin
        if (reset) begin
            result_valid_r <= 1'b0;
        end else if (dbg_reg_write_wb && (dbg_rd_wb == 10)) begin
            result_data_r  <= dbg_wb_data[{result_msb}:0];
            result_valid_r <= 1'b1;
        end
    end

    assign result_valid = result_valid_r;
    assign result_data  = result_data_r;

endmodule
'''


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) != 3:
        print('Usage: python3 tools/gen_pipeline_and_tb.py <insts.json> <outdir>')
        return 1

    inst_json = Path(argv[1])
    outdir = Path(argv[2])

    summary = load_json(inst_json)
    program_name = infer_program_name(summary, inst_json)
    trim = load_trim_profile(inst_json, summary)

    alu_width = trim['alu_width']
    imm_width = trim['imm_width']
    reg_index_width = trim['reg_index_width']

    instructions_used = summary.get('instructions_used', [])
    has_custom = any(str(i).startswith('custom_') for i in instructions_used)

    BRANCH_SET = {"beq", "bne", "blt", "bge", "bltu", "bgeu"}
    LOAD_SET = {"lb", "lh", "lw", "lbu", "lhu"}
    JUMP_SET = {"jal", "jalr"}
    instructions_used_set = set(instructions_used)
    has_branch = bool(instructions_used_set & BRANCH_SET)
    # hazard_unit is needed if EITHER a load-use stall is possible (any
    # load instruction used) OR a flush is possible (any branch or jump
    # used) -- see gen_hazard_unit's two independent conditions.
    has_hazard = bool(instructions_used_set & (LOAD_SET | BRANCH_SET | JUMP_SET))

    # Same source register_file_v.j2 itself uses for its own
    # stored_registers -- guarantees the testbench only ever references
    # u_dut.u_reg_file.rN for N that actually exist as physical signals.
    stored_registers = sorted(set(summary.get('registers_written', [])))

    # pc_width comes from pc_width.txt (written by gen_pc.py into the
    # same output directory) -- MUST match pc.v/pc_adder.v/
    # instruction_memory.v exactly, or the primary addressing path
    # reintroduces a proven wraparound bug. Falls back to a conservative
    # default if gen_pc.py hasn't been run yet.
    pc_width_path = outdir / 'pc_width.txt'
    pc_width = max(1, int(pc_width_path.read_text(encoding='utf-8').strip())) if pc_width_path.exists() else 12

    # If gen_dense_control.py has already run (dense encoding mode),
    # encoding_plan.json will be sitting in the same output directory --
    # load it so alu_op/alu_control/mem_to_reg wires and the write-back
    # mux match control_unit.v/alu_control.v/alu.v exactly. If it's not
    # there, make_pipeline_top falls back to the original fixed widths.
    plan_path = outdir / 'encoding_plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8')) if plan_path.exists() else None

    write_text(outdir / 'pipeline_top.v', make_pipeline_top(alu_width, imm_width, reg_index_width, pc_width, has_custom=has_custom, has_branch=has_branch, has_hazard=has_hazard, plan=plan))
    write_text(outdir / 'pipeline_top_hw.v', make_pipeline_top_hw(alu_width, reg_index_width))
    write_text(outdir / 'alu_width.txt', str(alu_width))
    write_text(outdir / 'result_data_width.txt', str(min(alu_width, 14)))
    write_text(outdir / f'tb_pipeline_top_{sanitize(program_name)}.v',
               make_program_tb(program_name, alu_width, reg_index_width, stored_registers=stored_registers))
    write_text(outdir / 'tb_pipeline_top.v',
               make_stable_tb(alu_width, reg_index_width, stored_registers=stored_registers))

    print(f'Generated {outdir / "pipeline_top.v"} (has_custom={has_custom}, has_branch={has_branch}, has_hazard={has_hazard}, dense_encoding={plan is not None})')
    print(f'Generated {outdir / "pipeline_top_hw.v"} (minimal clk/reset/halted wrapper -- use as the synthesis/implementation top)')
    print(f'Generated {outdir / f"tb_pipeline_top_{sanitize(program_name)}.v"}')
    print(f'Generated {outdir / "tb_pipeline_top.v"}')
    print(f'Trim widths: alu={alu_width}, imm={imm_width}, reg_index={reg_index_width}, pc={pc_width} (primary addressing path AND pipeline-carried copies both narrowed consistently)')
    print(f'Final-result register dump will include: {stored_registers}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())