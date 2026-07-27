#!/usr/bin/env bash
set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <source.c> [name]"
    exit 1
fi

SRC="$1"
NAME="${2:-$(basename "$SRC" .c)}"
OUTDIR="demo/build"
INST_JSON="$OUTDIR/${NAME}_insts.json"

mkdir -p "$OUTDIR" generated

echo "==> Compiling $SRC"

# 1. C -> ELF/DIS/BIN/MEM
./tools/c_to_mem.sh "$SRC" "$NAME"

echo "==> Generating disassembly"

# 2. DIS -> instruction summary
python3 tools/extract_insts.py \
    "$OUTDIR/$NAME.dis" \
    "$INST_JSON"

echo "==> Extracting .text section"
echo "==> Converting binary to instructions.mem"
echo "==> Copying to project instructions.mem"

# 3. Instruction summary -> specialized control/ALU + TB
python3 tools/gen_control_from_insts.py \
    "$INST_JSON" \
    generated

echo
echo "Flow complete for $SRC:"
echo "  ELF        : $OUTDIR/$NAME.elf"
echo "  DIS        : $OUTDIR/$NAME.dis"
echo "  MEM        : generated/instructions.mem"
echo "  Instr set  : $INST_JSON"
echo "  Control    : generated/control_unit.v"
echo "  ALU ctrl   : generated/alu_control.v"
echo "  IMM gen    : generated/imm_gen.v"
echo "  Branch     : generated/branch_unit.v"
echo "  ALU        : generated/alu.v"
echo "  Testbench  : generated/tb_pipeline_top_${NAME}.v"
echo "  Stable TB  : generated/tb_pipeline_top.v"
echo "  OOC rpt dir: generated/vivado_ooc"

echo "==> Running Vivado (batch mode)"
./tools/run_vivado.sh

echo "All done."