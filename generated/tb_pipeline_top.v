// ============================================================
// Module      : tb_pipeline_top
// Description : Testbench for pipeline_top_hw -- the SAME module used
//               as the synthesis/implementation top (see build.tcl).
//               This is deliberate: post-synthesis simulation runs
//               against whatever synth_1 actually built, so this
//               testbench must instantiate the identical hierarchy, or
//               the simulation isn't actually testing what got
//               synthesized. For full per-cycle debug visibility
//               (PC/instruction/ALU/memory trace) in RTL/behavioral-only
//               simulation, use tb_pipeline_top_<program>.v instead,
//               which instantiates pipeline_top directly -- that
//               testbench is NOT valid for post-synthesis simulation.
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top;
    reg clk;
    reg reset;
    integer cyclecount;

    wire halted;
    wire result_valid;
    wire [6:0] result_data;

    pipeline_top_hw u_dut (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .result_valid(result_valid),
        .result_data(result_data)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_pipeline_top.vcd");
        $dumpvars(0, tb_pipeline_top);
    end

    // No fixed cycle count: this testbench decides for itself, via
    // `halted`, exactly when the program is done. Note this is about
    // DYNAMIC execution length, not the STATIC instruction count -- an
    // 18-instruction program with no loops stops in ~18 + a handful of
    // drain cycles, but an 18-instruction program containing a
    // 128-iteration loop can easily need several thousand cycles, since
    // the same small set of instructions gets fetched over and over.
    // MAX_CYCLES below is a generous upper bound covering that, not a
    // per-instruction-count estimate. Pair with `run -all` in the
    // Vivado sim Tcl (not `run <fixed time>`), so XSim actually stops
    // here instead of waiting out a fixed wall-clock duration
    // regardless of $finish.
    localparam MAX_CYCLES = 200000;  // generous margin for real loops (e.g. 128 iterations easily needs several thousand cycles)

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("============================================================");
        $display(" pipeline_top_hw simulation start (matches synthesis top)");
        $display("============================================================");

        repeat (5) @(posedge clk);
        reset = 1'b0;

        while (!halted && cyclecount < MAX_CYCLES) begin
            @(posedge clk);
            cyclecount = cyclecount + 1;
        end

        $display("");
        $display("############################################################");
        $display("###                  FINAL RESULT                       ###");
        $display("############################################################");
        $display("halted=%b at cycle=%0d", halted, cyclecount);
        if (result_valid)
            $display("Return value (a0/x10) : 0x%0h (%0d)  <- latched in real hardware logic, per RISC-V calling convention",
                     result_data, $signed(result_data));
        else
            $display("Return value (a0/x10) : (x10 was never written this run -- this program may not follow the standard calling convention)");
        $display("############################################################");
        $display("");

        if (halted)
            $display("PASS: halted cleanly after %0d cycles", cyclecount);
        else
            $display("FAIL: halted never asserted within %0d cycles", MAX_CYCLES);
        $finish;
    end

    initial begin
        #2000000;  // matches MAX_CYCLES=200000 at 10ns/cycle
        $display("FAIL simulation timeout");
        $finish;
    end
endmodule
