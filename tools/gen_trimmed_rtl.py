#!/usr/bin/env python3
"""
gen_trimmed_rtl.py -- ASIP bit-width trimming for the RTL your real
templates (alu_v.j2, imm_gen_v.j2, register_file_v.j2) actually produce.

DESIGN PRINCIPLE:
------------------
Every port that pipeline_top.v connects to (a/b/result on the ALU,
imm_out on imm_gen, write_data/read_data1/read_data2/rs1/rs2/rd on the
register file) is left at its template-rendered width. pipeline_top.v is
never modified, so nothing here can create a port-width mismatch with it.

Verified with real Icarus Verilog simulation:
  - Narrowing a signed VALUE port directly (immediate, ALU result,
    register data) and letting it connect to pipeline_top.v's unmodified
    wires zero-extends the narrow value into the wider wire, which is
    correct for magnitude but destroys sign: addi x1,x0,-5 came back as
    +507 instead of -5.
  - U-type immediates (lui/auipc) carry their meaning in the UPPER bits
    (lower 12 are architecturally 0); no sign-extension-from-a-narrow-base
    scheme can represent them, so they are exempted entirely.
  - Register INDEX fields (rs1/rs2/rd) are safe to narrow directly: they
    are unsigned addresses, and pipeline_top.v's driving wires are always
    wide enough for any index actually used, so Verilog just prunes
    always-zero high bits both directions.
  - A shared bus (one register file data port used by every register)
    cannot be "wide for one register, narrow for another" -- proven by
    corrupting an ordinary `addi sp,sp,-32` down to 0 when a previous
    version of this tooling tried exactly that. That is NOT what this
    script does. What IS safe and IS done here: your register_file_v.j2
    gives each used register its OWN NAMED, INDEPENDENT storage reg
    (r1, r2, r8, ...) -- these do not share a bus with each other at the
    storage level (only the read/write PORTS are shared, and those stay
    32-bit), so each one can be narrowed to its own true required width
    independently, with sign-extension on read and truncation on write.

This script only touches alu.v, imm_gen.v, and register_file.v -- the
three modules whose exact template structure this file matches. It does
not touch control_unit.v, alu_control.v, branch_unit.v, or pipeline_top.v.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def insert_banner(text: str, banner: str) -> str:
    return text if banner in text else banner + "\n" + text


def patch_imm_gen(path: Path, imm_width: int) -> str:
    text = path.read_text(encoding="utf-8")
    if imm_width < 32 and "output reg [31:0] imm_out" in text and "assign opcode = instruction[6:0];" in text:
        w = imm_width
        text = text.replace(
            "output reg [31:0] imm_out",
            "output [31:0] imm_out",
        )
        text = text.replace(
            "assign opcode = instruction[6:0];",
            "assign opcode = instruction[6:0];\n\n"
            "    reg [31:0] imm_out_full;\n"
            "    wire is_u_type = (opcode == 7'b0110111) || (opcode == 7'b0010111);",
        )
        text = text.replace("imm_out = ", "imm_out_full = ")
        replicate = 32 - w
        sign_expr = f"imm_out_full[{w - 1}]"
        low_expr = f"imm_out_full[{w - 1}:0]"
        narrow_rhs = "{{" + str(replicate) + "{" + sign_expr + "}}, " + low_expr + "}"
        text = text.replace(
            "endmodule",
            "\n    // U-type (lui/auipc) immediates carry their meaning in the UPPER\n"
            "    // bits (lower 12 are architecturally 0) -- no low-bits-plus-sign-\n"
            "    // extension scheme can represent them, so they pass through at\n"
            "    // full precision regardless of the profiled width for other kinds.\n"
            f"    assign imm_out = is_u_type ? imm_out_full : {narrow_rhs};\n"
            "endmodule",
        )
        banner = (
            f"// Trim applied: immediate significant width = {imm_width} bits "
            f"(sign-extended internally; port stays 32-bit; U-type exempted)"
        )
    else:
        banner = "// Trim applied: immediate width unchanged (32 bits, or template structure not recognized)"
    text = insert_banner(text, banner)
    path.write_text(text, encoding="utf-8")
    return banner


def patch_alu(path: Path, alu_width: int) -> str:
    text = path.read_text(encoding="utf-8")
    marker = "wire [32:0] sub_result = {1'b0, a} - {1'b0, b};"
    if alu_width < 32 and "output reg [31:0] result" in text and marker in text and "always @(*) begin" in text:
        w = alu_width
        start_marker = "always @(*) begin"
        end_marker = "endcase\n    end"
        start = text.index(start_marker)
        end = text.index(end_marker) + len(end_marker)
        block = text[start:end]
        block_fixed = re.sub(r"\bresult\b", "result_full", block)
        text = text[:start] + block_fixed + text[end:]

        text = text.replace(
            "output reg [31:0] result",
            "output [31:0] result",
        )
        text = text.replace(
            marker,
            marker + "\n    reg [31:0] result_full;",
        )
        replicate = 32 - w
        sign_expr = f"result_full[{w - 1}]"
        low_expr = f"result_full[{w - 1}:0]"
        rhs = "{{" + str(replicate) + "{" + sign_expr + "}}, " + low_expr + "}"
        text = text.replace(
            "endmodule",
            f"\n    assign result = {rhs};\nendmodule",
        )
        banner = (
            f"// Trim applied: ALU result carries only {alu_width} significant bits "
            f"(sign-extended internally; a/b/result ports stay 32-bit; "
            f"a/b themselves are never narrowed, so overflow's a[31]/b[31] stay valid)"
        )
    else:
        banner = "// Trim applied: ALU width unchanged (32 bits, or template structure not recognized)"
    text = insert_banner(text, banner)
    path.write_text(text, encoding="utf-8")
    return banner


def patch_register_file(path: Path, reg_index_width: int, per_register_width: dict[int, int], visible_registers: list[int]) -> str:
    text = path.read_text(encoding="utf-8")
    notes = []

    # Register INDEX narrowing (rs1/rs2/rd): safe -- unsigned addresses,
    # pipeline_top.v's driving wires are always >= this width for any
    # register actually used.
    if reg_index_width < 5:
        for name in ("rs1", "rs2", "rd"):
            text = re.sub(
                rf"(\binput\s+)\[4:0\](\s*{name}\b)",
                rf"\1[{reg_index_width - 1}:0]\2",
                text,
            )
        notes.append(f"register index ports narrowed to {reg_index_width} bits (safe: unsigned address pruning)")
    else:
        notes.append("register index width unchanged (5 bits)")

    # Per-register storage narrowing: each rN is its OWN, INDEPENDENT reg
    # (not a shared array/bus), so each can be narrowed to its own real
    # required width with sign-extension on read / truncation on write,
    # with no risk to any other register -- unlike the array-based design
    # this project moved away from, there is no shared-bus corruption
    # possible here at the storage level.
    narrowed_any = False
    for reg_num, width in sorted(per_register_width.items()):
        if width >= 32:
            continue
        decl = f"reg [31:0] r{reg_num};"
        if decl not in text:
            continue
        narrowed_any = True
        text = text.replace(decl, f"reg [{width - 1}:0] r{reg_num};")
        text = text.replace(f"r{reg_num} = 32'h00000000;", f"r{reg_num} = {width}'h0;")
        text = text.replace(
            f"5'd{reg_num}: r{reg_num} <= write_data;",
            f"5'd{reg_num}: r{reg_num} <= write_data[{width - 1}:0];",
        )
        replicate = 32 - width
        sign_expr = f"r{reg_num}[{width - 1}]"
        rhs = "{{" + str(replicate) + "{" + sign_expr + "}}, " + f"r{reg_num}" + "}"
        for readvar in ("read_data1_r", "read_data2_r"):
            text = text.replace(
                f"5'd{reg_num}: {readvar} = r{reg_num};",
                f"5'd{reg_num}: {readvar} = {rhs};",
            )
    if narrowed_any:
        widths_str = ", ".join(f"x{k}={v}b" for k, v in sorted(per_register_width.items()) if v < 32)
        notes.append(f"per-register storage narrowed independently ({widths_str}); read/write ports stay 32-bit")
    else:
        notes.append("no per-register storage narrowing applied (all registers need full width, or template structure not recognized)")

    banner = "// Trim applied: " + "; ".join(notes) + f"; visible registers={visible_registers}"
    text = insert_banner(text, banner)
    path.write_text(text, encoding="utf-8")
    return banner


def patch_trim_report(out_dir: Path, profile: dict, applied: dict, banners: dict, skipped: list[str]):
    report = {
        "recommended_trim": profile.get("recommended_trim", {}),
        "applied_trim": applied,
        "per_file_result": banners,
        "not_touched": skipped,
        "notes": [
            "This pass ONLY patches alu.v, imm_gen.v, and register_file.v, matching "
            "the exact structure alu_v.j2 / imm_gen_v.j2 / register_file_v.j2 render. "
            "It deliberately does NOT touch pipeline_top.v, tb_pipeline_top.v, "
            "control_unit.v, alu_control.v, or branch_unit.v.",
            "Register data width is now computed PER REGISTER (each named r-register "
            "is independent storage, not a shared bus), which is both safer and more "
            "aggressive than a single width shared across all registers.",
        ],
    }
    (out_dir / "trim_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) != 3:
        print("Usage: python3 tools/gen_trimmed_rtl.py <bit_profile.json> <generated_dir>")
        return 1

    profile = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out_dir = Path(argv[2])
    rec = profile.get("recommended_trim", {})

    alu_width = int(rec.get("alu_width", 32))
    imm_width = int(rec.get("imm_width", 32))
    reg_index_width = int(rec.get("register_index_width", 5))

    reg_write_widths = profile.get("register_write_required_width", {})
    per_register_width: dict[int, int] = {}
    for reg_name, width in reg_write_widths.items():
        try:
            idx = int(str(reg_name).lower().lstrip("x"))
        except ValueError:
            continue
        per_register_width[idx] = max(1, min(32, int(width)))
    visible_registers = profile.get("registers_used", [])

    applied = {
        "alu_width": alu_width,
        "imm_width": imm_width,
        "register_index_width": reg_index_width,
        "per_register_data_width": per_register_width,
    }

    banners = {}
    skipped = []

    alu_file = out_dir / "alu.v"
    imm_file = out_dir / "imm_gen.v"
    reg_file = out_dir / "register_file.v"

    if alu_file.exists():
        banners["alu.v"] = patch_alu(alu_file, alu_width)
    else:
        skipped.append("alu.v (not found)")

    if imm_file.exists():
        banners["imm_gen.v"] = patch_imm_gen(imm_file, imm_width)
    else:
        skipped.append("imm_gen.v (not found)")

    if reg_file.exists():
        banners["register_file.v"] = patch_register_file(reg_file, reg_index_width, per_register_width, visible_registers)
    else:
        skipped.append("register_file.v (not found)")

    skipped.append("pipeline_top.v / tb_pipeline_top.v (not touched by design)")
    skipped.append("control_unit.v / alu_control.v / branch_unit.v (no width trimming needed/attempted)")

    patch_trim_report(out_dir, profile, applied, banners, skipped)

    print("Applied trim-aware patching to generated RTL:")
    print(f" ALU width            : {alu_width}")
    print(f" Immediate width      : {imm_width}")
    print(f" Register index width : {reg_index_width}")
    print(f" Per-register widths  : {per_register_width}")
    for f, b in banners.items():
        print(f" {f}: {b}")
    print(f" Report               : {out_dir / 'trim_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())