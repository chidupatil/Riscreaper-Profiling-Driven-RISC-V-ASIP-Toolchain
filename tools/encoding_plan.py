#!/usr/bin/env python3
"""
encoding_plan.py -- computes DENSE (minimal-width, profile-driven)
encodings for alu_op, alu_control, and mem_to_reg, instead of the
original fixed-width encodings that always reserve room for every
possible RV32I value regardless of what a given program actually uses.

THIS IS A SHARED MODULE, NOT A STANDALONE SCRIPT. It is imported by:
  - gen_dense_control.py  (generates control_unit.v / alu_control.v / alu.v)
  - gen_pipeline_regs.py  (sizes the mem_to_reg / alu_op fields in
                            id_ex_reg.v / ex_mem_reg.v / mem_wb_reg.v)
  - gen_pipeline_and_tb.py (sizes the corresponding wires in pipeline_top.v
                            and the final write-back mux)

Every one of those must agree on the EXACT same codes for EXACT the same
program, or the result is a silent, catastrophic control-logic mismatch
(e.g. control_unit.v asserting alu_op=1 meaning "branch" while
alu_control.v was generated believing alu_op=1 means "lui"). Computing
the plan in exactly one place, deterministically (sorted inputs, fixed
tie-breaking), and having every consumer import it rather than
re-derive it, is the only way to make that impossible instead of just
unlikely.
"""
from __future__ import annotations

import math

R_TYPE_SET = {"add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu"}
I_ALU_SET = {"addi", "andi", "ori", "xori", "slti", "sltiu", "slli", "srli", "srai"}
LOAD_SET = {"lb", "lh", "lw", "lbu", "lhu"}
STORE_SET = {"sb", "sh", "sw"}
BRANCH_SET = {"beq", "bne", "blt", "bge", "bltu", "bgeu"}
JAL_SET = {"jal"}
JALR_SET = {"jalr"}
LUI_SET = {"lui"}
AUIPC_SET = {"auipc"}

# Instruction -> which ALU operation it needs (R-type / I-type-ALU family,
# both of which use alu_op="ialu" and decode further by funct3/funct7).
ALU_OP_FOR_INST = {
    "add": "ADD", "addi": "ADD",
    "sub": "SUB",
    "and": "AND", "andi": "AND",
    "or": "OR", "ori": "OR",
    "xor": "XOR", "xori": "XOR",
    "sll": "SLL", "slli": "SLL",
    "srl": "SRL", "srli": "SRL",
    "sra": "SRA", "srai": "SRA",
    "slt": "SLT", "slti": "SLT",
    "sltu": "SLTU", "sltiu": "SLTU",
}

# The 4-bit codes the ORIGINAL (non-dense) alu.v/alu_control.v use for
# each operation. Kept here so gen_dense_control.py's alu.v case
# statement bodies (the actual AND/ADD/etc. logic per op) can be reused
# verbatim -- only the CASE LABELS (the codes) get densified, not the
# computation each op performs.
ORIGINAL_ALU_OPCODE = {
    "AND": 0b0000, "OR": 0b0001, "ADD": 0b0010, "XOR": 0b0011,
    "SLL": 0b0100, "SRL": 0b0101, "SUB": 0b0110, "SRA": 0b0111,
    "SLT": 0b1000, "SLTU": 0b1001, "LUIPASS": 0b1010,
}


def dense_code_map(names) -> tuple[dict, int]:
    """Deterministic name->code assignment (sorted order) plus the
    minimum bit width to represent it. Floors at 1 bit even for a
    single value, to avoid a 0-width-signal special case throughout
    every consumer -- a small, deliberate safety-over-aggressiveness
    trade-off."""
    names = sorted(set(names))
    n = len(names)
    width = max(1, (max(0, n - 1)).bit_length())
    return {name: i for i, name in enumerate(names)}, width


def compute_plan(instructions_used) -> dict:
    instructions_used = set(instructions_used)

    # ---------------- alu_op (which decode family applies) ----------------
    alu_op_families = []
    if instructions_used & (R_TYPE_SET | I_ALU_SET):
        alu_op_families.append("ialu")
    if instructions_used & BRANCH_SET:
        alu_op_families.append("branch")
    if instructions_used & LUI_SET:
        alu_op_families.append("lui")
    # "addfam" covers load/store/jalr/auipc/jal -- all use ADD via the
    # original alu_op=00, including jal even though its ALU result is
    # architecturally unused (write-back comes from pc_plus4 instead);
    # jal still asserts alu_op=00 as the unconditional default in
    # control_unit.v, so it must be accounted for here regardless.
    if instructions_used & (LOAD_SET | STORE_SET | JALR_SET | AUIPC_SET | JAL_SET):
        alu_op_families.append("addfam")
    if not alu_op_families:
        alu_op_families = ["addfam"]  # control_unit always needs a sane default

    alu_op_codes, alu_op_width = dense_code_map(alu_op_families)

    # ---------------- alu_control (actual ALU operation) ----------------
    alu_ops_needed = set()
    for inst in instructions_used:
        if inst in ALU_OP_FOR_INST:
            alu_ops_needed.add(ALU_OP_FOR_INST[inst])
    if instructions_used & BRANCH_SET:
        alu_ops_needed.add("SUB")  # every branch type uses SUB (see alu_control_v.j2 fix)
    if instructions_used & (LOAD_SET | STORE_SET | JALR_SET | AUIPC_SET | JAL_SET):
        alu_ops_needed.add("ADD")
    if instructions_used & LUI_SET:
        alu_ops_needed.add("LUIPASS")
    if not alu_ops_needed:
        alu_ops_needed = {"ADD"}

    alu_control_codes, alu_control_width = dense_code_map(alu_ops_needed)

    # ---------------- mem_to_reg (write-back source select) ----------------
    wb_sources = ["alu"]  # always needed as the fallback/default
    if instructions_used & LOAD_SET:
        wb_sources.append("mem")
    if instructions_used & (JAL_SET | JALR_SET):
        wb_sources.append("pcplus4")

    mem_to_reg_codes, mem_to_reg_width = dense_code_map(wb_sources)

    return {
        "instructions_used": sorted(instructions_used),
        "alu_op_codes": alu_op_codes,
        "alu_op_width": alu_op_width,
        "alu_control_codes": alu_control_codes,
        "alu_control_width": alu_control_width,
        "mem_to_reg_codes": mem_to_reg_codes,
        "mem_to_reg_width": mem_to_reg_width,
    }