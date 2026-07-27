#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <source.c> [output_name] [opt_level]"
  echo "  opt_level: -O0 (default), -O1, -O2, -O3, or -Os"
  exit 1
fi

SRC="$1"
NAME="${2:-$(basename "$SRC" .c)}"
OPT_LEVEL="${3:--O0}"
OUTDIR="demo/build"

mkdir -p "$OUTDIR" generated

echo "==> Compiling $SRC ($OPT_LEVEL)"
# -lgcc: this target is rv32i (base only, no M extension -- no hardware
# multiply/divide). Regular `*`/`/` on ints normally compiles to a call
# to libgcc's software routines (__mulsi3, __divsi3, __modsi3, etc.),
# but -nostdlib excludes ALL default libraries, libgcc included, which
# would otherwise make any multiply/divide fail to link at all
# ("undefined reference to __mulsi3"). -lgcc re-adds just this one
# compiler support library (not the full C standard library), which is
# the standard pattern for bare-metal/freestanding builds like this
# one. These routines are themselves implemented in plain RV32I
# (shifts, adds, branches -- exactly the instruction classes already
# proven working elsewhere in this project), and correctly land wherever
# main() actually is via the main-offset jump fix, regardless of where
# the linker places them relative to your own code.
#
# OPT_LEVEL: -O0 (the long-standing default) deliberately does the
# simplest possible thing for every statement -- every variable gets
# its own stack slot, every read/write is a real load/store even when
# a value could obviously just stay in a register, and `static inline`
# hints are ignored (functions never actually get inlined). That's why
# small, simple C code can compile to a surprising number of
# instructions -- it's not the processor design, it's this being
# debug-friendly rather than efficient. Higher levels (-O1/-O2) do
# real register allocation, dead-store elimination, and DO honor
# `static inline`, typically cutting instruction count substantially.
#
# Worth testing carefully rather than just switching by default,
# though: higher optimization can restructure code enough to exercise
# different instruction patterns than -O0 ever did (same class of
# thing that surfaced blt and lui as genuinely new, previously-untested
# paths) -- re-verify correctness on anything compiled at a higher
# level, the same way every -O0 test already has been, before trusting
# it.
riscv32-unknown-elf-gcc -march=rv32i -mabi=ilp32 \
  -nostdlib -nostartfiles -ffreestanding \
  -T tools/riscv_harvard.ld -Wl,--no-check-sections \
  "$OPT_LEVEL" "$SRC" -o "$OUTDIR/$NAME.elf" -lgcc

echo "==> Generating disassembly"
riscv32-unknown-elf-objdump -d -M no-aliases,numeric \
  "$OUTDIR/$NAME.elf" > "$OUTDIR/$NAME.dis"

echo "==> Extracting .text section"
riscv32-unknown-elf-objcopy -O binary \
  --only-section=.text \
  "$OUTDIR/$NAME.elf" "$OUTDIR/$NAME.bin"

echo "==> Locating main() -- the linker does not guarantee main() is the"
echo "    first thing in .text (e.g. a function defined earlier in the"
echo "    source file, like a helper used by main(), commonly ends up"
echo "    placed BEFORE main() in the binary). Verified: this actually"
echo "    happened for a real test program, where a helper function got"
echo "    linked first, executed with uninitialized arguments since"
echo "    main() never got a chance to set them up, then returned"
echo "    immediately (using the startup stub's ra, which expects"
echo "    main() to be what returns) -- main() never ran at all."
MAIN_ADDR=$(riscv32-unknown-elf-nm "$OUTDIR/$NAME.elf" | awk '$3 == "main" { print "0x" $1 }')
TEXT_BASE=$(riscv32-unknown-elf-objdump -h "$OUTDIR/$NAME.elf" | awk '$2 == ".text" { print "0x" $4 }')
if [ -z "$MAIN_ADDR" ]; then
  echo "ERROR: could not find a 'main' symbol in $OUTDIR/$NAME.elf -- does $SRC define main()?"
  exit 1
