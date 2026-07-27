#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

MASK32 = 0xFFFFFFFF


def u32(x: int) -> int:
    return x & MASK32


def s32(x: int) -> int:
    x &= MASK32
    return x if x < 0x80000000 else x - 0x100000000


def sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def bit_positions(x: int, width: int = 32) -> list[int]:
    x &= (1 << width) - 1
    return [i for i in range(width) if (x >> i) & 1]


def signed_bits_required(value: int) -> int:
    if value >= 0:
        return max(1, value.bit_length() + 1)
    return max(1, (~value).bit_length() + 1)


def load_mem_words(path: Path) -> dict[int, int]:
    mem = {}
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        mem[idx * 4] = u32(int(line, 16))
    return mem


def get_byte(mem: dict[int, int], addr: int) -> int:
    word_addr = addr & ~0x3
    word = mem.get(word_addr, 0)
    shift = (addr & 0x3) * 8
    return (word >> shift) & 0xFF


def set_byte(mem: dict[int, int], addr: int, value: int) -> None:
    word_addr = addr & ~0x3
    word = mem.get(word_addr, 0)
    shift = (addr & 0x3) * 8
    mask = 0xFF << shift
    mem[word_addr] = u32((word & ~mask) | ((value & 0xFF) << shift))


def load_half(mem: dict[int, int], addr: int) -> int:
    return get_byte(mem, addr) | (get_byte(mem, addr + 1) << 8)


def store_half(mem: dict[int, int], addr: int, value: int) -> None:
    set_byte(mem, addr, value & 0xFF)
    set_byte(mem, addr + 1, (value >> 8) & 0xFF)


def load_word(mem: dict[int, int], addr: int) -> int:
    if addr & 0x3:
        return u32(
            get_byte(mem, addr)
            | (get_byte(mem, addr + 1) << 8)
            | (get_byte(mem, addr + 2) << 16)
            | (get_byte(mem, addr + 3) << 24)
        )
    return u32(mem.get(addr, 0))


def store_word(mem: dict[int, int], addr: int, value: int) -> None:
    if addr & 0x3:
        for i in range(4):
            set_byte(mem, addr + i, (value >> (8 * i)) & 0xFF)
    else:
        mem[addr] = u32(value)


# Custom opcode-0x0B (7'b0001011) instructions. Verified against the real
# custom_unit.v: dispatch is on funct3 ONLY -- funct7 is never wired into
# custom_unit, so it must not be part of the key.
#   funct3=000  MUL     -> low 32 bits of signed x signed
#   funct3=001  MULH    -> high 32 bits of signed x signed
#   funct3=010  MULHU   -> high 32 bits of unsigned x unsigned
#   funct3=011  MAC     -> RTL comment marks this a placeholder; currently
#                          wired identically to MUL, not real MAC.
#   funct3=100..111      -> no case in the RTL; custom_valid still asserts
#                          but custom_result is forced to 0 (NOT illegal --
#                          do not halt on this).
CUSTOM_TYPE = {
    0b000: "custom_mul",
    0b001: "custom_mulh",
    0b010: "custom_mulhu",
    0b011: "custom_mac",
}
CUSTOM_RESERVED = "custom_reserved"

# OPEN QUESTION -- verify against your ACTUAL control_unit.v (not the
# gen_control_from_insts.py fallback, which has no case for opcode 0001011
# and would leave reg_write=0 for custom instructions). If your real
# control_unit.v does NOT assert reg_write for opcode 0001011, custom
# instructions never commit a result in hardware, and this should be set
# to False so profiling matches real silicon instead of assuming writeback.
CUSTOM_INSTRUCTIONS_WRITE_BACK = True

ALL_MNEMONICS = {
    "add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu",
    "addi", "andi", "ori", "xori", "slti", "sltiu", "slli", "srli", "srai",
    "lb", "lh", "lw", "lbu", "lhu",
    "sb", "sh", "sw",
    "beq", "bne", "blt", "bge", "bltu", "bgeu",
    "jal", "jalr", "lui", "auipc",
} | set(CUSTOM_TYPE.values()) | {CUSTOM_RESERVED}


