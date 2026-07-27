// ============================================================
// Module      : Data Memory
// File        : data_memory.v
// Description : 11-word data RAM (auto-generated, sized to
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

    reg [31:0] mem [0:10];

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
                        2'b00: read_data = {{24{mem[address[31:2]][7]}},
                                             mem[address[31:2]][7:0]};
                        2'b01: read_data = {{24{mem[address[31:2]][15]}},
                                             mem[address[31:2]][15:8]};
                        2'b10: read_data = {{24{mem[address[31:2]][23]}},
                                             mem[address[31:2]][23:16]};
                        2'b11: read_data = {{24{mem[address[31:2]][31]}},
                                             mem[address[31:2]][31:24]};
                        default: read_data = 32'h0;
                    endcase
                end
                3'b001: begin  // lh -- load halfword signed
                    case (address[1])
                        1'b0: read_data = {{16{mem[address[31:2]][15]}},
                                            mem[address[31:2]][15:0]};
                        1'b1: read_data = {{16{mem[address[31:2]][31]}},
                                            mem[address[31:2]][31:16]};
                        default: read_data = 32'h0;
                    endcase
                end
                3'b010:  // lw -- load word
                    read_data = mem[address[31:2]];
                3'b100: begin  // lbu -- load byte unsigned
                    case (address[1:0])
                        2'b00: read_data = {24'h0, mem[address[31:2]][7:0]};
                        2'b01: read_data = {24'h0, mem[address[31:2]][15:8]};
                        2'b10: read_data = {24'h0, mem[address[31:2]][23:16]};
                        2'b11: read_data = {24'h0, mem[address[31:2]][31:24]};
                        default: read_data = 32'h0;
                    endcase
                end
                3'b101: begin  // lhu -- load halfword unsigned
                    case (address[1])
                        1'b0: read_data = {16'h0, mem[address[31:2]][15:0]};
                        1'b1: read_data = {16'h0, mem[address[31:2]][31:16]};
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
