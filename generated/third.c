int mix_and_sum(int a, int b) {
    int x3 = a * 3;
    int x4 = b * 5;

    return x3 + x4;
}

int main(void) {
    // Use different constants so the compiler keeps everything “interesting”
    return mix_and_sum(1, 2);
}