def decode(inst: int) -> dict:
    opcode = inst & 0x7F
    rd = (inst >> 7) & 0x1F
    funct3 = (inst >> 12) & 0x7
    rs1 = (inst >> 15) & 0x1F
    rs2 = (inst >> 20) & 0x1F
    funct7 = (inst >> 25) & 0x7F

    imm_i = sign_extend((inst >> 20) & 0xFFF, 12)
    imm_s = sign_extend((((inst >> 25) & 0x7F) << 5) | rd, 12)
    imm_b = sign_extend(
        (((inst >> 31) & 0x1) << 12)
        | (((inst >> 7) & 0x1) << 11)
        | (((inst >> 25) & 0x3F) << 5)
        | (((inst >> 8) & 0xF) << 1),
        13,
    )
    imm_u = inst & 0xFFFFF000
    imm_j = sign_extend(
        (((inst >> 31) & 0x1) << 20)
        | (((inst >> 12) & 0xFF) << 12)
        | (((inst >> 20) & 0x1) << 11)
        | (((inst >> 21) & 0x3FF) << 1),
        21,
    )

    name = "unknown"
    fmt = "unknown"

    if opcode == 0x33:
        fmt = "R"
        lut = {
            (0x0, 0x00): "add", (0x0, 0x20): "sub",
            (0x7, 0x00): "and", (0x6, 0x00): "or", (0x4, 0x00): "xor",
            (0x1, 0x00): "sll", (0x5, 0x00): "srl", (0x5, 0x20): "sra",
            (0x2, 0x00): "slt", (0x3, 0x00): "sltu",
        }
        name = lut.get((funct3, funct7), "unknown")
    elif opcode == 0x13:
        fmt = "I"
        if funct3 == 0x0: name = "addi"
        elif funct3 == 0x7: name = "andi"
        elif funct3 == 0x6: name = "ori"
        elif funct3 == 0x4: name = "xori"
        elif funct3 == 0x2: name = "slti"
        elif funct3 == 0x3: name = "sltiu"
        elif funct3 == 0x1 and funct7 == 0x00: name = "slli"
        elif funct3 == 0x5 and funct7 == 0x00: name = "srli"
        elif funct3 == 0x5 and funct7 == 0x20: name = "srai"
    elif opcode == 0x03:
        fmt = "I"
        name = {0x0: "lb", 0x1: "lh", 0x2: "lw", 0x4: "lbu", 0x5: "lhu"}.get(funct3, "unknown")
    elif opcode == 0x23:
        fmt = "S"
        name = {0x0: "sb", 0x1: "sh", 0x2: "sw"}.get(funct3, "unknown")
    elif opcode == 0x63:
        fmt = "B"
        name = {0x0: "beq", 0x1: "bne", 0x4: "blt", 0x5: "bge", 0x6: "bltu", 0x7: "bgeu"}.get(funct3, "unknown")
    elif opcode == 0x6F:
        fmt = "J"
        name = "jal"
    elif opcode == 0x67:
        fmt = "I"
        name = "jalr"
    elif opcode == 0x37:
        fmt = "U"
        name = "lui"
    elif opcode == 0x17:
        fmt = "U"
        name = "auipc"
    elif opcode == 0x0B:
        fmt = "R"
        name = CUSTOM_TYPE.get(funct3, CUSTOM_RESERVED)

    return {
        "inst": inst, "opcode": opcode, "rd": rd, "rs1": rs1, "rs2": rs2,
        "funct3": funct3, "funct7": funct7,
        "imm_i": imm_i, "imm_s": imm_s, "imm_b": imm_b, "imm_u": imm_u, "imm_j": imm_j,
        "name": name, "format": fmt,
    }


