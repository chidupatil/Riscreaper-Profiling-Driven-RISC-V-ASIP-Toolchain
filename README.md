# RISCREAPER

A profiling-driven RISC-V ASIP (Application-Specific Instruction Processor)
toolchain. Give it a C program, and it profiles the program's *actual*
runtime behavior, then generates a custom 5-stage pipelined RV32I processor
trimmed to exactly what that program needs — narrower buses, fewer
physically-stored registers, unused instruction logic removed entirely, and
optional pipeline modules only built when the program actually triggers
them.

```
██████╗ ██╗███████╗ ██████╗██████╗ ███████╗ █████╗ ██████╗ ███████╗██████╗
██╔══██╗██║██╔════╝██╔════╝██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗
██████╔╝██║███████╗██║     ██████╔╝█████╗  ███████║██████╔╝█████╗  ██████╔╝
██╔══██╗██║╚════██║██║     ██╔══██╗██╔══╝  ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗
██║  ██║██║███████║╚██████╗██║  ██║███████╗██║  ██║██║     ███████╗██║  ██║
╚═╝  ╚═╝╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
```

## Why

A general-purpose processor has to support every instruction, every
register, full-width datapaths — all the time, because it doesn't know in
advance what program will run on it. In an embedded/ASIP context, you
usually *do* know the program ahead of time. This toolchain asks: if you
know exactly what a program needs, why build hardware for the rest?

## How it works

1. **Compile** — the C program compiles to RV32I machine code via a real
   RISC-V cross-compiler, targeting bare metal (no OS, `-nostdlib`).
2. **Profile** — a custom RV32I emulator (Python) actually *executes* the
   compiled program and records everything: which instructions run (and
   which never do), the real signed value range of every register, how
   many bits the ALU/immediates/PC/memory ever actually need, which memory
   addresses get touched. This is dynamic profiling, not static analysis.
3. **Trim** — using that profile, the toolchain regenerates the
   processor's RTL from scratch, specific to this one program.
4. **Synthesize & verify** — the generated RTL goes through Xilinx Vivado
   (targeting a Digilent Basys3, `xc7a35tcpg236-1`) for synthesis,
   implementation, timing analysis, and post-synthesis functional
   simulation against real hardware primitives.

## What actually gets trimmed

| Component | Trimming applied | Safety mechanism |
|---|---|---|
| Program counter | Narrowed to the real address range used | Bit-position tracking of every executed PC |
| ALU | Port stays 32-bit; internal significant bits narrowed | Signed-range tracking (not just bit-union — see below) |
| Immediates | Port stays 32-bit; internal significant bits narrowed | Signed-range tracking per immediate kind (I/S/B/J/U) |
| Register file | Only registers the program touches are physically stored; each sized to its own value range | Per-register signed-range tracking |
| Data memory (depth) | Sized to the real address range used, not a fixed 64 words | Stack-top-relative depth computation |
| Data memory (word width) | Internal word storage narrowed to the widest value ever stored *anywhere* in the array | Only applied if the program never uses byte/halfword access (`lb/lh/lbu/lhu/sb/sh`) at all — those need the full 32-bit word structure at every address, so this is a global, program-wide safety check, not a per-address one |
| Instruction set | Unused instructions get **zero logic** — not disabled, structurally absent from `control_unit.v`/`alu_control.v` | Profiled instruction-usage set |
| `branch_unit` | Only instantiated if the program has any branch instruction; each of the six branch types (`beq/bne/blt/bge/bltu/bgeu`) is also independently included only if that specific one is used | Profiled instruction-usage set |
| `hazard_unit` / `flush_unit` | Split into two independent modules — load-use stall detection and jump/branch flush logic are separate, each only instantiated if its own trigger condition is present | Previously bundled as one module that fired on almost every program (since nearly every function ends in a `jalr` return) regardless of whether it had a single load |
| `custom_unit` | Only instantiated if the program issues a `custom_*` instruction; only includes the specific multiplier(s) the program uses; operand and result widths independently narrowed to profiled actual values | Separate operand-range and result-range tracking, specific to custom-instruction call sites (not the general ALU/register ranges) |

**A note on why signed-range tracking matters**: an earlier, simpler
approach tracked *bit positions* ever set across all observed values.
That approach has a real flaw — a single negative value (or any value with
a high bit set) inflates the tracked width to ~32 bits regardless of every
other value's actual magnitude, silently defeating narrowing for almost
any real program (loop counters, sentinels, and ordinary arithmetic
routinely go negative at some point). Every width computation in this
project tracks actual signed min/max ranges instead.

## Custom instructions

A dedicated execution unit off the main pipeline supports genuinely custom,
application-specific instructions under opcode `0x0B`, disambiguated by
`funct3`:

| `funct3` | Name | Operation |
|---|---|---|
| `000` | `custom_mul` | Low 32 bits of `rs1 * rs2` |
| `001` | `custom_mulh` | High 32 bits of signed `rs1 * rs2` |
| `010` | `custom_mulhu` | High 32 bits of unsigned `rs1 * rs2` |
| `011` | `custom_mac` | Placeholder, currently wired identically to `custom_mul` |

Example usage from C:

```c
static inline unsigned int custom_mul(unsigned int a, unsigned int b) {
    unsigned int result;
    asm volatile (".insn r 0x0B, 0, 0, %0, %1, %2"
                  : "=r"(result)
                  : "r"(a), "r"(b));
    return result;
}
```

## Measured results

