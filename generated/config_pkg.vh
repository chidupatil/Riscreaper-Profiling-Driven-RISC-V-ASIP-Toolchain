`ifndef CONFIG_PKG_VH
`define CONFIG_PKG_VH

`define HAS_IMM_I      1
`define HAS_IMM_S      1
`define HAS_IMM_B      0
`define HAS_IMM_J      1

`define HAS_REGWRITE   1
`define HAS_MEMREAD    1
`define HAS_MEMWRITE   1
`define HAS_BRANCH     0
`define HAS_JUMP       1
`define HAS_CUSTOM     0

`define ALU_HAS_ADD    1
`define ALU_HAS_SUB    0
`define ALU_HAS_AND    0
`define ALU_HAS_OR     0
`define ALU_HAS_XOR    0
`define ALU_HAS_SLT    0

`endif
