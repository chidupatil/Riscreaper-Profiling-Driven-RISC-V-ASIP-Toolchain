#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from jinja2 import Template
except Exception:
    Template = None


def sanitize_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(name).strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "program"


def infer_program_name(summary: dict, json_path: Path) -> str:
    for key in ("program", "name", "base_name", "source", "elf", "input"):
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).stem
    return json_path.stem.replace("_insts", "")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_template(path: Path):
    if Template is None:
        return None
    if not path.exists():
        # Try the other common naming convention before giving up --
        # confirmed via a real bug that this mismatch (register_file.v.j2
        # vs register_file_v.j2) can silently fall back to a hardcoded
        # version missing a real fix the actual template has, with zero
        # warning that it happened.
        alt_path = path.with_name(path.name.replace(".v.j2", "_v.j2"))
        if alt_path.exists():
            return Template(alt_path.read_text(encoding="utf-8"))
        print(f"WARNING: template not found at {path} (or {alt_path}) -- "
              f"falling back to a hardcoded, simpler version. This can "
              f"silently miss real fixes the actual template has -- "
              f"verify this is intentional.", file=sys.stderr)
        return None
    return Template(path.read_text(encoding="utf-8"))


def render_or_fallback(template, fallback: str, **kwargs) -> str:
    if template is None:
        return fallback
    return template.render(**kwargs)


def make_control_unit_fallback() -> str:
    return """module control_unit(
    input  [6:0] opcode,
    input  [4:0] rd,
    output reg       branch,
    output reg       mem_read,
    output reg [1:0] mem_to_reg,
    output reg [1:0] alu_op,
    output reg       mem_write,
    output reg       alu_src,
    output reg       reg_write,
    output reg       jump,
    output reg       jalr
);
always @(*) begin
    branch     = 1'b0;
    mem_read   = 1'b0;
    mem_to_reg = 2'b00;
    alu_op     = 2'b00;
    mem_write  = 1'b0;
    alu_src    = 1'b0;
    reg_write  = 1'b0;
    jump       = 1'b0;
    jalr       = 1'b0;

    case (opcode)
        7'b0110011: begin reg_write = (rd != 5'd0); alu_op = 2'b10; end
        7'b0010011: begin reg_write = (rd != 5'd0); alu_src = 1'b1; alu_op = 2'b11; end
        7'b0000011: begin mem_read = 1'b1; mem_to_reg = 2'b01; alu_src = 1'b1; reg_write = (rd != 5'd0); alu_op = 2'b00; end
        7'b0100011: begin mem_write = 1'b1; alu_src = 1'b1; alu_op = 2'b00; end
        7'b1100011: begin branch = 1'b1; alu_op = 2'b01; end
        7'b1101111: begin jump = 1'b1; reg_write = (rd != 5'd0); mem_to_reg = 2'b10; end
        7'b1100111: begin jump = 1'b1; jalr = 1'b1; alu_src = 1'b1; reg_write = (rd != 5'd0); mem_to_reg = 2'b10; end
        7'b0110111: begin alu_src = 1'b1; reg_write = (rd != 5'd0); alu_op = 2'b11; end
        7'b0010111: begin alu_src = 1'b1; reg_write = (rd != 5'd0); alu_op = 2'b11; end
        7'b0001011: begin reg_write = (rd != 5'd0); end
        default: begin end
    endcase
end
endmodule
"""


def make_alu_control_fallback() -> str:
    return """module alu_control(
    input  [1:0] alu_op,
    input  [2:0] funct3,
    input        funct7_5,
    output reg [3:0] alu_control
);
always @(*) begin
    case (alu_op)
        2'b00: alu_control = 4'b0010;
        2'b01: alu_control = 4'b0110;
        2'b10: begin
            case ({funct7_5, funct3})
                4'b0_000: alu_control = 4'b0010;
                4'b1_000: alu_control = 4'b0110;
                4'b0_111: alu_control = 4'b0000;
                4'b0_110: alu_control = 4'b0001;
                4'b0_100: alu_control = 4'b0011;
                4'b0_001: alu_control = 4'b0100;
                4'b0_101: alu_control = 4'b0101;
                4'b1_101: alu_control = 4'b0111;
                4'b0_010: alu_control = 4'b1000;
                4'b0_011: alu_control = 4'b1001;
                default:  alu_control = 4'b0010;
            endcase
        end
        2'b11: begin
            case (funct3)
                3'b000: alu_control = 4'b0010;
                3'b111: alu_control = 4'b0000;
                3'b110: alu_control = 4'b0001;
                3'b100: alu_control = 4'b0011;
                3'b001: alu_control = 4'b0100;
                3'b101: alu_control = funct7_5 ? 4'b0111 : 4'b0101;
                3'b010: alu_control = 4'b1000;
                3'b011: alu_control = 4'b1001;
                default: alu_control = 4'b0010;
            endcase
        end
        default: alu_control = 4'b0010;
    endcase
end
endmodule
"""


