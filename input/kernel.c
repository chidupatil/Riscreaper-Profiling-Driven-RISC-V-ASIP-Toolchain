int main() {
    int a = 12;
    int b = 30;
    int c = a + b;
    *((int*)4) = c;
    while (1) {}
    return 0;
}
