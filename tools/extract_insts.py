from pathlib import Path
import re
import sys
import json

if len(sys.argv) != 3:
    print("Usage: python3 tools/extract_insts.py <input.dis> <output.json>")
    sys.exit(1)

inf = Path(sys.argv[1]).read_text().splitlines()

mnems = set()
registers_read = set()
registers_written = set()

inst_re = re.compile(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z.]+)\s*(.*)$')
reg_re = re.compile(r'\bx([0-9]|[12][0-9]|3[01])\b')

branch_set = {"beq", "bne", "blt", "bge", "bltu", "bgeu"}
load_set   = {"lb", "lh", "lw", "lbu", "lhu"}
store_set  = {"sb", "sh", "sw"}
i_alu_set  = {"addi", "andi", "ori", "xori", "slti", "sltiu", "slli", "srli", "srai"}
r_type_set = {"add", "sub", "and", "or", "xor", "sll", "srl", "sra", "slt", "sltu"}
u_set      = {"lui", "auipc"}
j_set      = {"jal"}
jalr_set   = {"jalr"}

for line in inf:
    m = inst_re.match(line)
    if not m:
        continue

    mn = m.group(1)
    ops = m.group(2).strip()
    mnems.add(mn)

    regs = [int(x) for x in reg_re.findall(ops)]

    if mn in r_type_set:
        if len(regs) >= 3:
            registers_written.add(regs[0])
            registers_read.add(regs[1])
            registers_read.add(regs[2])

    elif mn in i_alu_set:
        if len(regs) >= 2:
            registers_written.add(regs[0])
            registers_read.add(regs[1])

    elif mn in load_set:
        if len(regs) >= 2:
            registers_written.add(regs[0])
            registers_read.add(regs[1])

    elif mn in store_set:
        if len(regs) >= 2:
            registers_read.add(regs[0])
            registers_read.add(regs[1])

    elif mn in branch_set:
        if len(regs) >= 2:
            registers_read.add(regs[0])
            registers_read.add(regs[1])

    elif mn in u_set:
        if len(regs) >= 1:
            registers_written.add(regs[0])

    elif mn in j_set:
        if len(regs) >= 1:
            registers_written.add(regs[0])

    elif mn in jalr_set:
        if len(regs) >= 2:
            registers_written.add(regs[0])
            registers_read.add(regs[1])

    elif mn == "ret":
        registers_read.add(1)

    elif mn == "j":
        pass

    elif mn == "jr":
        if len(regs) >= 1:
            registers_read.add(regs[0])

    elif mn == "mv":
        if len(regs) >= 2:
            registers_written.add(regs[0])
            registers_read.add(regs[1])

    elif mn == "li":
        if len(regs) >= 1:
            registers_written.add(regs[0])

out = {
    "instructions_used": sorted(mnems),
    "registers_read": sorted(registers_read),
    "registers_written": sorted(registers_written),
}

Path(sys.argv[2]).write_text(json.dumps(out, indent=2))
print("Found", len(mnems), "unique instructions")
print("Registers read:", sorted(registers_read))
print("Registers written:", sorted(registers_written))