class BitProfiler:
    def __init__(self):
        self.instruction_counts = Counter()
        self.pc_bits = set()
        self.reg_read_bits = defaultdict(set)
        self.reg_write_bits = defaultdict(set)
        self.signed_reg_write_ranges: dict[int, list[int]] = {}
        self.alu_result_bits = set()
        self.signed_alu_range: list[int] | None = None
        # Separate from signed_alu_range/register-write ranges: those
        # track a register's or the ALU's value across the WHOLE
        # program, which isn't precise for "how wide does custom_unit's
        # multiplier actually need to be" -- a register could hold a
        # large value at some other point in the program and still only
        # ever pass small values into a custom_mul call specifically.
        # This tracks exactly the operand values seen AT custom
        # instruction call sites, nothing else.
        self.custom_operand_range: list[int] | None = None
        # Same reasoning as custom_operand_range: the general
        # alu_signed_range tracks the ALU's value across EVERY
        # instruction in the program combined, which isn't precise for
        # "how wide does custom_unit's RESULT actually need to be" --
        # some other instruction elsewhere in the program could need
        # the full 32 bits while custom_mul's own result never exceeds
        # a handful of bits. This tracks exactly the result value
        # produced AT custom instruction call sites, nothing else.
        self.custom_result_range: list[int] | None = None
        self.mem_addr_bits = set()
        self.min_mem_addr: int | None = None
        self.max_mem_addr: int | None = None
        self.mem_read_bits = set()
        self.mem_write_bits = set()
        self.signed_imm_ranges: dict[str, list[int]] = {}
        self.imm_u_bits = set()
        self.max_shamt_seen = 0
        self.toggled_result_bits = set()
        self.max_unsigned_value_seen = 0
        self.min_signed_value_seen = 0
        self.max_signed_value_seen = 0
        self.executed_pcs = []
        self.halted_reason = "max_steps"
        self.steps = 0
        self.last_alu_result = None
        self.registers_read = set()
        self.registers_written = set()

    def observe_value(self, value: int):
        u = u32(value)
        s = s32(value)
        self.max_unsigned_value_seen = max(self.max_unsigned_value_seen, u)
        self.min_signed_value_seen = min(self.min_signed_value_seen, s)
        self.max_signed_value_seen = max(self.max_signed_value_seen, s)

    def observe_reg_read(self, reg: int, value: int):
        self.registers_read.add(reg)
        for b in bit_positions(value):
            self.reg_read_bits[reg].add(b)
        self.observe_value(value)

    def observe_reg_write(self, reg: int, value: int):
        self.registers_written.add(reg)
        for b in bit_positions(value):
            self.reg_write_bits[reg].add(b)
        self.observe_value(value)
        # Track the actual signed value range too (not just bit positions,
        # which -- same flaw as immediates before this was fixed there --
        # both inflate to ~32 bits for any negative value AND go entirely
        # invisible for a register whose value happens to be exactly 0
        # every time it's written, undercounting real per-register width).
        sval = s32(value)
        lo, hi = self.signed_reg_write_ranges.get(reg, (sval, sval))
        self.signed_reg_write_ranges[reg] = [min(lo, sval), max(hi, sval)]

    def observe_pc(self, pc: int):
        for b in bit_positions(pc):
            self.pc_bits.add(b)
        self.executed_pcs.append(u32(pc))

    def observe_mem_addr(self, addr: int):
        addr = u32(addr)
        for b in bit_positions(addr):
            self.mem_addr_bits.add(b)
        # Precise min/max, not reconstructed from bit positions -- the
        # bit-position union can only ever bound the true range from
        # above (e.g. a single address like 252 = 0b11111100 sets bits
        # 2-7, and reconstructing "2**8-1=255" from that is a real but
        # loose bound). Depth-sizing for data_memory.v needs the tight
        # bound, since it directly determines how much BRAM gets
        # allocated -- see gen_data_memory.py.
        if self.min_mem_addr is None or addr < self.min_mem_addr:
            self.min_mem_addr = addr
        if self.max_mem_addr is None or addr > self.max_mem_addr:
            self.max_mem_addr = addr

    def observe_imm(self, imm: int, kind: str):
        if kind == "imm_u":
            self.imm_u_bits |= set(bit_positions(imm))
        elif kind == "shamt":
            self.max_shamt_seen = max(self.max_shamt_seen, imm)
        else:
            lo, hi = self.signed_imm_ranges.get(kind, (imm, imm))
            self.signed_imm_ranges[kind] = [min(lo, imm), max(hi, imm)]

    def observe_alu(self, value: int):
        bits = set(bit_positions(value))
        self.alu_result_bits |= bits
        if self.last_alu_result is not None:
            self.toggled_result_bits |= set(bit_positions(self.last_alu_result ^ u32(value)))
        self.last_alu_result = u32(value)
        # Same flaw as immediates/register-writes before those were
        # fixed: bit_positions() on a sign-extended negative ALU result
        # (e.g. any subtraction that goes negative, any stack-pointer
        # arithmetic) lights up nearly all 32 bits regardless of the
        # value's actual magnitude, so alu_required_width stayed
        # permanently inflated to ~32 for almost any real program. Track
        # the actual signed range instead and derive width from that.
        sval = s32(value)
        if self.signed_alu_range is None:
            self.signed_alu_range = [sval, sval]
        else:
            self.signed_alu_range[0] = min(self.signed_alu_range[0], sval)
            self.signed_alu_range[1] = max(self.signed_alu_range[1], sval)

    def observe_custom_operands(self, rs1v: int, rs2v: int):
        """Tracks the actual signed value range of BOTH operands at a
        custom instruction call site, combined into one range (not two
        separate ones) since custom_unit.v's multiplier treats rs1_val
        and rs2_val symmetrically -- whichever one needs more bits sets
        the real requirement for both."""
        for value in (rs1v, rs2v):
            sval = s32(value)
            if self.custom_operand_range is None:
                self.custom_operand_range = [sval, sval]
            else:
                self.custom_operand_range[0] = min(self.custom_operand_range[0], sval)
                self.custom_operand_range[1] = max(self.custom_operand_range[1], sval)

    def observe_custom_result(self, value: int):
        """Tracks the actual signed value range of custom_unit's own
        computed RESULT specifically -- separate from custom_operand_range
        (that's the inputs) and separate from the general alu_signed_range
        (that's every instruction in the program combined)."""
        sval = s32(value)
        if self.custom_result_range is None:
            self.custom_result_range = [sval, sval]
        else:
            self.custom_result_range[0] = min(self.custom_result_range[0], sval)
            self.custom_result_range[1] = max(self.custom_result_range[1], sval)

    def summary(self, all_known_mnemonics: set[str] | None = None) -> dict:
        reg_write_width = {
            f"x{reg}": max(signed_bits_required(lo), signed_bits_required(hi))
            for reg, (lo, hi) in sorted(self.signed_reg_write_ranges.items())
        }
        imm_widths_by_kind = {
            kind: {
                "min_seen": lo,
                "max_seen": hi,
                "required_bits": max(signed_bits_required(lo), signed_bits_required(hi)),
            }
            for kind, (lo, hi) in sorted(self.signed_imm_ranges.items())
        }
        imm_u_width = max(self.imm_u_bits) + 1 if self.imm_u_bits else 1
        shamt_width = max(1, self.max_shamt_seen.bit_length())
        overall_imm_width = max(
            [d["required_bits"] for d in imm_widths_by_kind.values()] + [imm_u_width, shamt_width, 1]
        )
        # IMPORTANT: derive touched_regs from the flat registers_read /
        # registers_written sets, NOT from reg_read_bits/reg_write_bits
        # keys. The bit-dicts only gain an entry when bit_positions(value)
        # is non-empty, so a register genuinely read/written while holding
        # value 0 (e.g. `ra`/`s0` read during a function prologue before
        # they're ever set) silently disappears from that view -- which
        # then undercounts register_index_required_width and would cause
        # gen_trimmed_rtl.py to trim the register address field too
        # narrow for that register.
        touched_regs = self.registers_read | self.registers_written
        max_reg_index = max(touched_regs) if touched_regs else 0
        used_mnemonics = set(self.instruction_counts.keys())
        unused = sorted((all_known_mnemonics or set()) - used_mnemonics)

        if self.signed_alu_range is not None:
            alu_lo, alu_hi = self.signed_alu_range
            alu_width = max(signed_bits_required(alu_lo), signed_bits_required(alu_hi))
        else:
            alu_width = 1

        if self.custom_operand_range is not None:
            cust_lo, cust_hi = self.custom_operand_range
            custom_operand_width = max(signed_bits_required(cust_lo), signed_bits_required(cust_hi))
        else:
            # No custom_* instruction was ever used -- 32 is a safe
            # default (matches the original, untrimmed port width) and
            # is moot anyway, since pipeline_top.v's has_custom logic
            # won't instantiate custom_unit at all in that case.
            custom_operand_width = 32

        if self.custom_result_range is not None:
            res_lo, res_hi = self.custom_result_range
            custom_result_width = max(signed_bits_required(res_lo), signed_bits_required(res_hi))
        else:
            custom_result_width = 32

        return {
            "steps": self.steps,
            "halted_reason": self.halted_reason,
            "instructions_executed": dict(self.instruction_counts),
            "instructions_used": sorted(used_mnemonics),
            "unused_instructions": unused,
            "executed_pc_count": len(self.executed_pcs),
            "pc_bits_used": sorted(self.pc_bits),
            "pc_required_width": max(self.pc_bits) + 1 if self.pc_bits else 1,
            "registers_used": sorted(touched_regs),
            "registers_read": sorted(self.registers_read),
            "registers_written": sorted(self.registers_written),
            "register_index_required_width": max(1, max_reg_index.bit_length()),
            "register_read_bits_used": {f"x{k}": sorted(v) for k, v in sorted(self.reg_read_bits.items())},
            "register_write_bits_used": {f"x{k}": sorted(v) for k, v in sorted(self.reg_write_bits.items())},
            "register_write_required_width": reg_write_width,
            "alu_result_bits_used": sorted(self.alu_result_bits),
            "alu_required_width": alu_width,
            "alu_signed_range": self.signed_alu_range,
            "alu_toggled_bits": sorted(self.toggled_result_bits),
            "memory_address_bits_used": sorted(self.mem_addr_bits),
            "memory_address_width": max(self.mem_addr_bits) + 1 if self.mem_addr_bits else 1,
            "memory_min_addr": self.min_mem_addr,
            "memory_max_addr": self.max_mem_addr,
            "memory_read_bits_used": sorted(self.mem_read_bits),
            "memory_write_bits_used": sorted(self.mem_write_bits),
            "immediate_widths_by_kind": imm_widths_by_kind,
            "immediate_u_type_required_width": imm_u_width,
            "shamt_required_width": shamt_width,
            "max_unsigned_value_seen": self.max_unsigned_value_seen,
            "min_signed_value_seen": self.min_signed_value_seen,
            "max_signed_value_seen": self.max_signed_value_seen,
            "custom_decode_map": {f"funct3_{k:03b}": v for k, v in sorted(CUSTOM_TYPE.items())},
            "custom_operand_required_width": custom_operand_width,
            "custom_operand_signed_range": self.custom_operand_range,
            "custom_result_required_width": custom_result_width,
            "custom_result_signed_range": self.custom_result_range,
            "recommended_trim": {
                "pc_width": max(self.pc_bits) + 1 if self.pc_bits else 1,
                "alu_width": alu_width,
                "imm_width": overall_imm_width,
                "data_addr_width": max(self.mem_addr_bits) + 1 if self.mem_addr_bits else 1,
                "register_index_width": max(1, max_reg_index.bit_length()),
                "custom_operand_width": custom_operand_width,
                "custom_result_width": custom_result_width,
            },
        }