def make_imm_gen_fallback() -> str:
    return """module imm_gen(
    input  [31:0] instruction,
    output reg [31:0] imm_out
);
wire [6:0] opcode = instruction[6:0];
always @(*) begin
    case (opcode)
        7'b0010011, 7'b0000011, 7'b1100111:
            imm_out = {{20{instruction[31]}}, instruction[31:20]};
        7'b0100011:
            imm_out = {{20{instruction[31]}}, instruction[31:25], instruction[11:7]};
        7'b1100011:
            imm_out = {{19{instruction[31]}}, instruction[31], instruction[7], instruction[30:25], instruction[11:8], 1'b0};
        7'b0110111, 7'b0010111:
            imm_out = {instruction[31:12], 12'b0};
        7'b1101111:
            imm_out = {{11{instruction[31]}}, instruction[31], instruction[19:12], instruction[20], instruction[30:21], 1'b0};
        default:
            imm_out = 32'b0;
    endcase
end
endmodule
"""


def make_branch_unit_fallback() -> str:
    return """module branch_unit(
    input  [2:0] funct3,
    input        zero,
    input        negative,
    input        carry_out,
    input        overflow,
    output reg   branch_taken
);
always @(*) begin
    case (funct3)
        3'b000: branch_taken =  zero;
        3'b001: branch_taken = ~zero;
        3'b100: branch_taken =  negative;
        3'b101: branch_taken = ~negative;
        3'b110: branch_taken = ~carry_out;
        3'b111: branch_taken =  carry_out;
        default: branch_taken = 1'b0;
    endcase
end
endmodule
"""


def make_alu_fallback() -> str:
    return """module alu(
    input  [31:0] a,
    input  [31:0] b,
    input  [3:0]  alu_control,
    output reg [31:0] result,
    output        zero,
    output        negative,
    output reg    overflow,
    output reg    carry_out
);
wire [32:0] add_ext = {1'b0, a} + {1'b0, b};
wire [32:0] sub_ext = {1'b0, a} - {1'b0, b};
always @(*) begin
    overflow = 1'b0;
    carry_out = 1'b0;
    case (alu_control)
        4'b0000: result = a & b;
        4'b0001: result = a | b;
        4'b0010: begin result = a + b; carry_out = add_ext[32]; overflow = (~(a[31] ^ b[31])) & (a[31] ^ result[31]); end
        4'b0011: result = a ^ b;
        4'b0100: result = a << b[4:0];
        4'b0101: result = a >> b[4:0];
        4'b0110: begin result = a - b; carry_out = ~sub_ext[32]; overflow = ((a[31] ^ b[31])) & (a[31] ^ result[31]); end
        4'b0111: result = $signed(a) >>> b[4:0];
        4'b1000: result = ($signed(a) < $signed(b)) ? 32'd1 : 32'd0;
        4'b1001: result = (a < b) ? 32'd1 : 32'd0;
        default: result = 32'b0;
    endcase
end
assign zero = (result == 32'b0);
assign negative = result[31];
endmodule
"""


def make_register_file_fallback() -> str:
    return """module register_file(
    input         clk,
    input         reg_write,
    input  [4:0]  rs1,
    input  [4:0]  rs2,
    input  [4:0]  rd,
    input  [31:0] write_data,
    output [31:0] read_data1,
    output [31:0] read_data2
);
reg [31:0] registers [0:31];
integer i;
initial begin
    for (i = 0; i < 32; i = i + 1)
        registers[i] = 32'b0;
end
always @(posedge clk) begin
    if (reg_write && (rd != 5'd0))
        registers[rd] <= write_data;
    registers[0] <= 32'b0;
end
// Write-before-read forwarding: without this, a register written in
// WB and read in ID at the SAME clock edge returns the OLD value --
// the write is a non-blocking assignment (takes effect at the clock
// edge) while this read is purely combinational from the pre-update
// state, so it's a genuine race. Standard EX/MEM and MEM/WB forwarding
// (in forwarding_unit, operating at the EX stage) never covers this,
// since by the time an instruction reaches EX, its ID-stage register
// read already happened and already got the stale value baked into
// id_ex_reg. Confirmed via simulation: a 3-instruction gap between a
// register's write and a later read of it (e.g. `addi sp,sp,-32` then
// `addi s0,sp,32` a few instructions later) lands the write in WB on
// the exact same cycle the read happens in ID, corrupting the read
// silently -- with X propagating from there into a later stack
// restore that depended on the corrupted value, eventually stalling
// the whole pipeline.
assign read_data1 = (rs1 == 5'd0) ? 32'b0 :
                     (reg_write && (rd == rs1) && (rd != 5'd0)) ? write_data :
                     registers[rs1];
assign read_data2 = (rs2 == 5'd0) ? 32'b0 :
                     (reg_write && (rd == rs2) && (rd != 5'd0)) ? write_data :
                     registers[rs2];
endmodule
"""


