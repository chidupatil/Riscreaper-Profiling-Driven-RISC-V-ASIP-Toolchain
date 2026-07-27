// ============================================================
// Module      : tb_pipeline_top_six
// Description : Program-specific RICH-DEBUG testbench for six
//               Instantiates pipeline_top DIRECTLY (full dbg_* trace:
//               PC, instruction, ALU result, memory access, every
//               cycle). RTL/BEHAVIORAL SIMULATION ONLY -- do not use
//               this for post-synthesis simulation. synth_1's actual
//               top is pipeline_top_hw (see build.tcl), which leaves
//               most of pipeline_top's dbg_* ports unconnected; trying
//               to instantiate pipeline_top directly against that
//               synthesized netlist risks the same
//               "port not declared" failures hierarchical signal
//               access hit earlier in this project. For a testbench
//               that's valid in both RTL and post-synthesis contexts,
//               use tb_pipeline_top.v (make_stable_tb) instead, which
//               instantiates pipeline_top_hw to match what's actually
//               synthesized.
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top_six;
    reg clk;
    reg reset;
    integer cyclecount;

    wire        halted;
    wire [31:0] dbg_pc;
    wire [31:0] dbg_instr_if;
    wire [31:0] dbg_instr_id;
    wire [8:0] dbg_alu_result_ex;
    wire dbg_branch_taken_ex;
    wire dbg_mem_write_mem;
    wire [8:0] dbg_mem_addr_mem;
    wire [8:0] dbg_mem_wdata_mem;
    wire dbg_reg_write_wb;
    wire [3:0] dbg_rd_wb;
    wire [8:0] dbg_wb_data;

    reg [8:0] last_wb_data;
    reg [3:0] last_wb_rd;
    reg last_wb_seen;
    reg [8:0] last_mem_addr;
    reg [8:0] last_mem_wdata;
    reg last_mem_seen;
    reg [8:0] last_a0_data;
    reg last_a0_seen;

    pipeline_top u_dut (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .dbg_pc(dbg_pc),
        .dbg_instr_if(dbg_instr_if),
        .dbg_instr_id(dbg_instr_id),
        .dbg_alu_result_ex(dbg_alu_result_ex),
        .dbg_branch_taken_ex(dbg_branch_taken_ex),
        .dbg_mem_write_mem(dbg_mem_write_mem),
        .dbg_mem_addr_mem(dbg_mem_addr_mem),
        .dbg_mem_wdata_mem(dbg_mem_wdata_mem),
        .dbg_reg_write_wb(dbg_reg_write_wb),
        .dbg_rd_wb(dbg_rd_wb),
        .dbg_wb_data(dbg_wb_data)
    );

    initial begin
        last_wb_seen = 1'b0;
        last_mem_seen = 1'b0;
        last_a0_seen = 1'b0;
    end
    always @(posedge clk) begin
        if (dbg_reg_write_wb && (dbg_rd_wb != 0)) begin
            last_wb_data <= dbg_wb_data;
            last_wb_rd   <= dbg_rd_wb;
            last_wb_seen <= 1'b1;
        end
        if (dbg_reg_write_wb && (dbg_rd_wb == 10)) begin
            last_a0_data <= dbg_wb_data;
            last_a0_seen <= 1'b1;
        end
        if (dbg_mem_write_mem) begin
            last_mem_addr  <= dbg_mem_addr_mem;
            last_mem_wdata <= dbg_mem_wdata_mem;
            last_mem_seen  <= 1'b1;
        end
    end

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_pipeline_top_six.vcd");
        $dumpvars(0, tb_pipeline_top_six);
    end

    localparam MAX_CYCLES = 200000;  // generous margin for real loops (e.g. 128 iterations easily needs several thousand cycles)

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("============================================================");
        $display(" Program-specific pipeline_top simulation start");
        $display(" Program: six");
        $display("============================================================");

        repeat (5) @(posedge clk);
        reset = 1'b0;
        $display("%0t Reset deasserted", $time);

        while (!halted && cyclecount < MAX_CYCLES) begin
            @(posedge clk);
            cyclecount = cyclecount + 1;
            $display("Cycle %0d | PC=0x%0h | InstrIF=0x%08h | WB reg_write=%b rd=x%0d data=0x%0h (%0d) | MEM write=%b addr=0x%0h wdata=0x%0h",
                     cyclecount, dbg_pc, dbg_instr_if, dbg_reg_write_wb, dbg_rd_wb, dbg_wb_data, dbg_wb_data,
                     dbg_mem_write_mem, dbg_mem_addr_mem, dbg_mem_wdata_mem);
        end


        $display("");
        $display("############################################################");
        $display("###                  FINAL RESULT                       ###");
        $display("############################################################");
        $display("halted=%b at cycle=%0d", halted, cyclecount);
        if (last_a0_seen)
            $display("Return value (a0/x10) : 0x%0h (%0d)  <- last write to x10, per RISC-V calling convention",
                     last_a0_data, $signed(last_a0_data));
        else
            $display("Return value (a0/x10) : (x10 was never written this run -- this program may not follow the standard calling convention, or doesn't use a0 for its result)");
        if (last_wb_seen)
            $display("Last REAL writeback   : rd=x%0d data=0x%0h (%0d)  (often just epilogue sp/fp restoration -- NOT necessarily the answer, see a0 above)",
                     last_wb_rd, last_wb_data, $signed(last_wb_data));
        else
            $display("Last REAL writeback   : (no register was ever written this run)");
        if (last_mem_seen)
            $display("Last REAL mem write   : addr=0x%0h wdata=0x%0h (%0d)",
                     last_mem_addr, last_mem_wdata, $signed(last_mem_wdata));
        else
            $display("Last REAL mem write   : (no memory write occurred this run)");
        $display("Final PC              : 0x%0h", dbg_pc);
        $display("");
        $display("NOTE: this build only exposes the last REAL writeback/memory");
        $display("write, not a full register/memory dump -- hierarchical internal");
        $display("signal access (e.g. u_reg_file.r1) doesn't survive synthesis.");
        $display("This testbench instantiates pipeline_top directly for full debug");
        $display("visibility -- RTL/behavioral simulation ONLY, not valid for");
        $display("post-synthesis sim (use tb_pipeline_top.v for that instead).");
        $display("This build stores these registers: [1, 2, 8, 10, 11, 12, 13, 14, 15]");
        $display("############################################################");
        $display("");

        $finish;
    end

    initial begin
        #2000000;  // matches MAX_CYCLES=200000 at 10ns/cycle
        $display("FAIL absolute timeout in tb_pipeline_top_six.v");
        $finish;
    end
endmodule
