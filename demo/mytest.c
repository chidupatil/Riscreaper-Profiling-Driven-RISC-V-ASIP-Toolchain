int main(void) {
    volatile int a = 17;
    volatile int b = 5;
 
    volatile int product   = a * b;        // 85
    volatile int quotient  = product / b;  // 17
    volatile int remainder = a % b;        // 2
 
    volatile int result = quotient + remainder;  // 19
 
    return result;
}