def make_program_tb(program_name: str) -> str:
    mod_suffix = sanitize_name(program_name)
    return f"""`timescale 1ns / 1ps
module tb_pipeline_top_{mod_suffix};

    reg clk;
    reg reset;
    integer cycle_count;

    wire [31:0] dbg_pc;
    wire [31:0] dbg_instr_if;
    wire [31:0] dbg_instr_id;
    wire [31:0] dbg_alu_result_ex;
    wire        dbg_branch_taken_ex;
    wire        dbg_mem_write_mem;
    wire [31:0] dbg_mem_addr_mem;
    wire [31:0] dbg_mem_wdata_mem;
    wire        dbg_reg_write_wb;
    wire [4:0]  dbg_rd_wb;
    wire [31:0] dbg_wb_data;

    pipeline_top u_dut (
        .clk                 (clk),
        .reset               (reset),
        .dbg_pc              (dbg_pc),
        .dbg_instr_if        (dbg_instr_if),
        .dbg_instr_id        (dbg_instr_id),
        .dbg_alu_result_ex   (dbg_alu_result_ex),
        .dbg_branch_taken_ex (dbg_branch_taken_ex),
        .dbg_mem_write_mem   (dbg_mem_write_mem),
        .dbg_mem_addr_mem    (dbg_mem_addr_mem),
        .dbg_mem_wdata_mem   (dbg_mem_wdata_mem),
        .dbg_reg_write_wb    (dbg_reg_write_wb),
        .dbg_rd_wb           (dbg_rd_wb),
        .dbg_wb_data         (dbg_wb_data)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("pipeline_top_{mod_suffix}.vcd");
        $dumpvars(0, tb_pipeline_top_{mod_suffix});
    end

    task print_state;
        begin
            $display("[%0t] cycle=%0d pc=0x%08h if=0x%08h id=0x%08h ex=0x%08h br=%b memw=%b mema=0x%08h memd=0x%08h wb_we=%b wb_rd=x%0d wb_data=0x%08h",
                     $time, cycle_count,
                     dbg_pc, dbg_instr_if, dbg_instr_id, dbg_alu_result_ex,
                     dbg_branch_taken_ex, dbg_mem_write_mem, dbg_mem_addr_mem,
                     dbg_mem_wdata_mem, dbg_reg_write_wb, dbg_rd_wb, dbg_wb_data);
        end
    endtask

    initial begin
        cycle_count = 0;
        reset = 1'b1;

        repeat (5) @(posedge clk);
        reset = 1'b0;

        repeat (120) begin
            @(posedge clk);
            cycle_count = cycle_count + 1;

            if (cycle_count <= 20 || dbg_mem_write_mem || dbg_reg_write_wb || dbg_branch_taken_ex)
                print_state();
        end

        $display("PASS: program-specific debug smoke test completed for {program_name}");
        $finish;
    end

    initial begin
        #5000;
        $display("FAIL: timeout in tb_pipeline_top_{mod_suffix}.v");
        $finish;
    end

endmodule
"""