fi
if [ -z "$TEXT_BASE" ]; then
  echo "ERROR: could not find .text section base address in $OUTDIR/$NAME.elf"
  exit 1
fi
MAIN_OFFSET=$(( MAIN_ADDR - TEXT_BASE ))
echo "    main() is at $MAIN_ADDR, .text base is $TEXT_BASE -> offset $MAIN_OFFSET bytes into the extracted program"
echo "$MAIN_OFFSET" > "$OUTDIR/$NAME.main_offset.txt"

echo "==> Converting binary to instructions.mem"
python3 tools/bin_to_mem.py \
  "$OUTDIR/$NAME.bin" "$OUTDIR/$NAME.mem"

echo "==> Copying to project instructions.mem"
cp "$OUTDIR/$NAME.mem" generated/instructions.mem
cp "$OUTDIR/$NAME.main_offset.txt" generated/main_offset.txt

# NOTE: stack-pointer initialization (gen_startup_stub.py) is NO LONGER
# called here. It now needs to run with a --stack-top value computed
# from the ACTUAL profiled data memory depth, which requires a
# two-pass flow (profile once with a safe default, compute the real
# requirement, regenerate) -- see build_from_c_with_trimming.sh. That
# script calls gen_startup_stub.py directly, always starting fresh from
# $OUTDIR/$NAME.mem (this step's clean, pre-stub output), once per pass.

echo "==> Extracting .data/.bss sections (if present)"
# NOTE: not every program has global/static variables -- objcopy will
# simply produce nothing for a section that doesn't exist. `|| true` plus
# the explicit `touch` afterward guarantee $NAME.data.bin exists either
# way, since emulator.py (and the build scripts) always expect
# generated/data.mem to be a real, readable file, even if empty.
riscv32-unknown-elf-objcopy -O binary \
  --only-section=.data --only-section=.sdata \
  --only-section=.bss  --only-section=.sbss \
  --only-section=.rodata --only-section=.srodata \
  "$OUTDIR/$NAME.elf" "$OUTDIR/$NAME.data.bin" 2>/dev/null || true
touch "$OUTDIR/$NAME.data.bin"

echo "==> Converting data binary to data.mem"
python3 tools/bin_to_mem.py \
  "$OUTDIR/$NAME.data.bin" "$OUTDIR/$NAME.data.mem"

echo "==> Copying to project data.mem"
cp "$OUTDIR/$NAME.data.mem" generated/data.mem

echo
echo "Done."
echo "ELF:          $OUTDIR/$NAME.elf"
echo "Disassembly:  $OUTDIR/$NAME.dis"
echo "Binary:       $OUTDIR/$NAME.bin"
echo "MEM file:     $OUTDIR/$NAME.mem"
echo "Project MEM:  generated/instructions.mem"
echo "Data MEM:     $OUTDIR/$NAME.data.mem"
echo "Project data: generated/data.mem"
echo
echo "Instruction count:"
wc -l "$OUTDIR/$NAME.mem"
echo "Data word count:"
wc -l "$OUTDIR/$NAME.data.mem"

echo
echo "NOTE: global/static variables now link correctly against"
echo "data_memory.v's actual address-0-based addressing, via"
echo "tools/riscv_harvard.ld (a two-region linker script -- IMEM for"
echo ".text, DMEM for .data/.bss/.rodata -- matching this design's"
echo "Harvard-architecture memory model). This was NOT tested against"
echo "the real riscv32-unknown-elf toolchain -- verify with a program"
echo "that declares a global variable: check the disassembly shows"
echo "small, near-zero addresses for .data/.bss/.rodata accesses"
echo "(auipc/lui sequences targeting something like 0x0-0x100, not a"
echo "large absolute address), and that the program's actual behavior"
echo "is correct end to end."