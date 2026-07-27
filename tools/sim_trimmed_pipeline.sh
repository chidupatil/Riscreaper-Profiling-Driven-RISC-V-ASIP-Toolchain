#!/usr/bin/env bash
set -e

TOP_TB="generated/tb_pipeline_top.v"
OUTDIR="generated/sim"
mkdir -p "$OUTDIR"

FILES=(
  generated/control_unit.v
  generated/alu_control.v
  generated/imm_gen.v
  generated/branch_unit.v
  generated/alu.v
  generated/register_file.v
  generated/if_id_reg.v
  generated/id_ex_reg.v
  generated/ex_mem_reg.v
  generated/mem_wb_reg.v
  generated/pipeline_top.v
  "$TOP_TB"
)

for f in "${FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo "Missing required file: $f"
    exit 1
  fi
done

if ! command -v iverilog >/dev/null 2>&1; then
  echo "iverilog not found. Install it first, e.g. sudo apt-get install iverilog"
  exit 1
fi

echo "==> Compiling with Icarus Verilog"
iverilog -g2012 -o "$OUTDIR/pipeline_sim.out" "${FILES[@]}"

echo "==> Running simulation"
vvp "$OUTDIR/pipeline_sim.out" | tee "$OUTDIR/sim.log"

echo "==> Width sanity grep"
grep -n "\[6:0\]\|\[8:0\]\|\[3:0\]" generated/if_id_reg.v generated/id_ex_reg.v generated/ex_mem_reg.v generated/mem_wb_reg.v generated/pipeline_top.v | tee "$OUTDIR/widths.log"

echo "Simulation artifacts:"
echo "  $OUTDIR/pipeline_sim.out"
echo "  $OUTDIR/sim.log"
echo "  $OUTDIR/widths.log"