def make_stable_tb() -> str:
    return r'''`timescale 1ns / 1ps
module tb_pipeline_top;

    reg clk;
    reg reset;
    integer cycle_count;

    wire [31:0] dbg_pc;
    wire [31:0] dbg_instr_if;
    wire [31:0] dbg_instr_id;
    wire [31:0] dbg_alu_result_ex;
    wire        dbg_branch_taken_ex;
    wire        dbg_mem_write_mem;
    wire [31:0] dbg_mem_addr_mem;
    wire [31:0] dbg_mem_wdata_mem;
    wire        dbg_reg_write_wb;
    wire [4:0]  dbg_rd_wb;
    wire [31:0] dbg_wb_data;

    pipeline_top u_dut (
        .clk                 (clk),
        .reset               (reset),
        .dbg_pc              (dbg_pc),
        .dbg_instr_if        (dbg_instr_if),
        .dbg_instr_id        (dbg_instr_id),
        .dbg_alu_result_ex   (dbg_alu_result_ex),
        .dbg_branch_taken_ex (dbg_branch_taken_ex),
        .dbg_mem_write_mem   (dbg_mem_write_mem),
        .dbg_mem_addr_mem    (dbg_mem_addr_mem),
        .dbg_mem_wdata_mem   (dbg_mem_wdata_mem),
        .dbg_reg_write_wb    (dbg_reg_write_wb),
        .dbg_rd_wb           (dbg_rd_wb),
        .dbg_wb_data         (dbg_wb_data)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("pipeline_top.vcd");
        $dumpvars(0, tb_pipeline_top);
    end

    task print_state;
        begin
            $display("[%0t] cycle=%0d", $time, cycle_count);
            $display("    PC           = 0x%08h", dbg_pc);
            $display("    IF instr     = 0x%08h", dbg_instr_if);
            $display("    ID instr     = 0x%08h", dbg_instr_id);
            $display("    EX alu_result= 0x%08h", dbg_alu_result_ex);
            $display("    EX branch    = %b", dbg_branch_taken_ex);
            $display("    MEM write_en = %b", dbg_mem_write_mem);
            $display("    MEM addr     = 0x%08h", dbg_mem_addr_mem);
            $display("    MEM wdata    = 0x%08h", dbg_mem_wdata_mem);
            $display("    WB reg_write = %b", dbg_reg_write_wb);
            $display("    WB rd        = x%0d", dbg_rd_wb);
            $display("    WB data      = 0x%08h", dbg_wb_data);
            $display("------------------------------------------------------");
        end
    endtask

    initial begin
        cycle_count = 0;
        reset = 1'b1;

        $display("============================================================");
        $display("   RISC-V Pipeline Simulation Start");
        $display("   Debug-port based TB (RTL + Post-Synthesis Compatible)");
        $display("============================================================");

        repeat (5) @(posedge clk);
        reset = 1'b0;

        repeat (120) begin
            @(posedge clk);
            cycle_count = cycle_count + 1;

            if (cycle_count <= 20 || dbg_mem_write_mem || dbg_reg_write_wb || dbg_branch_taken_ex)
                print_state();
        end

        $display("============================================================");
        $display("PASS: portable debug smoke test completed");
        $display("============================================================");
        $finish;
    end

    initial begin
        #5000;
        $display("FAIL: simulation timeout");
        $finish;
    end

endmodule
'''


