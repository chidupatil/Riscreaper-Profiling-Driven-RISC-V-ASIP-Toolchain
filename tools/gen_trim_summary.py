#!/usr/bin/env python3
"""
gen_trim_summary.py -- consolidates every trimming decision made across
the whole toolchain into ONE report (JSON + human-readable text),
instead of having to piece it together from pc_width.txt,
data_depth_words.txt, encoding_plan.json, trim_report.json, the bit
profile, and insts.json separately.

Run this LAST, after every other generator (gen_pc.py,
gen_instruction_memory.py, gen_data_memory.py, gen_dense_control.py,
gen_pipeline_regs.py, gen_pipeline_and_tb.py, gen_trimmed_rtl.py) has
already written its own output into the same directory -- this script
only reads what's already there, it doesn't generate any RTL itself.

Baselines (the "untrimmed" starting point each saving is measured
against) are the ORIGINAL, hand-written values this whole project
started from: 32-bit PC, 128-word instruction memory, 64-word data
memory, 32-bit ALU/immediate internals, 5-bit register index (32
architectural registers), 4-bit alu_control, 2-bit alu_op, 2-bit
mem_to_reg, and the full 42-instruction ISA this toolchain supports
(37 RV32I + 5 custom).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Baselines: the untrimmed starting point for every measurement below.
# ---------------------------------------------------------------------------
BASELINE_PC_WIDTH = 32
BASELINE_IMEM_DEPTH_WORDS = 128
BASELINE_DMEM_DEPTH_WORDS = 64
BASELINE_ALU_WIDTH = 32
BASELINE_IMM_WIDTH = 32
BASELINE_REG_INDEX_WIDTH = 5
BASELINE_ALU_CONTROL_WIDTH = 4
BASELINE_ALU_OP_WIDTH = 2
BASELINE_MEM_TO_REG_WIDTH = 2
BASELINE_ARCH_REGISTERS = 32

# Exact field lists per pipeline register, taken directly from
# gen_pipeline_regs.py's port declarations. Each entry is
# (field_name, width_key, baseline_width). width_key is either a fixed
# int (fields that never narrow -- full data words, or ISA-fixed fields
# like funct3/control flags) or one of "pc_width", "imm_width",
# "reg_index_width", "alu_op_width", "mem_to_reg_width", looked up from
# the widths computed for this specific program.
PIPELINE_REG_FIELDS = {
    "if_id_reg": [
        ("pc", "pc_width", BASELINE_PC_WIDTH),
        ("pc_plus4", "pc_width", BASELINE_PC_WIDTH),
        ("instruction", 32, 32),
    ],
    "id_ex_reg": [
        ("pc", "pc_width", BASELINE_PC_WIDTH),
        ("pc_plus4", "pc_width", BASELINE_PC_WIDTH),
        ("read_data1", 32, 32),
        ("read_data2", 32, 32),
        ("imm", "imm_width", BASELINE_IMM_WIDTH),
        ("instruction", 32, 32),
        ("rs1", "reg_index_width", BASELINE_REG_INDEX_WIDTH),
        ("rs2", "reg_index_width", BASELINE_REG_INDEX_WIDTH),
        ("rd", "reg_index_width", BASELINE_REG_INDEX_WIDTH),
        ("alu_op", "alu_op_width", BASELINE_ALU_OP_WIDTH),
        ("alu_src", 1, 1),
        ("mem_read", 1, 1),
        ("mem_write", 1, 1),
        ("funct3", 3, 3),
        ("reg_write", 1, 1),
        ("mem_to_reg", "mem_to_reg_width", BASELINE_MEM_TO_REG_WIDTH),
        ("branch", 1, 1),
        ("jump", 1, 1),
        ("jalr", 1, 1),
    ],
    "ex_mem_reg": [
        ("pc_plus4", "pc_width", BASELINE_PC_WIDTH),
        ("alu_result", 32, 32),
        ("write_data", 32, 32),
        ("branch_target", "pc_width", BASELINE_PC_WIDTH),
        ("zero", 1, 1),
        ("branch_taken", 1, 1),
        ("rd", "reg_index_width", BASELINE_REG_INDEX_WIDTH),
        ("mem_read", 1, 1),
        ("mem_write", 1, 1),
        ("funct3", 3, 3),
        ("reg_write", 1, 1),
        ("mem_to_reg", "mem_to_reg_width", BASELINE_MEM_TO_REG_WIDTH),
        ("jump", 1, 1),
    ],
    "mem_wb_reg": [
        ("pc_plus4", "pc_width", BASELINE_PC_WIDTH),
        ("alu_result", 32, 32),
        ("mem_read_data", 32, 32),
        ("rd", "reg_index_width", BASELINE_REG_INDEX_WIDTH),
        ("reg_write", 1, 1),
        ("mem_to_reg", "mem_to_reg_width", BASELINE_MEM_TO_REG_WIDTH),
    ],
}

# The full instruction set this toolchain is capable of supporting, for
# computing "N used out of 42 possible". Mirrors encoding_plan.py's sets.
ALL_INSTRUCTIONS = sorted(
    {"add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu"}       # R-type (10)
    | {"addi", "andi", "ori", "xori", "slti", "sltiu", "slli", "srli", "srai"}    # I-type ALU (9)
    | {"lb", "lh", "lw", "lbu", "lhu"}                                            # loads (5)
    | {"sb", "sh", "sw"}                                                          # stores (3)
    | {"beq", "bne", "blt", "bge", "bltu", "bgeu"}                                # branches (6)
    | {"jal", "jalr", "lui", "auipc"}                                             # jumps/upper (4)
    | {"custom_mul", "custom_mulh", "custom_mulhu", "custom_mac", "custom_reserved"}  # custom (5)
)


def pct_saved(baseline: int, trimmed: int) -> float:
    if baseline <= 0:
        return 0.0
    return round(100.0 * (baseline - trimmed) / baseline, 1)


def read_json_if_exists(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_int_if_exists(path: Path, default: int) -> int:
    return int(path.read_text(encoding="utf-8").strip()) if path.exists() else default


def count_mem_words(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("//", "#"))
    )


def build_summary(generated_dir: Path, bit_profile_path: Path, insts_json_path: Path) -> dict:
    profile = read_json_if_exists(bit_profile_path)
    insts = read_json_if_exists(insts_json_path)
    rec = insts.get("recommended_trim") or profile.get("recommended_trim", {})
    encoding_plan = read_json_if_exists(generated_dir / "encoding_plan.json")
    trim_report = read_json_if_exists(generated_dir / "trim_report.json")

    pc_width = read_int_if_exists(generated_dir / "pc_width.txt", BASELINE_PC_WIDTH)
    dmem_depth = read_int_if_exists(generated_dir / "data_depth_words.txt", BASELINE_DMEM_DEPTH_WORDS)
    imem_depth = count_mem_words(generated_dir / "instructions.mem")
    if imem_depth == 0:
        imem_depth = BASELINE_IMEM_DEPTH_WORDS

    alu_width = int(rec.get("alu_width", BASELINE_ALU_WIDTH))
    imm_width = int(rec.get("imm_width", BASELINE_IMM_WIDTH))
    reg_index_width = int(rec.get("register_index_width", BASELINE_REG_INDEX_WIDTH))

    alu_op_width = int(encoding_plan.get("alu_op_width", BASELINE_ALU_OP_WIDTH))
    alu_control_width = int(encoding_plan.get("alu_control_width", BASELINE_ALU_CONTROL_WIDTH))
    mem_to_reg_width = int(encoding_plan.get("mem_to_reg_width", BASELINE_MEM_TO_REG_WIDTH))
    mem_to_reg_codes = encoding_plan.get("mem_to_reg_codes", {})
    write_back_mux_eliminated = set(mem_to_reg_codes.keys()) == {"alu"}

    instructions_used = sorted(set(insts.get("instructions_used", profile.get("instructions_used", []))))
    excluded_instructions = sorted(set(ALL_INSTRUCTIONS) - set(instructions_used))

    registers_written = sorted(set(int(r) for r in insts.get("registers_written", [])))
    registers_read = sorted(set(int(r) for r in insts.get("registers_read", [])))
    stored_registers = sorted(set(registers_written) | set(registers_read))
    per_register_width = trim_report.get("applied_trim", {}).get("per_register_data_width", {})

    has_custom = any(str(i).startswith("custom_") for i in instructions_used)

    pipeline_top_path = generated_dir / "pipeline_top.v"
    custom_unit_instantiated = False
    if pipeline_top_path.exists():
        custom_unit_instantiated = "custom_unit u_custom" in pipeline_top_path.read_text(encoding="utf-8")

    forwarding_hazard_ports = {
        "forwarding_unit": ["id_ex_rs1", "id_ex_rs2", "ex_mem_rd", "mem_wb_rd"],
        "hazard_unit": ["id_ex_rd", "if_id_rs1", "if_id_rs2"],
    }

    computed_widths = {
        "pc_width": pc_width,
        "imm_width": imm_width,
        "reg_index_width": reg_index_width,
        "alu_op_width": alu_op_width,
        "mem_to_reg_width": mem_to_reg_width,
    }
    baseline_widths = {
        "pc_width": BASELINE_PC_WIDTH,
        "imm_width": BASELINE_IMM_WIDTH,
        "reg_index_width": BASELINE_REG_INDEX_WIDTH,
        "alu_op_width": BASELINE_ALU_OP_WIDTH,
        "mem_to_reg_width": BASELINE_MEM_TO_REG_WIDTH,
    }

    def field_widths(width_key, baseline):
        if isinstance(width_key, int):
            return width_key, baseline
        return computed_widths[width_key], baseline_widths[width_key]

    pipeline_registers = {}
    for reg_name, fields in PIPELINE_REG_FIELDS.items():
        field_report = []
        baseline_total = 0
        trimmed_total = 0
        for fname, width_key, baseline in fields:
            trimmed_w, baseline_w = field_widths(width_key, baseline)
            baseline_total += baseline_w
            trimmed_total += trimmed_w
            field_report.append({
                "field": fname,
                "baseline_bits": baseline_w,
                "trimmed_bits": trimmed_w,
                "narrowed": trimmed_w != baseline_w,
            })
        pipeline_registers[reg_name] = {
            "baseline_total_bits": baseline_total,
            "trimmed_total_bits": trimmed_total,
            "bits_saved": baseline_total - trimmed_total,
            "percent_saved": pct_saved(baseline_total, trimmed_total),
            "fields": field_report,
        }

    summary = {
        "program_counter": {
            "baseline_width_bits": BASELINE_PC_WIDTH,
            "trimmed_width_bits": pc_width,
            "bits_saved": BASELINE_PC_WIDTH - pc_width,
            "percent_saved": pct_saved(BASELINE_PC_WIDTH, pc_width),
            "note": "Applies to pc.v, pc_adder.v, instruction_memory.v's pc port, AND pipeline_top.v's primary pc_out/pc_plus4_if/pc_next wires -- all generated at this same width together, since narrowing them inconsistently previously caused a proven wraparound bug.",
        },
        "instruction_memory": {
            "baseline_depth_words": BASELINE_IMEM_DEPTH_WORDS,
            "trimmed_depth_words": imem_depth,
            "words_saved": BASELINE_IMEM_DEPTH_WORDS - imem_depth,
            "percent_saved": pct_saved(BASELINE_IMEM_DEPTH_WORDS, imem_depth),
            "note": "Includes the prepended startup stub (sp/ra init) in the word count -- this is the real, final program size.",
        },
        "data_memory": {
            "baseline_depth_words": BASELINE_DMEM_DEPTH_WORDS,
            "trimmed_depth_words": dmem_depth,
            "words_saved": BASELINE_DMEM_DEPTH_WORDS - dmem_depth,
            "percent_saved": pct_saved(BASELINE_DMEM_DEPTH_WORDS, dmem_depth),
            "stack_top_bytes": dmem_depth * 4,
            "note": "Depth only -- per-word width is NOT trimmed (kept at 32 bits) because sub-word (byte/halfword) addressing needs full word structure at every location, and this memory is used heterogeneously (full-width saved registers alongside byte-sized locals in the same array). See gen_data_memory.py.",
        },
        "alu": {
            "port_width_bits": BASELINE_ALU_WIDTH,
            "port_width_note": "Ports (a, b, result) are deliberately kept at 32 bits always -- narrowing them directly caused proven data corruption earlier in this project. All savings below are from internal logic only.",
            "internal_significant_bits": alu_width,
            "internal_bits_saved": BASELINE_ALU_WIDTH - alu_width,
            "internal_percent_saved": pct_saved(BASELINE_ALU_WIDTH, alu_width),
            "alu_control_width_baseline_bits": BASELINE_ALU_CONTROL_WIDTH,
            "alu_control_width_trimmed_bits": alu_control_width,
            "alu_control_bits_saved": BASELINE_ALU_CONTROL_WIDTH - alu_control_width,
            "alu_control_codes": encoding_plan.get("alu_control_codes", {}),
        },
        "immediate": {
            "port_width_bits": BASELINE_IMM_WIDTH,
            "port_width_note": "imm_out port kept at 32 bits always, same reasoning as the ALU.",
            "internal_significant_bits": imm_width,
            "internal_bits_saved": BASELINE_IMM_WIDTH - imm_width,
            "internal_percent_saved": pct_saved(BASELINE_IMM_WIDTH, imm_width),
        },
        "register_file": {
            "architectural_registers": BASELINE_ARCH_REGISTERS,
            "physically_stored_registers": len(stored_registers),
            "stored_register_list": [f"x{r}" for r in stored_registers],
            "registers_never_stored": BASELINE_ARCH_REGISTERS - len(stored_registers),
            "register_index_width_baseline_bits": BASELINE_REG_INDEX_WIDTH,
            "register_index_width_trimmed_bits": reg_index_width,
            "register_index_bits_saved": BASELINE_REG_INDEX_WIDTH - reg_index_width,
            "per_register_data_width_bits": {f"x{k}": v for k, v in per_register_width.items()},
            "note": "Registers not in stored_register_list have NO physical storage at all -- not narrowed, entirely absent. Each stored register's own data width is independent (per_register_data_width_bits), since register_file_v.j2 gives each one its own named signal rather than a shared array.",
        },
        "control_signal_encoding": {
            "alu_op_width_baseline_bits": BASELINE_ALU_OP_WIDTH,
            "alu_op_width_trimmed_bits": alu_op_width,
            "mem_to_reg_width_baseline_bits": BASELINE_MEM_TO_REG_WIDTH,
            "mem_to_reg_width_trimmed_bits": mem_to_reg_width,
            "mem_to_reg_write_back_mux_eliminated": write_back_mux_eliminated,
            "mem_to_reg_codes": mem_to_reg_codes,
            "alu_op_codes": encoding_plan.get("alu_op_codes", {}),
            "note": "Dense mode (gen_dense_control.py) only -- if that script wasn't run, these stay at baseline width using the original fixed encoding." if not encoding_plan else "Dense encoding mode active.",
        },
        "instructions": {
            "total_supported": len(ALL_INSTRUCTIONS),
            "used_count": len(instructions_used),
            "used_instructions": instructions_used,
            "excluded_count": len(excluded_instructions),
            "excluded_instructions": excluded_instructions,
            "percent_excluded": pct_saved(len(ALL_INSTRUCTIONS), len(instructions_used)),
            "note": "control_unit.v, alu_control.v, and branch_unit.v only ever contain case arms for used_instructions -- excluded ones have no corresponding logic at all, not disabled logic.",
        },
        "custom_unit": {
            "any_custom_instruction_used": has_custom,
            "instantiated_in_pipeline_top": custom_unit_instantiated,
            "note": "custom_unit.v the FILE is never modified, but is only instantiated (and therefore only costs real hardware) if a custom_* instruction was actually used." if not has_custom else "This program uses a custom instruction, so custom_unit is instantiated normally.",
        },
        "branch_unit": {
            "any_branch_instruction_used": any(i in instructions_used for i in ("beq", "bne", "blt", "bge", "bltu", "bgeu")),
            "instantiated_in_pipeline_top": "branch_unit u_branch" in (generated_dir / "pipeline_top.v").read_text(encoding="utf-8") if (generated_dir / "pipeline_top.v").exists() else None,
            "note": "Same pattern as custom_unit: branch_unit.v's output is gated by the branch control signal, which is never asserted if no branch instruction exists at all, so it's only instantiated when actually needed.",
        },
        "hazard_unit": {
            "load_use_stall_possible": any(i in instructions_used for i in ("lb", "lh", "lw", "lbu", "lhu")),
            "flush_possible": any(i in instructions_used for i in ("beq", "bne", "blt", "bge", "bltu", "bgeu", "jal", "jalr")),
            "instantiated_in_pipeline_top": "hazard_unit u_hazard" in (generated_dir / "pipeline_top.v").read_text(encoding="utf-8") if (generated_dir / "pipeline_top.v").exists() else None,
            "note": "Only instantiated if either condition above is true -- both stem from independent conditions in hazard_unit's own logic that otherwise always evaluate to their inert defaults.",
        },
        "pipeline_registers": pipeline_registers,
        "forwarding_and_hazard_units": {
            "register_index_port_width_bits": reg_index_width,
            "baseline_register_index_port_width_bits": BASELINE_REG_INDEX_WIDTH,
            "ports_at_this_width": forwarding_hazard_ports,
            "note": "forwarding_unit.v and hazard_unit.v's rs1/rs2/rd ports (listed above) are generated at the real register_index_width, not a fixed 5 bits.",
        },
        "halt_detection": {
            "primary_pc_path_note": "pc.v, pc_adder.v, instruction_memory.v, and pipeline_top.v's primary fetch wires stay full-precision AT the trimmed pc_width (not narrowed-after-the-fact) -- see program_counter section above.",
        },
    }
    return summary


def render_text_report(summary: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("TRIMMING SUMMARY")
    lines.append("=" * 70)

    def section(title, rows):
        lines.append("")
        lines.append(f"-- {title} --")
        for row in rows:
            lines.append(f"  {row}")

    pc = summary["program_counter"]
    section("Program Counter", [
        f"{BASELINE_PC_WIDTH} bits -> {pc['trimmed_width_bits']} bits "
        f"({pc['bits_saved']} bits saved, {pc['percent_saved']}%)",
    ])

    im = summary["instruction_memory"]
    section("Instruction Memory", [
        f"{im['baseline_depth_words']} words -> {im['trimmed_depth_words']} words "
        f"({im['words_saved']} words saved, {im['percent_saved']}%)",
    ])

    dm = summary["data_memory"]
    section("Data Memory", [
        f"{dm['baseline_depth_words']} words -> {dm['trimmed_depth_words']} words "
        f"({dm['words_saved']} words saved, {dm['percent_saved']}%)",
        f"per-word width: unchanged (32 bits) -- see note in JSON for why",
    ])

    alu = summary["alu"]
    section("ALU", [
        f"port width: unchanged ({alu['port_width_bits']} bits, by design)",
        f"internal significant bits: {alu['internal_significant_bits']} "
        f"({alu['internal_bits_saved']} bits saved, {alu['internal_percent_saved']}%)",
        f"alu_control width: {alu['alu_control_width_baseline_bits']} bits -> "
        f"{alu['alu_control_width_trimmed_bits']} bits ({alu['alu_control_bits_saved']} bits saved)",
    ])

    imm = summary["immediate"]
    section("Immediate", [
        f"port width: unchanged ({imm['port_width_bits']} bits, by design)",
        f"internal significant bits: {imm['internal_significant_bits']} "
        f"({imm['internal_bits_saved']} bits saved, {imm['internal_percent_saved']}%)",
    ])

    rf = summary["register_file"]
    section("Register File", [
        f"{rf['architectural_registers']} architectural registers -> "
        f"{rf['physically_stored_registers']} physically stored ({rf['stored_register_list']})",
        f"register index width: {rf['register_index_width_baseline_bits']} bits -> "
        f"{rf['register_index_width_trimmed_bits']} bits",
        f"per-register data widths: {rf['per_register_data_width_bits']}",
    ])

    section("Pipeline Registers", [])
    for reg_name, data in summary["pipeline_registers"].items():
        lines.append(f"  {reg_name}: {data['baseline_total_bits']} bits -> "
                     f"{data['trimmed_total_bits']} bits "
                     f"({data['bits_saved']} bits saved, {data['percent_saved']}%)")
        for f in data["fields"]:
            marker = "narrowed" if f["narrowed"] else "fixed (full data width, by design)"
            lines.append(f"      {f['field']}: {f['baseline_bits']} -> {f['trimmed_bits']} bits [{marker}]")

    cs = summary["control_signal_encoding"]
    section("Control Signal Encoding", [
        f"alu_op: {cs['alu_op_width_baseline_bits']} bits -> {cs['alu_op_width_trimmed_bits']} bits",
        f"mem_to_reg: {cs['mem_to_reg_width_baseline_bits']} bits -> {cs['mem_to_reg_width_trimmed_bits']} bits"
        + (" (write-back mux ELIMINATED entirely)" if cs["mem_to_reg_write_back_mux_eliminated"] else ""),
    ])

    ins = summary["instructions"]
    section("Instructions", [
        f"{ins['used_count']} / {ins['total_supported']} used ({ins['percent_excluded']}% excluded)",
        f"used: {', '.join(ins['used_instructions'])}",
    ])

    cu = summary["custom_unit"]
    section("Custom Unit", [
        f"instantiated: {cu['instantiated_in_pipeline_top']}",
    ])

    bu = summary["branch_unit"]
    section("Branch Unit", [
        f"instantiated: {bu['instantiated_in_pipeline_top']}",
    ])

    hu = summary["hazard_unit"]
    section("Hazard Unit", [
        f"instantiated: {hu['instantiated_in_pipeline_top']}",
    ])

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) != 4:
        print("Usage: python3 tools/gen_trim_summary.py <bit_profile.json> <insts.json> <generated_dir>")
        return 1

    bit_profile_path = Path(argv[1])
    insts_json_path = Path(argv[2])
    generated_dir = Path(argv[3])

    summary = build_summary(generated_dir, bit_profile_path, insts_json_path)

    json_path = generated_dir / "trim_summary.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    text_path = generated_dir / "trim_summary.txt"
    text_path.write_text(render_text_report(summary), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {text_path}")
    print()
    print(render_text_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())