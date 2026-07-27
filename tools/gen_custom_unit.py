#!/usr/bin/env python3
"""
gen_custom_unit.py <insts.json> <outdir>

Generates a TRIMMED custom_unit.v, replacing the static, never-trimmed
version. The original always computed BOTH a signed multiply
(mul_result, needed by custom_mul/custom_mulh/custom_mac) AND a
separate, independent unsigned multiply (mulhu_result, needed only by
custom_mulhu) unconditionally every cycle, regardless of which
operation the program actually uses -- Vivado can't optimize this away
on its own, since funct3 is a real runtime signal from synthesis's
perspective, not something it can prove is always one specific value.

Confirmed via a real utilization report: a program using ONLY
custom_mul (never mulh/mulhu/mac) was still consuming ~7 DSP slices --
consistent with two independent ~32x32 multipliers being synthesized,
when only one was ever actually needed.

This generator only includes:
  - mul_result (the signed multiply) if custom_mul, custom_mulh, or
    custom_mac is actually used (all three share it)
  - mulhu_result (the separate unsigned multiply) only if custom_mulhu
    is actually used
  - case arms only for the instructions actually used, matching the
    same trimming pattern as control_unit.v/alu_control.v/branch_unit.v
    elsewhere in this toolchain

If NEITHER mul_result nor mulhu_result end up needed (i.e. no custom_*
instruction is used at all), this script still runs but the resulting
file is moot -- pipeline_top.v's has_custom logic already skips
instantiating custom_unit entirely in that case, so the file's content
doesn't matter.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def gen_custom_unit(instructions_used: set, operand_width: int = 32, result_width: int = 32) -> str:
    needs_signed = bool(instructions_used & {"custom_mul", "custom_mulh", "custom_mac"})
    needs_unsigned = "custom_mulhu" in instructions_used
    w_msb = operand_width - 1
    rw_msb = result_width - 1
    ext_bits = 32 - result_width

    lines = []
    lines.append("// ============================================================")
    lines.append("// Module      : Custom Instruction Unit (TRIMMED)")
    lines.append("// File        : custom_unit.v")
    lines.append("// Description : Implements custom-0 opcode (0x0B) operations --")
    lines.append("//               but ONLY the specific ones this program actually")
    lines.append("//               uses. An earlier, static version of this file")
    lines.append("//               always computed BOTH a signed AND a separate")
    lines.append("//               unsigned ~32x32 multiply unconditionally, every")
    lines.append("//               cycle, regardless of which operation was ever")
    lines.append("//               actually selected -- confirmed via a real")
    lines.append("//               utilization report to cost ~7 DSP slices for a")
    lines.append("//               program using only custom_mul (which needs just")
    lines.append("//               ONE of the two). This version only includes the")
    lines.append("//               multiplier(s) actually needed.")
    lines.append("//")
    lines.append(f"//               The multiplier is ALSO narrowed internally to")
    lines.append(f"//               {operand_width} bits, based on the actual operand")
    lines.append(f"//               values this program passes to custom_* instructions")
    lines.append(f"//               (profiled precisely, not the full 32-bit register")
    lines.append(f"//               width every operand COULD theoretically hold) --")
    lines.append(f"//               confirmed via a real profile: a program calling")
    lines.append(f"//               custom_mul(6,7) only ever needs 4 bits per operand,")
    lines.append(f"//               not 32. rs1_val/rs2_val stay 32-bit PORTS (matching")
    lines.append(f"//               pipeline_top.v's existing connections, no interface")
    lines.append(f"//               changes needed there), but only the low")
    lines.append(f"//               {operand_width} bits of each actually feed the")
    lines.append(f"//               multiplier -- a multiply this narrow needs no DSP")
    lines.append(f"//               slice at all, synthesizing entirely in LUTs.")
    lines.append("//")
    lines.append(f"//               The RESULT is narrowed the same way: this program's")
    lines.append(f"//               computed value never needs more than {result_width} bits,")
    lines.append(f"//               profiled from the actual result value at custom_*")
    lines.append(f"//               call sites (not just inherited from custom_result's")
    lines.append(f"//               fixed 32-bit port). Confirmed via a real Vivado")
    lines.append(f"//               timing report: sign-extending a narrow product up to")
    lines.append(f"//               a 32-bit port by simply slicing straight from the")
    lines.append(f"//               multiplier's own carry-chain output let synthesis")
    lines.append(f"//               implement that extension BY EXTENDING THE SAME CARRY")
    lines.append(f"//               CHAIN (4 chained CARRY4 blocks, 12 logic levels to the")
    lines.append(f"//               top bit) rather than something cheaper -- the fix is")
    lines.append(f"//               computing the real, narrow result first, then")
    lines.append(f"//               EXPLICITLY sign-extending it via bit replication,")
    lines.append(f"//               which synthesis maps to simple buffer fanout instead.")
    lines.append("//")
    lines.append("// funct3 operations included in THIS build:")
    if "custom_mul" in instructions_used:
        lines.append("//   000 -> MUL    result = rs1 * rs2 (lower 32 bits, signed)")
    if "custom_mulh" in instructions_used:
        lines.append("//   001 -> MULH   result = (rs1 * rs2)[63:32] signed")
    if "custom_mulhu" in instructions_used:
        lines.append("//   010 -> MULHU  result = (rs1 * rs2)[63:32] unsigned")
    if "custom_mac" in instructions_used:
        lines.append("//   011 -> MAC    result = rs1 * rs2 (placeholder, signed)")
    lines.append("// ============================================================")
    lines.append("")
    lines.append("`timescale 1ns / 1ps")
    lines.append("")
    lines.append("module custom_unit (")
    lines.append("    input             clk,")
    lines.append("    input             custom_en,      // 1 when custom opcode")
    lines.append("    input      [2:0]  funct3,         // Operation selector")
    lines.append("    input      [31:0] rs1_val,        // First source operand")
    lines.append("    input      [31:0] rs2_val,        // Second source operand")
    lines.append("    output reg [31:0] custom_result,  // Result for write-back")
    lines.append("    output            custom_valid,   // 1 when result ready")
    lines.append("    output            custom_stall    // 1 when needs more cycles")
    lines.append(");")
    lines.append("")
    lines.append("    // Single cycle implementation -- always ready immediately")
    lines.append("    assign custom_valid = custom_en;")
    lines.append("    assign custom_stall = 1'b0;  // No stall for single-cycle")
    lines.append("")

    if needs_signed:
        lines.append(f"    wire [63:0] mul_result = $signed(rs1_val[{w_msb}:0]) * $signed(rs2_val[{w_msb}:0]);")
    if needs_unsigned:
        lines.append(f"    wire [63:0] mulhu_result = rs1_val[{w_msb}:0] * rs2_val[{w_msb}:0];")
    lines.append("")

    if result_width < 32:
        lines.append(f"    // Narrow result register -- only {result_width} bits are ever")
        lines.append(f"    // actually significant (profiled), computed separately from the")
        lines.append(f"    // sign-extension below so synthesis sees them as distinct steps.")
        lines.append(f"    reg [{rw_msb}:0] custom_result_narrow;")
        lines.append("")

    result_reg = "custom_result_narrow" if result_width < 32 else "custom_result"
    result_slice = f"[{rw_msb}:0]"

    lines.append("    always @(*) begin")
    lines.append(f"        {result_reg} = {result_width}'h0;")
    lines.append("")
    lines.append("        if (custom_en) begin")
    lines.append("            case (funct3)")
    if "custom_mul" in instructions_used:
        lines.append(f"                3'b000: {result_reg} = mul_result{result_slice};   // MUL")
    if "custom_mulh" in instructions_used:
        lines.append(f"                3'b001: {result_reg} = mul_result[{rw_msb+32}:32];  // MULH signed")
    if "custom_mulhu" in instructions_used:
        lines.append(f"                3'b010: {result_reg} = mulhu_result[{rw_msb+32}:32];// MULHU unsigned")
    if "custom_mac" in instructions_used:
        lines.append(f"                3'b011: {result_reg} = mul_result{result_slice};   // MAC placeholder")
    lines.append(f"                default: {result_reg} = {result_width}'h0;")
    lines.append("            endcase")
    lines.append("        end")
    lines.append("    end")
    lines.append("")

    if result_width < 32:
        lines.append(f"    // Explicit sign-extension, kept separate from the case logic above --")
        lines.append(f"    // this is what actually fixes the timing issue: synthesis maps a")
        lines.append(f"    // standalone replication like this to plain buffer fanout, rather")
        lines.append(f"    // than folding it into whatever logic computed custom_result_narrow.")
        lines.append(f"    assign custom_result = {{{{{ext_bits}{{custom_result_narrow[{rw_msb}]}}}}, custom_result_narrow}};")
        lines.append("")

    lines.append("endmodule")
    lines.append("")

    return "\n".join(lines)


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) != 3:
        print("Usage: python3 gen_custom_unit.py <insts.json> <outdir>")
        return 1

    insts_path = Path(argv[1])
    outdir = Path(argv[2])

    data = json.loads(insts_path.read_text(encoding="utf-8"))
    instructions_used = set(data.get("instructions_used", []))
    custom_used = {i for i in instructions_used if str(i).startswith("custom_")}
    operand_width = data.get("recommended_trim", {}).get("custom_operand_width", 32)
    result_width = data.get("recommended_trim", {}).get("custom_result_width", 32)

    content = gen_custom_unit(instructions_used, operand_width, result_width)
    outpath = outdir / "custom_unit.v"
    outpath.write_text(content, encoding="utf-8")

    if custom_used:
        print(f"Generated {outpath} -- includes: {sorted(custom_used)}, "
              f"operand width narrowed to {operand_width} bits, "
              f"result width narrowed to {result_width} bits (both were fixed at 32)")
    else:
        print(f"Generated {outpath} -- no custom_* instructions used, "
              f"but this is moot: pipeline_top.v's has_custom logic won't "
              f"instantiate this module at all in that case.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())