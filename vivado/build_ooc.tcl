set proj_root "G:/asip_project/generated"
set part_name "xc7a12ticsg325-1L"
set out_dir   "$proj_root/viv_ooc"

file mkdir $out_dir

set src_list [list \
    "$proj_root/pipeline_top.v" \
    "$proj_root/alu.v" \
    "$proj_root/control_unit.v" \
    "$proj_root/alu_control.v" \
    "$proj_root/imm_gen.v" \
    "$proj_root/branch_unit.v" \
    "$proj_root/custom_unit.v" \
    "$proj_root/pc.v" \
    "$proj_root/pc_adder.v" \
    "$proj_root/instruction_memory.v" \
    "$proj_root/data_memory.v" \
    "$proj_root/register_file.v" \
    "$proj_root/if_id_reg.v" \
    "$proj_root/id_ex_reg.v" \
    "$proj_root/ex_mem_reg.v" \
    "$proj_root/mem_wb_reg.v" \
    "$proj_root/hazard_unit.v" \
    "$proj_root/forwarding_unit.v" \
]

proc synth_ooc {top_name src_list part_name out_dir} {
    puts "==== OOC synth for $top_name ===="

    read_verilog $src_list
    synth_design -top $top_name -part $part_name -mode out_of_context

    write_checkpoint -force "$out_dir/${top_name}_ooc.dcp"
    report_utilization -file "$out_dir/${top_name}_ooc_util.rpt"
    report_timing_summary -file "$out_dir/${top_name}_ooc_timing.rpt"

    close_design
}

synth_ooc "pipeline_top" $src_list $part_name $out_dir