// ============================================================
// Module      : pipeline_top_hw
// File        : pipeline_top_hw.v
// Description : Hardware-implementation wrapper around pipeline_top.
//               Exposes clk/reset/halted plus a narrow, MEANINGFUL
//               result output (result_valid/result_data = the low
//               7 bits of the last write to x10/a0,
//               latched in real synthesizable logic) -- not the full
//               dbg_* debug interface, but also not NOTHING beyond
//               halted, and capped to a width any real board's LEDs
//               can actually hold. See this file's generator
//               (gen_pipeline_and_tb.py's make_pipeline_top_hw) for the
//               full reasoning, including why alu_width itself (here:
//               7 bits) can't just be exposed directly.
//
// Use THIS as the synthesis/implementation top AND as what
// tb_pipeline_top.v instantiates -- both need to agree on the same
// hierarchy for post-synthesis simulation to be valid at all.
// ============================================================

`timescale 1ns / 1ps

module pipeline_top_hw (
    input  clk,
    input  reset,
    output halted,
    output result_valid,
    output [6:0] result_data
);

    wire dbg_reg_write_wb;
    wire [3:0] dbg_rd_wb;
    wire [6:0] dbg_wb_data;

    pipeline_top u_core (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .dbg_reg_write_wb(dbg_reg_write_wb),
        .dbg_rd_wb(dbg_rd_wb),
        .dbg_wb_data(dbg_wb_data)
        // Remaining dbg_* ports (dbg_pc, dbg_instr_if, dbg_instr_id,
        // dbg_alu_result_ex, dbg_branch_taken_ex, dbg_mem_write_mem,
        // dbg_mem_addr_mem, dbg_mem_wdata_mem) intentionally left
        // unconnected -- these are per-cycle trace signals with no
        // meaningful "final" value to latch and report as a real
        // hardware output. Full per-cycle visibility is still available
        // in RTL/behavioral-only simulation via tb_pipeline_top_<program>.v,
        // which instantiates pipeline_top directly (documented there as
        // not valid for post-synthesis use).
    );

    // Real synthesizable latch, not a testbench construct: holds the
    // low 7 bits of the last value written to x10/a0 for
    // as long as the design is powered, so a real user reading these
    // pins after `halted` asserts sees the actual computed result, not
    // a live wire that's already gone stale from epilogue/drain-cycle
    // activity by the time they look. Only the low 7 bits
    // of dbg_wb_data are captured -- see this function's docstring for
    // why the full 7-bit value can't be exposed as pins
    // directly.
    reg result_valid_r;
    reg [6:0] result_data_r;

    initial begin
        result_valid_r = 1'b0;
    end

    always @(posedge clk) begin
        if (reset) begin
            result_valid_r <= 1'b0;
        end else if (dbg_reg_write_wb && (dbg_rd_wb == 10)) begin
            result_data_r  <= dbg_wb_data[6:0];
            result_valid_r <= 1'b1;
        end
    end

    assign result_valid = result_valid_r;
    assign result_data  = result_data_r;

endmodule
