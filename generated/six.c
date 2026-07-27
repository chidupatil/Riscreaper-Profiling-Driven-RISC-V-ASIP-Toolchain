// demo/many_regs.c

int mix_and_sum(int a, int b, int c, int d, int e, int f) {
    int x0 = a + b;
    int x1 = c - d;
    int x2 = e ^ f;
    int x3 = a * 3 + c;
    int x4 = b * 5 - e;
    int x5 = (x0 & x2) | (x1 ^ x4);
    int x6 = x3 + x5;
    int x7 = x6 - x2;

    return x0 + x1 + x2 + x3 + x4 + x5 + x6 + x7;
}

int main(void) {
    // Use different constants so the compiler keeps everything “interesting”
    return mix_and_sum(1, 2, 3, 4, 5, 6);
}
