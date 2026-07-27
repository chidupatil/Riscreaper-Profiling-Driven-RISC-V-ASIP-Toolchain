int main() {
    int a = 5;
    int b = 12;
    int i = 0;
    int result = 0;

    while (i < 4) {
        if ((a ^ b) == 9) {
            result = (a & b) | i;
        } else {
            result = (a | b) ^ i;
        }

        a = a + 1;
        b = b - 1;
        i = i + 1;
    }

    return result;
}
