#!/usr/bin/env python3
"""
gen_data_memory.py -- generates data_memory.v sized to the actual
profiled address range, instead of a fixed 64-word (256-byte)
allocation regardless of program size.

WHY THIS IS SAFER THAN NARROWING WORD WIDTH (and why width stays 32):
------------------------------------------------------------------------
Only the DEPTH (number of words) is parametrized here -- the per-word
width stays 32 bits, unconditionally. Two reasons this is the safe
subset of "trim data_memory.v" and per-word width narrowing (like
register_file.v's per-register independent widths) is NOT attempted:

  1. Sub-word addressing needs the full word structure at EVERY
     location. `sb`/`lb`/`sh`/`lh` can target any byte offset within any
     word (mem[addr][31:24], mem[addr][15:8], etc.) -- narrowing a
     word's storage to match whatever value happens to be stored there
     would make those upper-byte accesses reference bits that no longer
     exist, not "safely truncated" bits.

  2. This project's data memory is used HETEROGENEOUSLY: the stack
     frame stores full-width saved values (e.g. `sw ra, 28(sp)`) right
     alongside byte-sized locals (e.g. `sb` for a loop counter) in the
     SAME array. Register file trimming worked because each register is
     its own independent named signal; data_memory.v is one array
     serving every address, so there's no way to narrow "just the
     byte-sized part" without also truncating the full-width saves
     sharing that array.

Depth, on the other hand, is completely safe to narrow: reducing the
NUMBER of words has no effect on the WIDTH of any individual word, so
byte/halfword sub-addressing within a word is entirely unaffected.

COORDINATION REQUIREMENT:
--------------------------
The depth chosen here MUST stay consistent with gen_startup_stub.py's
--stack-top value -- sp is initialized to point at the top of exactly
this array, so if this array shrinks without stack_top shrinking to
match (or vice versa), out-of-bounds stack accesses reappear. See
build_from_c_with_trimming.sh's two-pass flow for how these two stay in
sync: profile once with a safe default depth, compute the real
requirement from that profile, regenerate both this file and the
startup stub with the computed depth, then re-profile so every
downstream trimming decision is based on the FINAL, consistent
addresses -- not the bootstrap pass's.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_DEPTH_WORDS = 64  # matches the original, safe, hand-written size
MARGIN_BYTES = 32         # slack added above the profiled max address


def compute_required_depth_words(bit_profile: dict, default_stack_top: int,
                                  data_mem_word_count: int = 0,
                                  margin_bytes: int = MARGIN_BYTES) -> int:
    """Computes the minimum word depth this program actually needs, from
    a bootstrap profiling pass run with sp initialized to
    default_stack_top. Falls back to the original safe default if the
    profile shows no memory activity at all.

    THE KEY INSIGHT (found via direct testing, not obvious in advance):
    stack addresses are always close to whatever stack_top was, by
    construction -- sp starts AT stack_top and only moves down via
    subtraction, so memory_max_addr for a stack-only program will always
    end up near default_stack_top regardless of how little stack space
    is genuinely used. An earlier version of this function used
    memory_max_addr directly and reported zero savings for a
    3-instruction test program that only ever touched 4 bytes of stack,
    because that one access (sp-4) was still numerically close to 256.

    What actually reflects real usage is stack_top - memory_min_addr --
    how far below the bootstrap stack_top anything was ever accessed.
    That's computed here as stack_depth_used, and the new stack_top
    becomes stack_depth_used + margin (rounded up to a word boundary).

    This is separately checked against data_mem_word_count (the actual
    line count of data.mem) so that global/static variables -- which
    live at LOW, fixed addresses independent of stack_top -- never get
    truncated by a stack-driven depth reduction that has nothing to do
    with them.
    """
    min_addr = bit_profile.get("memory_min_addr")
    if min_addr is None:
        return max(DEFAULT_DEPTH_WORDS if data_mem_word_count == 0 else data_mem_word_count,
                    data_mem_word_count)
    stack_depth_used = max(0, default_stack_top - min_addr)
    required_bytes = stack_depth_used + margin_bytes
    required_words = -(-required_bytes // 4)  # ceil division to word count
    required_words = max(required_words, data_mem_word_count)  # never truncate globals
    # Never exceed the original safe default -- this is a narrowing
    # operation, not a way to accidentally grow the array.
    return max(1, min(required_words, DEFAULT_DEPTH_WORDS))


def gen_data_memory(depth_words: int) -> str:
    depth_words = max(1, depth_words)
    last_idx = depth_words - 1
    addr_hi = (depth_words - 1).bit_length() + 1  # word index bits, +2 handled via [addr_hi+1:2] below
    return f'''// ============================================================
// Module      : Data Memory
// File        : data_memory.v
// Description : {depth_words}-word data RAM (auto-generated, sized to
//               this program's actual profiled address range -- was a
//               fixed 64-word allocation regardless of program size).
//               Supports byte, halfword, and word reads and writes for
//               full RV32I. Per-word width is unconditionally 32 bits --
//               see this file's generator (gen_data_memory.py) for why
//               narrowing that is NOT safe the way register file
//               per-register widths were.
//
// COORDINATION: depth_words here MUST match gen_startup_stub.py's
// --stack-top value (stack_top = depth_words * 4). If these ever
// disagree, out-of-bounds stack accesses reappear.
//
// funct3 encoding for loads/stores:
//   000 -> byte  (lb/sb)
//   001 -> half  (lh/sh)
//   010 -> word  (lw/sw)
//   100 -> byte unsigned  (lbu)
//   101 -> half unsigned  (lhu)
// ============================================================

`timescale 1ns / 1ps

module data_memory (
    input             clk,
    input             mem_read,
    input             mem_write,
    input      [2:0]  funct3,
    input      [31:0] address,
    input      [31:0] write_data,
    output reg [31:0] read_data
);

    reg [31:0] mem [0:{last_idx}];

    initial begin
        $readmemh("data.mem", mem);
    end

    // -- Synchronous Write -----------------------------------
    always @(posedge clk) begin
        if (mem_write) begin
            case (funct3)
                3'b000: begin  // sb -- store byte
                    case (address[1:0])
                        2'b00: mem[address[31:2]][7:0]   <= write_data[7:0];
                        2'b01: mem[address[31:2]][15:8]  <= write_data[7:0];
                        2'b10: mem[address[31:2]][23:16] <= write_data[7:0];
                        2'b11: mem[address[31:2]][31:24] <= write_data[7:0];
                    endcase
                end
                3'b001: begin  // sh -- store halfword
                    case (address[1])
                        1'b0: mem[address[31:2]][15:0]  <= write_data[15:0];
                        1'b1: mem[address[31:2]][31:16] <= write_data[15:0];
                    endcase
                end
                3'b010:  // sw -- store word
                    mem[address[31:2]] <= write_data;
                default:
                    mem[address[31:2]] <= write_data;
            endcase
        end
    end

    // -- Combinational Read ------------------------------------
    always @(*) begin
        if (mem_read) begin
            case (funct3)
                3'b000: begin  // lb -- load byte signed
                    case (address[1:0])
                        2'b00: read_data = {{{{24{{mem[address[31:2]][7]}}}},
                                             mem[address[31:2]][7:0]}};
                        2'b01: read_data = {{{{24{{mem[address[31:2]][15]}}}},
                                             mem[address[31:2]][15:8]}};
                        2'b10: read_data = {{{{24{{mem[address[31:2]][23]}}}},
                                             mem[address[31:2]][23:16]}};
                        2'b11: read_data = {{{{24{{mem[address[31:2]][31]}}}},
                                             mem[address[31:2]][31:24]}};
                        default: read_data = 32'h0;
                    endcase
                end
                3'b001: begin  // lh -- load halfword signed
                    case (address[1])
                        1'b0: read_data = {{{{16{{mem[address[31:2]][15]}}}},
                                            mem[address[31:2]][15:0]}};
                        1'b1: read_data = {{{{16{{mem[address[31:2]][31]}}}},
                                            mem[address[31:2]][31:16]}};
                        default: read_data = 32'h0;
                    endcase
                end
                3'b010:  // lw -- load word
                    read_data = mem[address[31:2]];
                3'b100: begin  // lbu -- load byte unsigned
                    case (address[1:0])
                        2'b00: read_data = {{24'h0, mem[address[31:2]][7:0]}};
                        2'b01: read_data = {{24'h0, mem[address[31:2]][15:8]}};
                        2'b10: read_data = {{24'h0, mem[address[31:2]][23:16]}};
                        2'b11: read_data = {{24'h0, mem[address[31:2]][31:24]}};
                        default: read_data = 32'h0;
                    endcase
                end
                3'b101: begin  // lhu -- load halfword unsigned
                    case (address[1])
                        1'b0: read_data = {{16'h0, mem[address[31:2]][15:0]}};
                        1'b1: read_data = {{16'h0, mem[address[31:2]][31:16]}};
                        default: read_data = 32'h0;
                    endcase
                end
                default:
                    read_data = mem[address[31:2]];
            endcase
        end
        else
            read_data = 32'h0;
    end

endmodule
'''


def count_words(mem_path: Path) -> int:
    if not mem_path.exists():
        return 0
    return sum(
        1 for line in mem_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("//", "#"))
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--depth-words", type=int, default=None,
                         help="Explicit word depth. If omitted, --bit-profile is required.")
    parser.add_argument("--bit-profile", type=Path, default=None,
                         help="bit_profile.json to compute the required depth from.")
    parser.add_argument("--default-stack-top", type=int, default=DEFAULT_DEPTH_WORDS * 4,
                         help="The stack_top the bootstrap profiling pass used (bytes). Required for accurate depth computation from --bit-profile.")
    parser.add_argument("--data-mem", type=Path, default=None,
                         help="Path to data.mem, to ensure globals/statics never get truncated by a stack-driven depth reduction.")
    args = parser.parse_args(argv)

    if args.depth_words is not None:
        depth_words = max(1, args.depth_words)
    elif args.bit_profile is not None:
        profile = json.loads(args.bit_profile.read_text(encoding="utf-8"))
        data_words = count_words(args.data_mem) if args.data_mem else 0
        depth_words = compute_required_depth_words(profile, args.default_stack_top, data_words)
    else:
        print("Must supply either --depth-words or --bit-profile")
        return 1

    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "data_memory.v").write_text(gen_data_memory(depth_words), encoding="utf-8")
    (args.outdir / "data_depth_words.txt").write_text(str(depth_words), encoding="utf-8")

    print(f"Generated data_memory.v with depth={depth_words} words ({depth_words * 4} bytes) "
          f"(was fixed at 64 words regardless of program size)")
    print(f"Wrote {args.outdir / 'data_depth_words.txt'} for the build script to compute a matching --stack-top")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())