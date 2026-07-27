// Trim applied: immediate significant width = 7 bits (sign-extended internally; port stays 32-bit; U-type exempted)
`timescale 1ns / 1ps

module imm_gen (
    input      [31:0] instruction,
    output [31:0] imm_out
);

    wire [6:0] opcode;
    assign opcode = instruction[6:0];

    reg [31:0] imm_out_full;
    wire is_u_type = (opcode == 7'b0110111) || (opcode == 7'b0010111);

    always @(*) begin
        case (opcode)


            // I-type: addi, lw, jalr, and similar
            7'b0010011,
            7'b0000011,
            7'b1100111: begin

                imm_out_full = {{20{instruction[31]}}, instruction[31:20]};

            end



            // S-type: sw, sb, sh
            7'b0100011: begin

                imm_out_full = {{20{instruction[31]}}, instruction[31:25], instruction[11:7]};

            end







            // J-type: jal
            7'b1101111: begin

                imm_out_full = {{11{instruction[31]}},
                           instruction[31],
                           instruction[19:12],
                           instruction[20],
                           instruction[30:21],
                           1'b0};

            end


            default: begin
                imm_out_full = 32'b0;
            end
        endcase
    end


    // U-type (lui/auipc) immediates carry their meaning in the UPPER
    // bits (lower 12 are architecturally 0) -- no low-bits-plus-sign-
    // extension scheme can represent them, so they pass through at
    // full precision regardless of the profiled width for other kinds.
    assign imm_out = is_u_type ? imm_out_full : {{25{imm_out_full[6]}}, imm_out_full[6:0]};
endmodule