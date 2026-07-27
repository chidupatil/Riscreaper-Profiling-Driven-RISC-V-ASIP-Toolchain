#!/usr/bin/env bash
set -e

if [ $# -lt 1 ]; then
  echo "Usage: $0 <source.c> [name] [max_steps] [opt_level]"
  echo "  opt_level: -O0 (default), -O1, -O2, -O3, or -Os"
  exit 1
fi

SRC="$1"
NAME="${2:-$(basename "$SRC" .c)}"
MAX_STEPS="${3:-20000}"
OPT_LEVEL="${4:--O0}"
OUTDIR="demo/build"
EMU_PROFILE="$OUTDIR/${NAME}_bit_profile.json"
INST_JSON="$OUTDIR/${NAME}_insts.json"
BOOTSTRAP_PROFILE="$OUTDIR/${NAME}_bootstrap_profile.json"
DEFAULT_STACK_TOP=256   # matches the original, safe, hand-written data_memory.v size

mkdir -p "$OUTDIR" generated

echo "==> Step 1: C -> ELF/DIS/BIN/MEM (+ data.mem)"
./tools/c_to_mem.sh "$SRC" "$NAME" "$OPT_LEVEL"
# c_to_mem.sh leaves a clean, pre-stub instructions.mem at $OUTDIR/$NAME.mem
# -- every pass below starts fresh from that, never from a
# previously-stubbed generated/instructions.mem, since gen_startup_stub.py
# assumes a fresh input (see that script's own comments for why: an
# earlier idempotency-guard attempt using a `//` comment marker was
# actively dangerous, since $readmemh doesn't count comment lines toward
# addressing but emulator.py's line-based parser does).

# ============================================================
# PASS 1 (bootstrap): profile with the safe default stack size,
# just to learn the real data memory footprint this program needs.
# ============================================================
echo "==> Step 2a (bootstrap pass): stack-pointer init at default depth"
cp "$OUTDIR/$NAME.mem" generated/instructions.mem
python3 tools/gen_startup_stub.py generated/instructions.mem --stack-top "$DEFAULT_STACK_TOP"

echo "==> Step 2b (bootstrap pass): generate PC + instruction/data memory at default sizes"
python3 tools/gen_pc.py generated/instructions.mem generated
python3 tools/gen_instruction_memory.py generated/instructions.mem generated "$(cat generated/pc_width.txt)"
python3 tools/gen_data_memory.py generated --depth-words 64

echo "==> Step 2c (bootstrap pass): profile"
python3 tools/emulator.py \
  generated/instructions.mem \
  generated/data.mem \
  "$BOOTSTRAP_PROFILE" \
  "$MAX_STEPS"

echo "==> Step 2d: compute the REAL data memory depth this program needs"
python3 tools/gen_data_memory.py generated --bit-profile "$BOOTSTRAP_PROFILE"
DEPTH_WORDS=$(cat generated/data_depth_words.txt)
FINAL_STACK_TOP=$((DEPTH_WORDS * 4))
echo "    Bootstrap profile shows this program needs $DEPTH_WORDS words ($FINAL_STACK_TOP bytes)"
echo "    of data memory (was always a fixed 64 words / 256 bytes before)."

# ============================================================
# PASS 2 (final): regenerate everything at the REAL, minimal sizes,
# then re-profile so every downstream trimming decision (immediate
# width, ALU width, register widths, etc.) is based on the FINAL
# addresses this program actually uses -- not the bootstrap pass's.
# ============================================================
echo "==> Step 3a (final pass): stack-pointer init at computed depth"
cp "$OUTDIR/$NAME.mem" generated/instructions.mem
python3 tools/gen_startup_stub.py generated/instructions.mem --stack-top "$FINAL_STACK_TOP"

echo "==> Step 3b (final pass): regenerate PC + instruction/data memory at final sizes"
python3 tools/gen_pc.py generated/instructions.mem generated
python3 tools/gen_instruction_memory.py generated/instructions.mem generated "$(cat generated/pc_width.txt)"
python3 tools/gen_data_memory.py generated --depth-words "$DEPTH_WORDS"

echo "==> Step 3c (final pass): re-profile with the final, consistent addresses"
python3 tools/emulator.py \
  generated/instructions.mem \
  generated/data.mem \
  "$EMU_PROFILE" \
  "$MAX_STEPS"

echo "==> Step 4: Convert emulator report to generator summary"
python3 tools/gen_emulator_summary.py \
  "$EMU_PROFILE" \
  "$INST_JSON"

echo "==> Step 5: Summary -> specialized leaf RTL"
python3 tools/gen_control_from_insts.py \
  "$INST_JSON" \
  generated

echo "==> Step 5b: Dense-encode alu_op/alu_control/mem_to_reg (overwrites control_unit.v/alu_control.v/alu.v)"
python3 tools/gen_dense_control.py \
  "$INST_JSON" \
  generated

echo "==> Step 6: Generate pipeline registers (matches Step 5b's encoding_plan.json and Step 3b's pc_width.txt)"
python3 tools/gen_pipeline_regs.py \
  "$EMU_PROFILE" \
  generated

echo "==> Step 7: Generate pipeline_top and testbenches"
python3 tools/gen_pipeline_and_tb.py \
  "$INST_JSON" \
  generated

echo "==> Step 7b: Generate a TRIMMED custom_unit.v"
# Only includes the multiplier(s) actually needed based on which
# custom_* instructions this program uses -- an earlier, static
# version always computed BOTH a signed and a separate unsigned
# ~32x32 multiply unconditionally, costing real DSP slices for
# operations the program never issues (confirmed via a real
# utilization report: ~7 DSP slices for a program using only
# custom_mul, which only ever needed one of the two). Harmless/moot
# if no custom_* instruction is used at all -- pipeline_top.v's
# has_custom logic won't instantiate this module in that case
# regardless of its content.
python3 tools/gen_custom_unit.py \
  "$INST_JSON" \
  generated

echo "==> Step 8: Apply trim-aware patching (leaf modules only)"
python3 tools/gen_trimmed_rtl.py \
  "$EMU_PROFILE" \
  generated

echo "==> Step 8b: Consolidate everything trimmed into one report"
python3 tools/gen_trim_summary.py \
  "$EMU_PROFILE" \
  "$INST_JSON" \
  generated

echo
echo "==> All RTL is generated -- nothing in generated/ needs to be"
echo "    hand-copied in anymore (custom_unit.v moved from a static,"
echo "    always-full-size file to a generated, trimmed one in Step 7b)."

echo
echo "Flow complete for $SRC:"
echo " ELF               : $OUTDIR/$NAME.elf"
echo " DIS               : $OUTDIR/$NAME.dis"
echo " MEM               : generated/instructions.mem"
echo " Data MEM          : generated/data.mem"
echo " Bootstrap profile : $BOOTSTRAP_PROFILE (pass 1, discarded after sizing)"
echo " Final bit profile : $EMU_PROFILE (pass 2, used for all trimming decisions)"
echo " Instr set         : $INST_JSON"
echo " PC width          : $(cat generated/pc_width.txt) bits"
echo " Data memory depth : $DEPTH_WORDS words ($FINAL_STACK_TOP bytes)"
echo " Pipeline top      : generated/pipeline_top.v"
echo " Stable TB         : generated/tb_pipeline_top.v"
echo " Trim report       : generated/trim_report.json"
echo " Trim SUMMARY      : generated/trim_summary.json (generated/trim_summary.txt for a readable version)"

echo
echo "This script only generates/trims RTL -- it does NOT run Vivado."
echo "Use ./tools/build_and_vivado_trimmed.sh to do both in one step, or"
echo "run ./tools/run_vivado.sh directly once you're ready to synthesize."
echo "All done."