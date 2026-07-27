// Auto-generated hazard_unit (register-index width matches REG_INDEX_WIDTH,
// same reasoning as forwarding_unit above). Logic is otherwise identical
// to the original hand-written version (3-stage branch/jump flush).
`timescale 1ns / 1ps

module hazard_unit (
    input             id_ex_mem_read,
    input      [3:0]  id_ex_rd,
    input      [3:0]  if_id_rs1,
    input      [3:0]  if_id_rs2,
    input             branch_taken,
    input             jump,
    output reg        pc_write,
    output reg        if_id_write,
    output reg        if_id_flush,
    output reg        id_ex_flush,
    output reg        ex_mem_flush
);

    always @(*) begin
        pc_write     = 1'b1;
        if_id_write  = 1'b1;
        if_id_flush  = 1'b0;
        id_ex_flush  = 1'b0;
        ex_mem_flush = 1'b0;

        if (id_ex_mem_read &&
            (id_ex_rd != 4'b0000) &&
            ((id_ex_rd == if_id_rs1) ||
             (id_ex_rd == if_id_rs2))) begin
            pc_write    = 1'b0;
            if_id_write = 1'b0;
            id_ex_flush = 1'b1;
        end

        // NOTE: ex_mem_flush is deliberately NOT asserted here, even
        // though an earlier version of this module did. At the cycle
        // branch_taken/jump resolves, EX holds the branch/jump
        // instruction ITSELF -- valid, and (for jal/jalr) about to
        // write a real return address to rd. Asserting ex_mem_flush at
        // this same cycle discards that instruction's own transition
        // into MEM, silently dropping its write-back before it ever
        // reaches the register file. Proven via simulation: a nested
        // function call's `jal ra, callee` had its return-address
        // write to ra discarded this way, so the caller's own later
        // `ret` used a stale, pre-call ra value instead and jumped to
        // the wrong place. Branches never exposed this because a
        // branch never has reg_write=1 in the first place, so
        // discarding its own MEM transition was always harmless by
        // coincidence -- jal/jalr do, so it wasn't. Only if_id_flush
        // and id_ex_flush are needed: they discard the two
        // speculatively-fetched, genuinely wrong-path instructions
        // that were fetched sequentially before the redirect was known
        // (currently sitting in IF and ID), which is the only actual
        // misprediction to clean up.
        if ((branch_taken || jump) && pc_write) begin
            if_id_flush  = 1'b1;
            id_ex_flush  = 1'b1;
        end
    end

endmodule
