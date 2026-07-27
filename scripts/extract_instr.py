import json
import re
from pathlib import Path

dump_path = Path("build/kernel.dump")
out_path = Path("build/instructions.json")

pseudo_map = {
    "nop": "addi",
    "mv": "addi",
    "li": "addi",
}

used = []
seen = set()

line_re = re.compile(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-zA-Z0-9._]+)")

for line in dump_path.read_text().splitlines():
    match = line_re.match(line)
    if not match:
        continue

    mnemonic = match.group(1).lower()
    mnemonic = pseudo_map.get(mnemonic, mnemonic)

    if mnemonic not in seen:
        seen.add(mnemonic)
        used.append(mnemonic)

result = {
    "used_instructions": used
}

out_path.write_text(json.dumps(result, indent=2))
print(f"Wrote {out_path}")
print(json.dumps(result, indent=2))
