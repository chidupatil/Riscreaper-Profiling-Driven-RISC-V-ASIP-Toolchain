// ============================================================
// Module      : tb_pipeline_top_smaple
// Description : Program-specific smoke testbench for smaple
// ============================================================
`timescale 1ns / 1ps

module tb_pipeline_top_smaple;
    reg clk;
    reg reset;
    integer cyclecount;

    wire        halted;
    wire [31:0] dbg_pc;
    wire [31:0] dbg_instr_if;
    wire [31:0] dbg_instr_id;
    wire [31:0] dbg_alu_result_ex;
    wire dbg_branch_taken_ex;
    wire dbg_mem_write_mem;
    wire [31:0] dbg_mem_addr_mem;
    wire [31:0] dbg_mem_wdata_mem;
    wire dbg_reg_write_wb;
    wire [3:0] dbg_rd_wb;
    wire [31:0] dbg_wb_data;

    reg [31:0] last_wb_data;
    reg [3:0] last_wb_rd;
    reg last_wb_seen;
    reg [31:0] last_mem_addr;
    reg [31:0] last_mem_wdata;
    reg last_mem_seen;

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
    end
    always @(posedge clk) begin
        if (dbg_reg_write_wb && (dbg_rd_wb != 0)) begin
            last_wb_data <= dbg_wb_data;
            last_wb_rd   <= dbg_rd_wb;
            last_wb_seen <= 1'b1;
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
        $dumpfile("tb_pipeline_top_smaple.vcd");
        $dumpvars(0, tb_pipeline_top_smaple);
    end

    localparam MAX_CYCLES = 2000;

    initial begin
        cyclecount = 0;
        reset = 1'b1;
        $display("============================================================");
        $display(" Program-specific pipeline_top simulation start");
        $display(" Program: smaple");
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
        if (last_wb_seen)
            $display("Last REAL writeback : rd=x%0d data=0x%0h (%0d)",
                     last_wb_rd, last_wb_data, $signed(last_wb_data));
        else
            $display("Last REAL writeback : (no register was ever written this run)");
        if (last_mem_seen)
            $display("Last REAL mem write : addr=0x%0h wdata=0x%0h (%0d)",
                     last_mem_addr, last_mem_wdata, $signed(last_mem_wdata));
        else
            $display("Last REAL mem write : (no memory write occurred this run)");
        $display("Final PC            : 0x%0h", dbg_pc);
        $display("");
        $display("NOTE: this build only exposes the last REAL writeback/memory");
        $display("write, not a full register/memory dump -- hierarchical");
        $display("internal signal access (e.g. u_reg_file.r1) does not survive");
        $display("post-synthesis simulation, which this testbench also has to");
        $display("support. This build stores these registers: [1, 2, 8, 10, 14, 15]");
        $display("############################################################");
        $display("");

        $finish;
    end

    initial begin
        #20000;
        $display("FAIL absolute timeout in tb_pipeline_top_smaple.v");
        $finish;
    end
endmodule
