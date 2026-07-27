// ============================================================
// Module      : tb_pipeline_top_demo
// Description : Program-specific smoke testbench for demo
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top_demo;
    reg clk;
    reg reset;
    integer cyclecount;

    pipeline_top u_dut (
        .clk(clk),
        .reset(reset)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_pipeline_top_demo.vcd");
        $dumpvars(0, tb_pipeline_top_demo);
    end

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("Program-specific pipeline_top simulation start");
        $display("Program: demo");
        repeat (5) @(posedge clk);
        reset = 1'b0;
        $display("%0t Reset deasserted", $time);
        repeat (200) begin
            @(posedge clk);
            cyclecount = cyclecount + 1;
            if (cyclecount % 20 == 0)
                $display("%0t Cycle %0d", $time, cyclecount);
        end
        $display("PASS program-specific smoke test completed after %0d cycles", cyclecount);
        $finish;
    end

    initial begin
        #5000;
        $display("FAIL timeout in tb_pipeline_top_demo.v");
        $finish;
    end
endmodule