def generate_all(inst_json: Path, out_dir: Path) -> None:
    summary = json.loads(inst_json.read_text(encoding="utf-8"))
    instructions = sorted(set(summary.get("instructions_used", [])))
    registers_read = sorted(set(summary.get("registers_read", [])))
    registers_written = sorted(set(summary.get("registers_written", [])))
    stored_registers = sorted(r for r in registers_written if r != 0)
    visible_registers = sorted(set(registers_read) | set(registers_written) | {0})

    branch_set = {"beq", "bne", "blt", "bge", "bltu", "bgeu"}
    load_set = {"lb", "lh", "lw", "lbu", "lhu"}
    store_set = {"sb", "sh", "sw"}
    i_alu_set = {"addi", "andi", "ori", "xori", "slti", "sltiu", "slli", "srli", "srai"}
    r_type_set = {"add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu"}
    u_set = {"lui", "auipc"}
    j_set = {"jal"}
    jalr_set = {"jalr"}

    has_branch = any(inst in branch_set for inst in instructions)
    has_i_type = any(inst in (i_alu_set | load_set | jalr_set) for inst in instructions)
    has_s_type = any(inst in store_set for inst in instructions)
    has_b_type = any(inst in branch_set for inst in instructions)
    has_u_type = any(inst in u_set for inst in instructions)
    has_j_type = any(inst in j_set for inst in instructions)

    has_r_type = any(inst in r_type_set for inst in instructions)
    has_i_alu = any(inst in i_alu_set for inst in instructions)
    has_load = any(inst in load_set for inst in instructions)
    has_store = any(inst in store_set for inst in instructions)
    has_jal = any(inst in j_set for inst in instructions) or ("j" in instructions)
    has_jalr = any(inst in jalr_set for inst in instructions) or ("ret" in instructions)
    has_lui = "lui" in instructions
    has_auipc = "auipc" in instructions
    has_custom = any(str(inst).startswith("custom_") for inst in instructions)

    alu_ops = set()
    if any(inst in instructions for inst in {"add", "addi", "lb", "lh", "lw", "lbu", "lhu", "sb", "sh", "sw", "jalr", "auipc"}):
        alu_ops.add("ADD")
    if "sub" in instructions or any(inst in instructions for inst in branch_set):
        alu_ops.add("SUB")
    if any(inst in instructions for inst in {"and", "andi"}):
        alu_ops.add("AND")
    if any(inst in instructions for inst in {"or", "ori"}):
        alu_ops.add("OR")
    if any(inst in instructions for inst in {"xor", "xori"}):
        alu_ops.add("XOR")
    if any(inst in instructions for inst in {"sll", "slli"}):
        alu_ops.add("SLL")
    if any(inst in instructions for inst in {"srl", "srli"}):
        alu_ops.add("SRL")
    if any(inst in instructions for inst in {"sra", "srai"}):
        alu_ops.add("SRA")
    if any(inst in instructions for inst in {"slt", "slti"}):
        alu_ops.add("SLT")
    if any(inst in instructions for inst in {"sltu", "sltiu"}):
        alu_ops.add("SLTU")
    if "lui" in instructions:
        alu_ops.add("LUI")

    base = Path("templates")
    cu_template = load_template(base / "control_unit.v.j2")
    alu_template = load_template(base / "alu_control.v.j2")
    imm_template = load_template(base / "imm_gen.v.j2")
    branch_template = load_template(base / "branch_unit.v.j2")
    alu_core_template = load_template(base / "alu.v.j2")
    regfile_template = load_template(base / "register_file.v.j2")

    write_text(
        out_dir / "control_unit.v",
        render_or_fallback(
            cu_template,
            make_control_unit_fallback(),
            instructions=instructions,
            has_r_type=has_r_type,
            has_i_alu=has_i_alu,
            has_load=has_load,
            has_store=has_store,
            has_branch=has_branch,
            has_jal=has_jal,
            has_jalr=has_jalr,
            has_lui=has_lui,
            has_auipc=has_auipc,
            has_custom=has_custom,
        ),
    )

    write_text(
        out_dir / "alu_control.v",
        render_or_fallback(
            alu_template,
            make_alu_control_fallback(),
            instructions=instructions,
            has_branch=has_branch,
        ),
    )

    write_text(
        out_dir / "imm_gen.v",
        render_or_fallback(
            imm_template,
            make_imm_gen_fallback(),
            instructions=instructions,
            has_i_type=has_i_type,
            has_s_type=has_s_type,
            has_b_type=has_b_type,
            has_u_type=has_u_type,
            has_j_type=has_j_type,
        ),
    )

    write_text(
        out_dir / "branch_unit.v",
        render_or_fallback(
            branch_template,
            make_branch_unit_fallback(),
            instructions=instructions,
        ),
    )

    write_text(
        out_dir / "alu.v",
        render_or_fallback(
            alu_core_template,
            make_alu_fallback(),
            instructions=instructions,
            alu_ops=sorted(alu_ops),
        ),
    )

    write_text(
        out_dir / "register_file.v",
        render_or_fallback(
            regfile_template,
            make_register_file_fallback(),
            instructions=instructions,
            registers_read=registers_read,
            registers_written=registers_written,
            stored_registers=stored_registers,
            visible_registers=visible_registers,
        ),
    )

    program_name = infer_program_name(summary, inst_json)
    program_tb_name = f"tb_pipeline_top_{sanitize_name(program_name)}.v"
    write_text(out_dir / program_tb_name, make_program_tb(program_name))
    write_text(out_dir / "tb_pipeline_top.v", make_stable_tb())

    print("Generated:")
    print(out_dir / "control_unit.v")
    print(out_dir / "alu_control.v")
    print(out_dir / "imm_gen.v")
    print(out_dir / "branch_unit.v")
    print(out_dir / "alu.v")
    print(out_dir / "register_file.v")
    print(f"Generated {out_dir / program_tb_name}")
    print(f"Stable TB  : {out_dir / 'tb_pipeline_top.v'}")


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv

    if len(argv) != 3:
        print("Usage: python3 tools/gen_control_from_insts.py <insts.json> <outdir>")
        return 1

    try:
        inst_json = Path(argv[1])
        out_dir = Path(argv[2])
        out_dir.mkdir(parents=True, exist_ok=True)
        generate_all(inst_json, out_dir)
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())