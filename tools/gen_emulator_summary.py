#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    argv = argv or sys.argv
    if len(argv) != 3:
        print("Usage: python3 gen_emulator_summary.py <bit_profile.json> <summary.json>")
        return 1

    src = Path(argv[1])
    dst = Path(argv[2])
    profile = json.loads(src.read_text(encoding="utf-8"))

    summary = {
        "instructions_used": sorted(profile.get("instructions_used", [])),
        "registers_read": sorted(profile.get("registers_read", [])),
        "registers_written": sorted(profile.get("registers_written", [])),
        "recommended_trim": profile.get("recommended_trim", {}),
        "halted_reason": profile.get("halted_reason", "unknown"),
        "steps": profile.get("steps", 0),
    }

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote generator-compatible summary to {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())