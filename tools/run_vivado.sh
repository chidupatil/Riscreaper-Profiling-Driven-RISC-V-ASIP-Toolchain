#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

NAME="${1:-}"
VIVADO_BAT='G:\\viv\\2025.2\\Vivado\\bin\\vivado.bat'

if [ ! -f "vivado/build.tcl" ]; then
  echo "ERROR: vivado/build.tcl not found"
  exit 1
fi

if [ ! -f "vivado/build_ooc.tcl" ]; then
  echo "ERROR: vivado/build_ooc.tcl not found"
  exit 1
fi

echo "==> Running Vivado normal build${NAME:+ for $NAME} (GUI mode)"
cmd.exe /c "$VIVADO_BAT -mode gui -source vivado\\build.tcl"

echo "==> Running Vivado OOC build${NAME:+ for $NAME} (batch mode)"
cmd.exe /c "$VIVADO_BAT -mode batch -source vivado\\build_ooc.tcl"

echo "Vivado runs completed successfully."