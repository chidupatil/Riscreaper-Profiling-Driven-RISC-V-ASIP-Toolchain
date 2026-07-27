import json
from pathlib import Path

instr_path = Path("build/instructions.json")
out_path = Path("build/feature_map.json")

used = json.loads(instr_path.read_text())["used_instructions"]

features = {
    "has_imm_i": False,
    "has_imm_s": False,
    "has_imm_b": False,
    "has_imm_j": False,
    "has_regwrite": False,
    "has_memread": False,
    "has_memwrite": False,
    "has_branch": False,
    "has_jump": False,
    "has_custom": False
}

alu_ops = {
    "ADD": False,
    "SUB": False,
    "AND": False,
    "OR": False,
    "XOR": False,
    "SLT": False
}

for instr in used:
    if instr == "addi":
        features["has_imm_i"] = True
        features["has_regwrite"] = True
        alu_ops["ADD"] = True

    elif instr == "add":
        features["has_regwrite"] = True
        alu_ops["ADD"] = True

    elif instr == "sub":
        features["has_regwrite"] = True
        alu_ops["SUB"] = True

    elif instr == "lw":
        features["has_imm_i"] = True
        features["has_regwrite"] = True
        features["has_memread"] = True
        alu_ops["ADD"] = True

    elif instr == "sw":
        features["has_imm_s"] = True
        features["has_memwrite"] = True
        alu_ops["ADD"] = True

    elif instr in ["beq", "blt"]:
        features["has_imm_b"] = True
        features["has_branch"] = True

    elif instr == "jal":
        features["has_imm_j"] = True
        features["has_jump"] = True
        features["has_regwrite"] = True

    elif instr == "custom_mac":
        features["has_custom"] = True
        features["has_regwrite"] = True

result = {
    "used_instructions": used,
    "features": features,
    "alu_ops": alu_ops
}

out_path.write_text(json.dumps(result, indent=2))
print(f"Wrote {out_path}")
print(json.dumps(result, indent=2))
