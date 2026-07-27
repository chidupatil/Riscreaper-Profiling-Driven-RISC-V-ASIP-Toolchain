static inline unsigned int custom_mul(unsigned int a, unsigned int b) {
    unsigned int result;
    asm volatile (".insn r 0x0B, 0, 0, %0, %1, %2"
                  : "=r"(result)
                  : "r"(a), "r"(b));
    return result;
}
 
int main(void) {
    volatile unsigned int a = 124;
    volatile unsigned int b = 67;
    volatile unsigned int result = custom_mul(a, b);
 
    return result;
}
 
