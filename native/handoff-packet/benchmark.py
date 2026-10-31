"""Cold-process latency for the native proof of concept (run from repository root)."""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_mechanical_handoff import (  # noqa: E402
    HANDLER,
    HANDLER_PYTHON,
    PINS,
    PROMPT,
    packet,
)

target = Path(os.environ.get('CARGO_TARGET_DIR', ROOT / 'native/handoff-packet/target'))
BINARY = target / 'release' / ('handoff-packet.exe' if os.name == 'nt' else 'handoff-packet')
CONTINUITY = ROOT / 'plugins/mir-lifecycle-hooks/hooks/runtime_continuity.py'
scratch = tempfile.TemporaryDirectory(prefix='stop-benchmark-', dir=target)
repo = Path(scratch.name)
(repo / '.git').mkdir()
(repo / 'scripts').mkdir()
(repo / 'scripts/mir_ontology.py').write_text(f'print({PINS!r})\n', encoding='utf-8')
transcript = repo / 'session.jsonl'
transcript.write_text(json.dumps({'type': 'user', 'message': {'content': PROMPT}}) + '\n',
                      encoding='utf-8')
stop_bodies = {'Stop no packet': 'Reading the sources.',
               'Stop valid': packet(),
               'Stop defective': packet().replace(PINS, '')}
results = []
for label, tool, prompt in [('Read', 'Read', PROMPT + '\nNo commands.'),
                             ('Bash x', 'Bash', 'x'),
                             ('ordinary Bash', 'Bash', 'Inspect the repository.'),
                             ('handoff deny', 'Bash', PROMPT + '\nNo commands.'),
                             ('submit ordinary', '', 'Inspect the repository.'),
                             ('submit forbidden', '', PROMPT + '\nNo commands.'),
                             ('SessionStart', '', '')] + [
                                 (name, '', PROMPT) for name in stop_bodies]:
    raw = json.dumps(dict(hook_event_name='PreToolUse', tool_name=tool,
                          prompt=prompt, tool_input={'command': 'pwd'})).encode()
    if not tool:
        raw = json.dumps(dict(hook_event_name='UserPromptSubmit', prompt=prompt)).encode()
    if label in stop_bodies:
        raw = json.dumps(dict(hook_event_name='Stop', cwd=str(repo),
                              transcript_path=str(transcript), stop_hook_active=False,
                              last_assistant_message=stop_bodies[label])).encode()
    reference = CONTINUITY if label == 'SessionStart' else HANDLER
    native = (BINARY.with_name('runtime-continuity' + BINARY.suffix)
              if label == 'SessionStart' else BINARY)
    timings = {'Python': [], 'Rust': []}
    for _ in range(30):
        outputs = []
        for implementation, command in [('Python', [HANDLER_PYTHON, str(reference)]),
                                        ('Rust', [str(native), str(reference)])]:
            start = time.perf_counter_ns()
            result = subprocess.run(command, input=raw, capture_output=True, timeout=10,
                                    env=dict(os.environ, MIR_HANDOFF_PYTHON=HANDLER_PYTHON,
                                             PYTHONUTF8='1'))
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            assert result.returncode == (2 if label == 'handoff deny' else 0)
            outputs.append((result.stdout, result.stderr, result.returncode))
            if label == 'Stop valid':
                assert result.stdout == b'' and result.stderr == b''
            elif label == 'Stop defective':
                assert json.loads(result.stdout)['decision'] == 'block'
            timings[implementation].append(elapsed)
        assert outputs[0] == outputs[1], label
    for implementation, samples in timings.items():
        results.append(dict(fixture=label, implementation=implementation, samples=len(samples),
                            median_ms=round(statistics.median(samples), 3),
                            p90_ms=round(sorted(samples)[math.ceil(0.9 * len(samples)) - 1], 3)))
scratch.cleanup()
print(json.dumps(results, indent=2))
