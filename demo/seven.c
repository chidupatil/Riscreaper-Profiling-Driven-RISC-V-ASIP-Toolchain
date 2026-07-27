// seven.c
//
// A minimal RISCREAPER program. Edit this however you like, then run:
//   ./riscreaper build demo/seven.c
//
// CONSTRAINTS this toolchain expects:
//  - No standard library (-nostdlib -nostartfiles): no printf, malloc,
//    stdio.h, etc -- pure computation only.
//  - main() must return a value. Whatever main() returns ends up in
//    the a0/x10 register, which is exactly what RISCREAPER latches
//    and reports as your program's final result (see `result_valid`
//    / `result_data` in the generated hardware, or the "Return value"
//    line in simulation output).
//  - Base RV32I instructions are all supported. Four custom
//    instructions are also available via inline asm -- see the
//    commented-out example below.
//  - Global/static variables, local variables, loops, branches, and
//    nested function calls are all supported.
static inline unsigned int custom_mul(unsigned int a, unsigned int b) {
    unsigned int result;
    asm volatile (".insn r 0x0B, 0, 0, %0, %1, %2"
                  : "=r"(result)
                  : "r"(a), "r"(b));
                 
    return result;
}
int main(void) {
    volatile unsigned int a = 6;
    volatile unsigned int b = 7;
    volatile unsigned int result = custom_mul(a, b);
    return result;
}

