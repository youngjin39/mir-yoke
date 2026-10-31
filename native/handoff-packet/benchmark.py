"""Cold-process latency for the native proof of concept (run from repository root)."""
from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_mechanical_handoff import HANDLER, PROMPT  # noqa: E402

BINARY = ROOT / 'native/handoff-packet/target/release/handoff-packet'
results = []
for label, tool, prompt in [('Read', 'Read', PROMPT + '\nNo commands.'),
                             ('Bash x', 'Bash', 'x'),
                             ('ordinary Bash', 'Bash', 'Inspect the repository.'),
                             ('handoff deny', 'Bash', PROMPT + '\nNo commands.')]:
    raw = json.dumps(dict(hook_event_name='PreToolUse', tool_name=tool,
                          prompt=prompt, tool_input={'command': 'pwd'})).encode()
    timings = {'Python': [], 'Rust': []}
    for _ in range(30):
        for implementation, command in [('Python', ["python3", str(HANDLER)]),
                                        ('Rust', [str(BINARY), str(HANDLER)])]:
            start = time.perf_counter_ns()
            result = subprocess.run(command, input=raw, capture_output=True, timeout=10)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            assert result.returncode == (2 if label == 'handoff deny' else 0)
            timings[implementation].append(elapsed)
    for implementation, samples in timings.items():
        results.append(dict(fixture=label, implementation=implementation, samples=len(samples),
                            median_ms=round(statistics.median(samples), 3),
                            p90_ms=round(sorted(samples)[math.ceil(0.9 * len(samples)) - 1], 3)))
print(json.dumps(results, indent=2))
