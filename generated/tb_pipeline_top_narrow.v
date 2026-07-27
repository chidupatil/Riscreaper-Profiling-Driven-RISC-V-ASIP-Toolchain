// ============================================================
// Module      : tb_pipeline_top_narrow
// Description : Program-specific smoke testbench for narrow
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top_narrow;
    reg clk;
    reg reset;
    integer cyclecount;

    pipeline_top u_dut (
    .clk                (clk),
    .reset              (reset),
    .dbg_pc             (dbg_pc),
    .dbg_instr_if       (dbg_instr_if),
    .dbg_instr_id       (dbg_instr_id),
    .dbg_alu_result_ex  (dbg_alu_result_ex),
    .dbg_branch_taken_ex(dbg_branch_taken_ex),
    .dbg_mem_write_mem  (dbg_mem_write_mem),
    .dbg_mem_addr_mem   (dbg_mem_addr_mem),
    .dbg_mem_wdata_mem  (dbg_mem_wdata_mem),
    .dbg_reg_write_wb   (dbg_reg_write_wb),
    .dbg_rd_wb          (dbg_rd_wb),
    .dbg_wb_data        (dbg_wb_data)
);
    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_pipeline_top_narrow.vcd");
        $dumpvars(0, tb_pipeline_top_narrow);
    end

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("Program-specific pipeline_top simulation start");
        $display("Program: narrow");
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
        $display("FAIL timeout in tb_pipeline_top_narrow.v");
        $finish;
    end
endmodule
