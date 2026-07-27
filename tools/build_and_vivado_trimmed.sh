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

echo "==> Build, trim, and Vivado in one shot"
# NOTE: this now calls the plain (non-redesign) trimming flow.
# build_from_c_with_trimming_redesign.sh and _redesign_v2.sh, along with
# gen_trimmed_rtl_redesign.py, gen_trimmed_rtl_redesign_v2.py, and
# gen_pipeline_regs.py, tried to give the stack pointer (and other
# "address" registers) a different data width than everything else. That
# doesn't work: a single shared ALU / register-file data bus has one
# fixed width no matter which register's value is currently flowing
# through it. It was proven to corrupt an ordinary `addi sp, sp, -32` down
# to 0 in real Icarus Verilog simulation. Recommend deleting those five
# files (or at least not calling them) to avoid accidentally using them.
./tools/build_from_c_with_trimming.sh "$SRC" "$NAME" "$MAX_STEPS" "$OPT_LEVEL"

echo "==> Running Vivado on trimmed RTL"
./tools/run_vivado.sh

echo "==> Done."