class RV32IEmulator:
    def __init__(self, imem: dict[int, int], dmem: dict[int, int] | None = None):
        self.imem = dict(imem)
        self.dmem = dict(dmem or {})
        self.regs = [0] * 32
        self.pc = 0
        self.prof = BitProfiler()

    def read_reg(self, idx: int) -> int:
        return 0 if idx == 0 else self.regs[idx]

    def write_reg(self, idx: int, value: int):
        if idx != 0:
            self.regs[idx] = u32(value)
            self.prof.observe_reg_write(idx, value)
        self.regs[0] = 0

    def step(self) -> bool:
        inst = self.imem.get(self.pc)
        if inst is None:
            self.prof.halted_reason = "pc_not_mapped"
            return False

        d = decode(inst)
        name = d["name"]
        rs1v = self.read_reg(d["rs1"])
        rs2v = self.read_reg(d["rs2"])

        self.prof.steps += 1
        self.prof.instruction_counts[name] += 1
        self.prof.observe_pc(self.pc)

        fmt = d["format"]
        uses_rs1 = fmt in ("R", "I", "S", "B")
        uses_rs2 = fmt in ("R", "S", "B")
        if uses_rs1 and d["rs1"]:
            self.prof.observe_reg_read(d["rs1"], rs1v)
        if uses_rs2 and d["rs2"]:
            self.prof.observe_reg_read(d["rs2"], rs2v)

        next_pc = u32(self.pc + 4)
        alu_result = None

        if name in {"slli", "srli", "srai"}:
            self.prof.observe_imm(d["rs2"], "shamt")
        elif name in {"addi", "andi", "ori", "xori", "slti", "sltiu", "lb", "lh", "lw", "lbu", "lhu", "jalr"}:
            self.prof.observe_imm(d["imm_i"], "imm_i")
        elif name in {"sb", "sh", "sw"}:
            self.prof.observe_imm(d["imm_s"], "imm_s")
        elif name in {"beq", "bne", "blt", "bge", "bltu", "bgeu"}:
            self.prof.observe_imm(d["imm_b"], "branch")
        elif name in {"jal"}:
            self.prof.observe_imm(d["imm_j"], "jump")
        elif name in {"lui", "auipc"}:
            self.prof.observe_imm(d["imm_u"], "imm_u")

        if name == "add":
            alu_result = u32(rs1v + rs2v)
            self.write_reg(d["rd"], alu_result)
        elif name == "sub":
            alu_result = u32(rs1v - rs2v)
            self.write_reg(d["rd"], alu_result)
        elif name == "and":
            alu_result = u32(rs1v & rs2v)
            self.write_reg(d["rd"], alu_result)
        elif name == "or":
            alu_result = u32(rs1v | rs2v)
            self.write_reg(d["rd"], alu_result)
        elif name == "xor":
            alu_result = u32(rs1v ^ rs2v)
            self.write_reg(d["rd"], alu_result)
        elif name == "sll":
            alu_result = u32(rs1v << (rs2v & 0x1F))
            self.write_reg(d["rd"], alu_result)
        elif name == "srl":
            alu_result = u32(rs1v >> (rs2v & 0x1F))
            self.write_reg(d["rd"], alu_result)
        elif name == "sra":
            alu_result = u32(s32(rs1v) >> (rs2v & 0x1F))
            self.write_reg(d["rd"], alu_result)
        elif name == "slt":
            alu_result = 1 if s32(rs1v) < s32(rs2v) else 0
            self.write_reg(d["rd"], alu_result)
        elif name == "sltu":
            alu_result = 1 if rs1v < rs2v else 0
            self.write_reg(d["rd"], alu_result)
        elif name == "addi":
            alu_result = u32(rs1v + d["imm_i"])
            self.write_reg(d["rd"], alu_result)
        elif name == "andi":
            alu_result = u32(rs1v & d["imm_i"])
            self.write_reg(d["rd"], alu_result)
        elif name == "ori":
            alu_result = u32(rs1v | d["imm_i"])
            self.write_reg(d["rd"], alu_result)
        elif name == "xori":
            alu_result = u32(rs1v ^ d["imm_i"])
            self.write_reg(d["rd"], alu_result)
        elif name == "slti":
            alu_result = 1 if s32(rs1v) < d["imm_i"] else 0
            self.write_reg(d["rd"], alu_result)
        elif name == "sltiu":
            alu_result = 1 if rs1v < u32(d["imm_i"]) else 0
            self.write_reg(d["rd"], alu_result)
        elif name == "slli":
            alu_result = u32(rs1v << d["rs2"])
            self.write_reg(d["rd"], alu_result)
        elif name == "srli":
            alu_result = u32(rs1v >> d["rs2"])
            self.write_reg(d["rd"], alu_result)
        elif name == "srai":
            alu_result = u32(s32(rs1v) >> d["rs2"])
            self.write_reg(d["rd"], alu_result)
        elif name in {"lb", "lh", "lw", "lbu", "lhu"}:
            addr = u32(rs1v + d["imm_i"])
            self.prof.observe_mem_addr(addr)
            if name == "lb":
                val = sign_extend(get_byte(self.dmem, addr), 8)
            elif name == "lbu":
                val = get_byte(self.dmem, addr)
            elif name == "lh":
                val = sign_extend(load_half(self.dmem, addr), 16)
            elif name == "lhu":
                val = load_half(self.dmem, addr)
            else:
                val = load_word(self.dmem, addr)
            for b in bit_positions(val):
                self.prof.mem_read_bits.add(b)
            alu_result = addr
            self.write_reg(d["rd"], val)
        elif name in {"sb", "sh", "sw"}:
            addr = u32(rs1v + d["imm_s"])
            self.prof.observe_mem_addr(addr)
            if name == "sb":
                set_byte(self.dmem, addr, rs2v)
                written = rs2v & 0xFF
            elif name == "sh":
                store_half(self.dmem, addr, rs2v)
                written = rs2v & 0xFFFF
            else:
                store_word(self.dmem, addr, rs2v)
                written = rs2v
            for b in bit_positions(written):
                self.prof.mem_write_bits.add(b)
            alu_result = addr
        elif name == "beq":
            alu_result = u32(rs1v - rs2v)
            if rs1v == rs2v:
                next_pc = u32(self.pc + d["imm_b"])
        elif name == "bne":
            alu_result = u32(rs1v - rs2v)
            if rs1v != rs2v:
                next_pc = u32(self.pc + d["imm_b"])
        elif name == "blt":
            alu_result = u32(rs1v - rs2v)
            if s32(rs1v) < s32(rs2v):
                next_pc = u32(self.pc + d["imm_b"])
        elif name == "bge":
            alu_result = u32(rs1v - rs2v)
            if s32(rs1v) >= s32(rs2v):
                next_pc = u32(self.pc + d["imm_b"])
        elif name == "bltu":
            alu_result = u32(rs1v - rs2v)
            if rs1v < rs2v:
                next_pc = u32(self.pc + d["imm_b"])
        elif name == "bgeu":
            alu_result = u32(rs1v - rs2v)
            if rs1v >= rs2v:
                next_pc = u32(self.pc + d["imm_b"])
        elif name == "jal":
            self.write_reg(d["rd"], self.pc + 4)
            next_pc = u32(self.pc + d["imm_j"])
            alu_result = next_pc
        elif name == "jalr":
            self.write_reg(d["rd"], self.pc + 4)
            next_pc = u32((rs1v + d["imm_i"]) & ~1)
            alu_result = next_pc
        elif name == "lui":
            alu_result = u32(d["imm_u"])
            self.write_reg(d["rd"], alu_result)
        elif name == "auipc":
            alu_result = u32(self.pc + d["imm_u"])
            self.write_reg(d["rd"], alu_result)
        elif name == "custom_mul":
            # Low 32 bits of a 32x32 product are identical whether operands
            # are signed or unsigned (two's-complement wraparound).
            self.prof.observe_custom_operands(rs1v, rs2v)
            alu_result = u32(rs1v * rs2v)
            self.prof.observe_custom_result(alu_result)
            if CUSTOM_INSTRUCTIONS_WRITE_BACK:
                self.write_reg(d["rd"], alu_result)
        elif name == "custom_mulh":
            self.prof.observe_custom_operands(rs1v, rs2v)
            full = s32(rs1v) * s32(rs2v)   # arbitrary-precision signed product
            alu_result = u32(full >> 32)   # arithmetic shift == two's-complement high word
            self.prof.observe_custom_result(alu_result)
            if CUSTOM_INSTRUCTIONS_WRITE_BACK:
                self.write_reg(d["rd"], alu_result)
        elif name == "custom_mulhu":
            self.prof.observe_custom_operands(rs1v, rs2v)
            full = rs1v * rs2v             # both already unsigned 0..2^32-1
            alu_result = u32(full >> 32)
            self.prof.observe_custom_result(alu_result)
            if CUSTOM_INSTRUCTIONS_WRITE_BACK:
                self.write_reg(d["rd"], alu_result)
        elif name == "custom_mac":
            # RTL comment: "MAC placeholder" -- currently wired identically
            # to MUL, not real multiply-accumulate. Mirror that exactly.
            self.prof.observe_custom_operands(rs1v, rs2v)
            alu_result = u32(rs1v * rs2v)
            self.prof.observe_custom_result(alu_result)
            if CUSTOM_INSTRUCTIONS_WRITE_BACK:
                self.write_reg(d["rd"], alu_result)
        elif name == CUSTOM_RESERVED:
            # funct3 100-111: no case in custom_unit.v, result forced to 0
            # but custom_valid still asserts -- not illegal, don't halt.
            alu_result = 0
            if CUSTOM_INSTRUCTIONS_WRITE_BACK:
                self.write_reg(d["rd"], alu_result)
        else:
            self.prof.halted_reason = f"unsupported_instruction_0x{inst:08x}"
            return False

        if alu_result is not None:
            self.prof.observe_alu(alu_result)

        self.pc = next_pc
        self.regs[0] = 0
        return True

    def run(self, max_steps: int = 10000) -> dict:
        while self.prof.steps < max_steps:
            if not self.step():
                break
        else:
            self.prof.halted_reason = "max_steps"
        return self.prof.summary(all_known_mnemonics=ALL_MNEMONICS)


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) < 2 or len(argv) > 5:
        print("Usage: python3 emulator.py <instructions.mem> [data.mem] [output.json] [max_steps]")
        return 1

    inst_path = Path(argv[1])
    data_path = Path(argv[2]) if len(argv) >= 3 and argv[2] != "-" else None
    out_path = Path(argv[3]) if len(argv) >= 4 and argv[3] != "-" else Path("bit_profile.json")
    max_steps = int(argv[4]) if len(argv) >= 5 else 10000

    imem = load_mem_words(inst_path)
    if data_path and not data_path.exists():
        # Not every C program has a .data/.bss section (e.g. one with no
        # global/static variables), and some callers may not have created
        # this file at all -- treat "path given but doesn't exist" the
        # same as "no data file", rather than crashing the whole profiling
        # run over an empty data segment.
        print(f"NOTE: data file '{data_path}' not found -- treating data memory as empty.", file=sys.stderr)
        dmem = {}
    else:
        dmem = load_mem_words(data_path) if data_path else {}

    emu = RV32IEmulator(imem, dmem)
    report = emu.run(max_steps=max_steps)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Wrote bit-trimming profile to {out_path}")
    print(f"Steps: {report['steps']}")
    print(f"Halt:  {report['halted_reason']}")
    print(f"Instructions used: {sorted(report['instructions_executed'].items())}")
    print(f"Unused instructions ({len(report['unused_instructions'])}): {report['unused_instructions']}")
    print(f"Registers touched: {report['registers_used']}")
    print(f"Recommended trim: {report['recommended_trim']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())