"""Schema refusals must not launch the Python reference."""
import subprocess
import sys

import pytest
from test_mir_mcp_native_core import SCRIPT, native, request, run, wire  # noqa: F401


@pytest.mark.parametrize('name,args', [('unknown', {}), (False, {}), ('ontology_lookup', [])])
def test_schema_refusal_without_python(native, tmp_path, name, args):  # noqa: F811
    payload = wire(request('tools/call', {'name': name, 'arguments': args}))
    expected = run([sys.executable, '-I', '-B', str(SCRIPT)], payload)
    actual = subprocess.run([native[0], '--reference-python', str(tmp_path / 'absent'),
                             '--reference-script', str(SCRIPT)], input=payload,
                            capture_output=True, timeout=15)
    assert (actual.returncode, actual.stdout, actual.stderr) == (0, expected, b'')
