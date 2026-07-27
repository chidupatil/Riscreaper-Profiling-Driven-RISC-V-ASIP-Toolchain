#define N 20

void bubble_sort(int *a, int n) {
    for (int i = 0; i < n - 1; i++) {
        for (int j = 0; j < n - 1 - i; j++) {
            if (a[j] > a[j + 1]) {
                int tmp = a[j];
                a[j] = a[j + 1];
                a[j + 1] = tmp;
            }
        }
    }
}

int checksum(int *a, int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum = sum + a[i] * (i + 1);
    }
    return sum;
}

int main(void) {
    int arr[N];
    arr[0]  = 87;  arr[1]  = 12;  arr[2]  = 45;  arr[3]  = 3;   arr[4]  = 99;
    arr[5]  = 21;  arr[6]  = 67;  arr[7]  = 34;  arr[8]  = 5;   arr[9]  = 78;
    arr[10] = 56;  arr[11] = 90;  arr[12] = 11;  arr[13] = 43;  arr[14] = 29;
    arr[15] = 8;   arr[16] = 71;  arr[17] = 62;  arr[18] = 17;  arr[19] = 38;

    bubble_sort(arr, N);
    return checksum(arr, N);
}