These are real, verified numbers from this project — not projections:

- **`custom_unit` DSP usage**: an earlier version ran two independent
  multipliers (signed + unsigned) unconditionally, costing ~7 DSP48
  slices regardless of which operation a program used. Trimmed to
  include only the multiplier actually needed (→ ~3 DSP slices), then
  narrowed operand/result width to profiled actual values — a program
  calling `custom_mul(6, 7)` needs 0 DSP slices, confirmed via a real
  Vivado timing report showing the multiply synthesizing entirely in
  LUTs with 11ns+ of slack.
- **Cycle count vs. compiler optimization level**: the same bubble-sort
  test program, compiled at `-O0` vs `-O2`: **11,664 cycles → 3,238
  cycles**, a 72% reduction, identical correct output both times.
- **Data memory word width**: same bubble-sort program, per-word storage
  narrowed from 32 bits to 15 bits (53% reduction) — verified with a full
  compile-through-simulation run, same correct final answer.

## Requirements

- `riscv32-unknown-elf-gcc` (or equivalent RV32I bare-metal cross-compiler
  with `nm`/`objdump`/`objcopy`)
- Python 3
- Icarus Verilog (`iverilog`/`vvp`) for RTL simulation
- Xilinx Vivado 2025.2+ (only required for `bitstream`/`vivado` commands)

## Quick start

```bash
chmod +x riscreaper

./riscreaper new mytest              # scaffold demo/mytest.c from a working template
./riscreaper build demo/mytest.c     # compile, profile, trim -> RTL + a trim summary
./riscreaper bitstream demo/mytest.c # same, then synthesize + implement + bitstream

# optimization level is configurable, defaults to -O0:
./riscreaper build demo/mytest.c --opt-level=-O2
```

Run `./riscreaper --help` for the full command list, or
`./riscreaper <command> --help` for details on any specific one.

## CLI reference

| Command | Description |
|---|---|
| `new <name>` | Scaffold `demo/<name>.c` from a working template |
| `mem <source.c> [name]` | Compile + extract `.mem` only — no profiling/trimming/RTL |
| `build <source.c> [name] [max_steps] [--opt-level]` | Full trim pipeline, ends with a trim summary |
| `bitstream <source.c> [name] [max_steps] [--opt-level]` | Full flow + Vivado synthesis/implementation/bitstream |
| `vivado` | Re-run Vivado on the existing `generated/` output |
| `summary` | Show/regenerate the trim summary for the most recent build |
| `clean [--yes]` | Wipe `generated/` for a fresh build |
| `--quiet` | Suppress the banner — usable before or after any subcommand |

## Project structure

```
riscreaper                    # CLI entry point
tools/
    c_to_mem.sh                # C -> ELF/disassembly/.mem, main()-offset extraction
    build_from_c_with_trimming.sh   # full two-pass profile-and-trim pipeline
    build_and_vivado_trimmed.sh     # the above + Vivado, one command
    run_vivado.sh
    emulator.py                 # the RV32I profiling emulator
    gen_pc.py / gen_instruction_memory.py / gen_data_memory.py
    gen_startup_stub.py          # 3-instruction stub: sp/ra init, jump to main()
    gen_control_from_insts.py    # control_unit.v / alu_control.v / register_file.v / imm_gen.v / branch_unit.v / alu.v
    gen_dense_control.py         # dense-encodes alu_op/alu_control/mem_to_reg
    gen_pipeline_regs.py         # pipeline registers, hazard_unit, flush_unit, forwarding_unit
    gen_pipeline_and_tb.py       # pipeline_top.v, pipeline_top_hw.v, testbenches
    gen_custom_unit.py           # trimmed custom instruction unit
    gen_trimmed_rtl.py           # post-final-profile width patching (alu/imm/regfile/data memory)
    gen_trim_summary.py          # human-readable trim report
    riscv_harvard.ld             # Harvard-architecture linker script (separate IMEM/DMEM)
    *_v.j2                       # Jinja2 templates for leaf RTL modules
demo/                          # your C source programs
generated/                    # build output (gitignored — fully regeneratable)
```

## Board setup (Basys3)

| Signal | Pin | Notes |
|---|---|---|
| `clk` | W5 | 100MHz onboard oscillator — design runs at 50MHz via constraint |
| `reset` | U18 (btnC) | Active-high, async |
| `halted` | LED0 (U16) | |
| `result_valid` | LED1 (E19) | |
| `result_data[0..13]` | LEDs 2-15 | Capped to 14 bits — the remaining onboard LED budget after `halted`/`result_valid` |

## Notes on the architecture

- **Harvard architecture**: instruction and data memory are separate,
  independently-addressed spaces (both based at address 0), matching the
  linker script and the RTL's actual memory model.
- **Two-pass profiling**: the emulator runs once with a conservative
  default stack size to discover the real memory footprint, then again
  with the computed minimal size — so every trimming decision is based
  on final, correct addressing, not the bootstrap pass's provisional one.
- **`pipeline_top_hw`** exposes a narrow, board-appropriate interface
  (`clk`/`reset`/`halted`/`result_valid`/`result_data`) for synthesis,
  separate from the full internal-signal debug testbench used for
  RTL/behavioral simulation.

## Known limitations / open work

- Loop unrolling (the compiler-side path to reducing branch overhead) has
  not been attempted.
- Not every test program in this project's history has been verified
  against a real cross-compiler — some verification was done via manual
  reconstruction from real disassembly output where compiler access
  wasn't available at the time.
