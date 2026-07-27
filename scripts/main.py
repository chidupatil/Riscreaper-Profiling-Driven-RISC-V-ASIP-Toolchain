import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

steps = [
    ["python", "scripts/extract_instr.py"],
    ["python", "scripts/feature_map.py"],
    ["python", "scripts/generate_rtl.py"]
]

for cmd in steps:
    print(f"\n>>> Running: {' '.join(cmd)}")
    result = subprocess.run(" ".join(cmd), shell=True, cwd=project_root)
    if result.returncode != 0:
        print(f"Step failed: {' '.join(cmd)}")
        sys.exit(result.returncode)

print("\nAll steps completed successfully.")
