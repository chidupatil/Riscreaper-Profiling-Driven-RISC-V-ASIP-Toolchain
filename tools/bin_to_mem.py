from pathlib import Path
import sys

if len(sys.argv) != 3:
    print("Usage: python3 tools/bin_to_mem.py <input.bin> <output.mem>")
    sys.exit(1)

infile = Path(sys.argv[1])
outfile = Path(sys.argv[2])

data = infile.read_bytes()
data += b"\x00" * ((4 - len(data) % 4) % 4)

with open(outfile, "w") as f:
    for i in range(0, len(data), 4):
        word = int.from_bytes(data[i:i+4], "little")
        f.write(f"{word:08x}\n")
