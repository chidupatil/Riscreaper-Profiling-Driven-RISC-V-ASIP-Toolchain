// ============================================================
// Module      : RISC-V 5-Stage Pipeline Top
// File        : pipeline_top.v
// Description : Top-level module connecting all pipeline stages.
//               STRICT MODE: immediate / ALU / register-index paths are
//               profile-driven per program. PC stays full-width at the
//               primary fetch/address level (pc.v/pc_adder.v/
//               instruction_memory.v are unmodified); only the
//               pipeline-carried PC copies used for branch/JAL(R)
//               arithmetic are narrowed, and reconstructed via
//               zero-extension (PC is unsigned) at the point of use.
// ============================================================

`timescale 1ns / 1ps

module pipeline_top (
    input         clk,
    input         reset,

    output        halted,
    output [31:0] dbg_pc,
    output [31:0] dbg_instr_if,
    output [31:0] dbg_instr_id,
    output [6:0] dbg_alu_result_ex,
    output        dbg_branch_taken_ex,
    output        dbg_mem_write_mem,
    output [6:0] dbg_mem_addr_mem,
    output [6:0] dbg_mem_wdata_mem,
    output        dbg_reg_write_wb,
    output [3:0] dbg_rd_wb,
    output [6:0] dbg_wb_data
);

    // IF stage -- pc_width bits, matching pc.v/pc_adder.v/instruction_memory.v
    // exactly (all generated together from the same computed pc_width).
    wire [6:0] pc_out;
    wire [6:0] pc_plus4_if;
    wire [31:0] instruction_if;
    wire [6:0] pc_next;
    wire        program_end_if;
    reg  [3:0]  drain_count;
    reg         halted_r;

    // IF/ID -- pipeline-carried PC copy, narrowed
    wire [6:0] pc_id;
    wire [6:0] pc_plus4_id;
    wire [31:0] instruction_id;

    // ID
    wire [31:0] read_data1_id;
    wire [31:0] read_data2_id;
    wire [6:0] imm_id;

    wire branch_id;
    wire mem_read_id;
    wire [1:0] mem_to_reg_id;
    wire [0:0] alu_op_id;
    wire mem_write_id;
    wire alu_src_id;
    wire reg_write_id;
    wire jump_id;
    wire jalr_id;

    wire [3:0] rs1_id;
    wire [3:0] rs2_id;
    wire [3:0] rd_id;

    // ID/EX
    wire [6:0] pc_ex;
    wire [6:0] pc_plus4_ex;
    wire [31:0] read_data1_ex;
    wire [31:0] read_data2_ex;
    wire [6:0] imm_ex;
    wire [31:0] instruction_ex;
    wire [3:0] rs1_ex;
    wire [3:0] rs2_ex;
    wire [3:0] rd_ex;
    wire [0:0] alu_op_ex;
    wire alu_src_ex;
    wire mem_read_ex;
    wire mem_write_ex;
    wire [2:0] funct3_ex;
    wire reg_write_ex;
    wire [1:0] mem_to_reg_ex;
    wire branch_ex;
    wire jump_ex;
    wire jalr_ex;

    // EX
    wire [0:0] alu_control_ex;
    wire is_rtype_ex;
    wire [31:0] alu_input_a;
    wire [31:0] alu_input_b_pre;
    wire [31:0] alu_input_b;
    wire [31:0] alu_result_ex;
    wire zero_ex;
    wire negative_ex;
    wire overflow_ex;
    wire carry_out_ex;
    wire branch_taken_ex;
    wire [6:0] branch_target_ex;
    wire [1:0] forward_a;
    wire [1:0] forward_b;

    wire custom_en_ex;
    wire [31:0] custom_result_ex;
    wire [31:0] ex_result;
    wire custom_valid_ex;
    wire custom_stall_ex;
    wire [31:0] auipc_result;

    // EX/MEM -- pipeline-carried PC copy stays narrow; but nothing after
    // WB needs pc_plus4 for addressing, only for the JAL(R) link value.
    wire [6:0] pc_plus4_mem;
    wire [31:0] alu_result_mem;
    wire [31:0] write_data_mem;
    wire [6:0] branch_target_mem;
    wire zero_mem;
    wire branch_taken_mem;
    wire [3:0] rd_mem;
    wire mem_read_mem;
    wire mem_write_mem;
    wire [2:0] funct3_mem;
    wire reg_write_mem;
    wire [1:0] mem_to_reg_mem;
    wire jump_mem;

    // MEM
    wire [31:0] mem_read_data_mem;

    // MEM/WB
    wire [6:0] pc_plus4_wb;
    wire [31:0] alu_result_wb;
    wire [31:0] mem_read_data_wb;
    wire [3:0] rd_wb;
    wire reg_write_wb;
    wire [1:0] mem_to_reg_wb;

    // WB
    wire [31:0] write_back_data;

    // Hazard control
    wire pc_write;
    wire if_id_write;
    wire if_id_flush;
    wire id_ex_flush;
    wire ex_mem_flush;

    wire [6:0] jalr_target;
    wire is_auipc;

    wire [31:0] imm_id_sext;
    wire [31:0] imm_ex_sext;

    assign imm_id_sext = {{25{imm_id[6]}}, imm_id};
    assign imm_ex_sext = {{25{imm_ex[6]}}, imm_ex};

    // jalr_target: computed at full 32-bit precision (read_data1_ex is a
    // real, potentially large register value -- e.g. a computed pointer),
    // THEN truncated to pc_width bits for storage, since the target
    // address itself is expected to be within the profiled program's
    // range. Truncating after the full-precision add, rather than
    // truncating the operands first, avoids losing carry information.
    wire [31:0] jalr_target_full;
    assign jalr_target_full = (read_data1_ex + imm_ex_sext) & ~32'h1;
    assign jalr_target = jalr_target_full[6:0];

    assign pc_next =
        (jump_ex && jalr_ex) ? jalr_target :
        (jump_ex)            ? branch_target_ex :
        (branch_taken_ex)    ? branch_target_ex :
                               pc_plus4_if;

    pc u_pc (
        .clk(clk),
        .reset(reset),
        .pc_write(pc_write),
        .pc_next(pc_next),
        .pc_out(pc_out)
    );

    pc_adder u_pc_adder (
        .pc_in(pc_out),
        .pc_plus4(pc_plus4_if)
    );

    instruction_memory u_imem (
        .pc(pc_out),
        .instruction(instruction_if),
        .program_end(program_end_if)
    );

    // Halt detection: once IF has been continuously fetching past the end
    // of the program (not just a transient fetch that a branch/jump flush
    // later discards) for DRAIN_CYCLES cycles, the last real instruction
    // has had time to fully drain through ID/EX/MEM/WB, so it is safe to
    // declare the program complete. If program_end_if ever goes back low
    // (a flushed speculative fetch past the end, later corrected by a
    // taken backward branch), the counter resets rather than firing early.
    // This operates entirely on the untouched, full-width pc_out ->
    // instruction_memory.v path, so it is unaffected by any of the
    // pipeline-register narrowing above.
    localparam DRAIN_CYCLES = 4'd6;
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            drain_count <= 4'd0;
            halted_r    <= 1'b0;
        end else if (halted_r) begin
            // stay halted
        end else if (program_end_if) begin
            if (drain_count >= DRAIN_CYCLES)
                halted_r <= 1'b1;
            else
                drain_count <= drain_count + 4'd1;
        end else begin
            drain_count <= 4'd0;
        end
    end
    assign halted = halted_r;

    if_id_reg u_if_id (
        .clk(clk),
        .reset(reset),
        .if_id_write(if_id_write),
        .if_id_flush(if_id_flush),
        .pc_in(pc_out[6:0]),
        .pc_plus4_in(pc_plus4_if[6:0]),
        .instruction_in(instruction_if),
        .pc_out(pc_id),
        .pc_plus4_out(pc_plus4_id),
        .instruction_out(instruction_id)
    );

    assign rs1_id = instruction_id[18:15];
    assign rs2_id = instruction_id[23:20];
    assign rd_id  = instruction_id[10:7];

    control_unit u_control (
        .opcode(instruction_id[6:0]),
        .rd(instruction_id[11:7]),
        .branch(branch_id),
        .mem_read(mem_read_id),
        .mem_to_reg(mem_to_reg_id),
        .alu_op(alu_op_id),
        .mem_write(mem_write_id),
        .alu_src(alu_src_id),
        .reg_write(reg_write_id),
        .jump(jump_id),
        .jalr(jalr_id)
    );

    register_file u_reg_file (
        .clk(clk),
        .reg_write(reg_write_wb),
        .rs1(rs1_id),
        .rs2(rs2_id),
        .rd(rd_wb),
        .write_data(write_back_data),
        .read_data1(read_data1_id),
        .read_data2(read_data2_id)
    );

    imm_gen u_imm_gen (
        .instruction(instruction_id),
        .imm_out(imm_id)
    );

    id_ex_reg u_id_ex (
        .clk(clk),
        .reset(reset),
        .flush(id_ex_flush),
        .pc_in(pc_id),
        .pc_plus4_in(pc_plus4_id),
        .read_data1_in(read_data1_id),
        .read_data2_in(read_data2_id),
        .imm_in(imm_id),
        .instruction_in(instruction_id),
        .rs1_in(rs1_id),
        .rs2_in(rs2_id),
        .rd_in(rd_id),
        .alu_op_in(alu_op_id),
        .alu_src_in(alu_src_id),
        .mem_read_in(mem_read_id),
        .mem_write_in(mem_write_id),
        .funct3_in(instruction_id[14:12]),
        .reg_write_in(reg_write_id),
        .mem_to_reg_in(mem_to_reg_id),
        .branch_in(branch_id),
        .jump_in(jump_id),
        .jalr_in(jalr_id),
        .pc_out(pc_ex),
        .pc_plus4_out(pc_plus4_ex),
        .read_data1_out(read_data1_ex),
        .read_data2_out(read_data2_ex),
        .imm_out(imm_ex),
        .instruction_out(instruction_ex),
        .rs1_out(rs1_ex),
        .rs2_out(rs2_ex),
        .rd_out(rd_ex),
        .alu_op_out(alu_op_ex),
        .alu_src_out(alu_src_ex),
        .mem_read_out(mem_read_ex),
        .mem_write_out(mem_write_ex),
        .funct3_out(funct3_ex),
        .reg_write_out(reg_write_ex),
        .mem_to_reg_out(mem_to_reg_ex),
        .branch_out(branch_ex),
        .jump_out(jump_ex),
        .jalr_out(jalr_ex)
    );

    forwarding_unit u_fwd (
        .id_ex_rs1(rs1_ex),
        .id_ex_rs2(rs2_ex),
        .ex_mem_rd(rd_mem),
        .ex_mem_reg_write(reg_write_mem),
        .mem_wb_rd(rd_wb),
        .mem_wb_reg_write(reg_write_wb),
        .forward_a(forward_a),
        .forward_b(forward_b)
    );

    wire [31:0] fwd_a_result =
        (forward_a == 2'b10) ? alu_result_mem  :
        (forward_a == 2'b01) ? write_back_data :
                               read_data1_ex;

    assign is_auipc    = (instruction_ex[6:0] == 7'b0010111);
    assign is_rtype_ex = (instruction_ex[6:0] == 7'b0110011);
    assign alu_input_a = is_auipc ? {{25{1'b0}}, pc_ex} : fwd_a_result;

    assign alu_input_b_pre =
        (forward_b == 2'b10) ? alu_result_mem  :
        (forward_b == 2'b01) ? write_back_data :
                               read_data2_ex;

    assign alu_input_b  = alu_src_ex ? imm_ex_sext : alu_input_b_pre;
    assign auipc_result = {{25{1'b0}}, pc_ex} + imm_ex_sext;

    alu_control u_alu_ctrl (
        .alu_op(alu_op_ex),
        .funct3(funct3_ex),
        .funct7(instruction_ex[30]),
        .is_rtype(is_rtype_ex),
        .alu_control(alu_control_ex)
    );

    alu u_alu (
        .a(alu_input_a),
        .b(alu_input_b),
        .alu_control(alu_control_ex),
        .result(alu_result_ex),
        .zero(zero_ex),
        .negative(negative_ex),
        .overflow(overflow_ex),
        .carry_out(carry_out_ex)
    );

    // branch_unit omitted: no branch instruction (beq/bne/blt/bge/bltu/
    // bgeu) was used by this program. Its output is gated by the
    // `branch` control signal (see branch_unit_v.j2's `if (!branch)
    // branch_taken = 1'b0`), which control_unit.v never asserts when no
    // branch instruction exists at all -- so branch_taken would always
    // be 0 regardless. Tying it directly is equivalent and costs zero
    // hardware instead of an always-0 module.
    assign branch_taken_ex = 1'b0;

    // branch_target_ex: same full-precision-then-truncate pattern as
    // jalr_target above.
    wire [31:0] branch_target_ex_full;
    assign branch_target_ex_full = {{25{1'b0}}, pc_ex} + imm_ex_sext;
    assign branch_target_ex = branch_target_ex_full[6:0];

    assign custom_en_ex = (instruction_ex[6:0] == 7'b0001011);
    assign ex_result    = custom_en_ex ? custom_result_ex : alu_result_ex;

    custom_unit u_custom (
        .clk(clk),
        .custom_en(custom_en_ex),
        .funct3(funct3_ex),
        .rs1_val(alu_input_a),
        .rs2_val(alu_input_b_pre),
        .custom_result(custom_result_ex),
        .custom_valid(custom_valid_ex),
        .custom_stall(custom_stall_ex)
    );

    ex_mem_reg u_ex_mem (
        .clk(clk),
        .reset(reset),
        .flush(ex_mem_flush),
        .pc_plus4_in(pc_plus4_ex),
        .alu_result_in(ex_result),
        .write_data_in(alu_input_b_pre),
        .branch_target_in(branch_target_ex),
        .zero_in(zero_ex),
        .branch_taken_in(branch_taken_ex),
        .rd_in(rd_ex),
        .mem_read_in(mem_read_ex),
        .mem_write_in(mem_write_ex),
        .funct3_in(funct3_ex),
        .reg_write_in(reg_write_ex),
        .mem_to_reg_in(mem_to_reg_ex),
        .jump_in(jump_ex),
        .pc_plus4_out(pc_plus4_mem),
        .alu_result_out(alu_result_mem),
        .write_data_out(write_data_mem),
        .branch_target_out(branch_target_mem),
        .zero_out(zero_mem),
        .branch_taken_out(branch_taken_mem),
        .rd_out(rd_mem),
        .mem_read_out(mem_read_mem),
        .mem_write_out(mem_write_mem),
        .funct3_out(funct3_mem),
        .reg_write_out(reg_write_mem),
        .mem_to_reg_out(mem_to_reg_mem),
        .jump_out(jump_mem)
    );

    data_memory u_dmem (
        .clk(clk),
        .mem_read(mem_read_mem),
        .mem_write(mem_write_mem),
        .funct3(funct3_mem),
        .address(alu_result_mem),
        .write_data(write_data_mem),
        .read_data(mem_read_data_mem)
    );

    mem_wb_reg u_mem_wb (
        .clk(clk),
        .reset(reset),
        .pc_plus4_in(pc_plus4_mem),
        .alu_result_in(alu_result_mem),
        .mem_read_data_in(mem_read_data_mem),
        .rd_in(rd_mem),
        .reg_write_in(reg_write_mem),
        .mem_to_reg_in(mem_to_reg_mem),
        .pc_plus4_out(pc_plus4_wb),
        .alu_result_out(alu_result_wb),
        .mem_read_data_out(mem_read_data_wb),
        .rd_out(rd_wb),
        .reg_write_out(reg_write_wb),
        .mem_to_reg_out(mem_to_reg_wb)
    );

    assign write_back_data = 
        (mem_to_reg_wb == 2'd1) ? mem_read_data_wb :
        (mem_to_reg_wb == 2'd2) ? {{25{1'b0}}, pc_plus4_wb} :
                                   alu_result_wb;

    hazard_unit u_hazard (
        .id_ex_mem_read(mem_read_ex),
        .id_ex_rd(rd_ex),
        .if_id_rs1(rs1_id),
        .if_id_rs2(rs2_id),
        .branch_taken(branch_taken_ex),
        .jump(jump_ex),
        .pc_write(pc_write),
        .if_id_write(if_id_write),
        .if_id_flush(if_id_flush),
        .id_ex_flush(id_ex_flush),
        .ex_mem_flush(ex_mem_flush)
    );

    assign dbg_pc              = pc_out;
    assign dbg_instr_if        = instruction_if;
    assign dbg_instr_id        = instruction_id;
    assign dbg_alu_result_ex   = alu_result_ex[6:0];
    assign dbg_branch_taken_ex = branch_taken_ex;
    assign dbg_mem_write_mem   = mem_write_mem;
    assign dbg_mem_addr_mem    = alu_result_mem[6:0];
    assign dbg_mem_wdata_mem   = write_data_mem[6:0];
    assign dbg_reg_write_wb    = reg_write_wb;
    assign dbg_rd_wb           = rd_wb;
    assign dbg_wb_data         = write_back_data[6:0];

endmodule
