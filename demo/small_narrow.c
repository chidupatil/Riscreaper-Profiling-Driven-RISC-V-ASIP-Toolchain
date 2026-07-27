// demo/small_narrow.c
// Values stay in 0..127 so data can be safely trimmed.

int main(void) {
    volatile unsigned char sum = 0;      // 8-bit range 0..255, we keep it small
    volatile unsigned char i   = 0;      // loop counter 0..127

    // Simple loop: sum = 0 + 1 + 2 + ... + 127
    for (i = 0; i < 128; i++) {
        sum = sum + i;
    }

    // Dummy use to keep sum live:
    if (sum == 0) {
        // This never happens; prevents compiler from optimizing sum away.
        return 1;
    }

    return sum;
}
