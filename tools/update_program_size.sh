#!/usr/bin/env bash
set -e

MEM_FILE="${1:-instructions.mem}"
RTL_FILE="${2:-instruction_memory.v}"

COUNT=$(wc -l < "$MEM_FILE")
echo "Updating PROGRAM_SIZE to $COUNT in $RTL_FILE"

sed -i -E "s/(parameter[[:space:]]+PROGRAM_SIZE[[:space:]]*=[[:space:]]*)[0-9]+/\1$COUNT/" "$RTL_FILE"

echo "Updated successfully."
