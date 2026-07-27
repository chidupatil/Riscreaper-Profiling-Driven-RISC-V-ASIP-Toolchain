// Trim applied: register index ports narrowed to 4 bits (safe: unsigned address pruning); per-register storage narrowed independently (x1=7b, x2=7b, x10=7b, x14=4b, x15=7b); read/write ports stay 32-bit; visible registers=[1, 2, 10, 14, 15]
// ============================================================
// Module      : Register File
// File        : register_file.v
// Description : Specialized architectural register file.
//               Only registers written by the current program
//               are physically stored.
//               x0 remains hardwired to 0.
//
// Registers read   : [1, 2, 14, 15]
// Registers written: [1, 2, 10, 14, 15]
// Stored registers : [1, 2, 10, 14, 15]
// ============================================================

`timescale 1ns / 1ps

module register_file (
    input             clk,
    input             reg_write,
    input      [3:0]  rs1,
    input      [3:0]  rs2,
    input      [3:0]  rd,
    input      [31:0] write_data,
    output     [31:0] read_data1,
    output     [31:0] read_data2
);


    reg [6:0] r1;

    reg [6:0] r2;

    reg [6:0] r10;

    reg [3:0] r14;

    reg [6:0] r15;


    initial begin


        r1 = 7'h0;

        r2 = 7'h0;

        r10 = 7'h0;

        r14 = 4'h0;

        r15 = 7'h0;


    end

    // Synchronous write - x0 and unused registers ignored
    always @(posedge clk) begin
        if (reg_write) begin
            case (rd)

                5'd1: r1 <= write_data[6:0];

                5'd2: r2 <= write_data[6:0];

                5'd10: r10 <= write_data[6:0];

                5'd14: r14 <= write_data[3:0];

                5'd15: r15 <= write_data[6:0];

                default: ;
            endcase
        end
    end

    reg [31:0] read_data1_r;
    reg [31:0] read_data2_r;

    always @(*) begin
        case (rs1)
            5'd0: read_data1_r = 32'h00000000;

            5'd1: read_data1_r = {{25{r1[6]}}, r1};

            5'd2: read_data1_r = {{25{r2[6]}}, r2};

            5'd10: read_data1_r = {{25{r10[6]}}, r10};

            5'd14: read_data1_r = {{28{r14[3]}}, r14};

            5'd15: read_data1_r = {{25{r15[6]}}, r15};

            default: read_data1_r = 32'h00000000;
        endcase
    end

    always @(*) begin
        case (rs2)
            5'd0: read_data2_r = 32'h00000000;

            5'd1: read_data2_r = {{25{r1[6]}}, r1};

            5'd2: read_data2_r = {{25{r2[6]}}, r2};

            5'd10: read_data2_r = {{25{r10[6]}}, r10};

            5'd14: read_data2_r = {{28{r14[3]}}, r14};

            5'd15: read_data2_r = {{25{r15[6]}}, r15};

            default: read_data2_r = 32'h00000000;
        endcase
    end

    // Asynchronous read with write-before-read forwarding
    assign read_data1 =
        (rs1 == 5'd0) ? 32'h00000000 :
        (reg_write && rd == rs1 && rd != 5'd0) ? write_data :
        read_data1_r;

    assign read_data2 =
        (rs2 == 5'd0) ? 32'h00000000 :
        (reg_write && rd == rs2 && rd != 5'd0) ? write_data :
        read_data2_r;

endmodule