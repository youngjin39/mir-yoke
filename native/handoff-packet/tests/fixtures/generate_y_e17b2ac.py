"""Add retained-stream and surrogate observations from the pinned bootstrap."""
import json
import subprocess
import sys
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e17b2a.py").read_text().split("records = []")[0], scope)
a, root, wrapper = (scope[k] for k in ("a", "root", "wrapper"))
records = []
for case in ("retained-stdout", "surrogate"):
    for mode in ("activate", "finalize"):
        init = "self.output=sys.stdout; self.output.write('A')"
        body = "self.output.write('B')"
        if case == "surrogate":
            init = "pass"
            body = r"sys.stdout.write('\udcff|\\udcff|\ud800|é')"
        source = "import sys,os\nfrom mir.core.capabilities.manager import CapabilityError\n"
        source += f"class CapabilityManager:\n def __init__(self,*a,**kw): {init}\n"
        source += f" def sync(self,*a,**kw):\n  {body}\n  raise CapabilityError('refused')\n"
        source += " finalize = sync\n"
        work = root / f"{mode}-{case}"
        work.mkdir(exist_ok=True)
        r = dict(mode=mode, case=case, source=source, closing=True)
        out = subprocess.run([sys.executable, "-I", str(wrapper), json.dumps(r)],
                             cwd=work, env={"HOME": str(work), "PATH": "/usr/bin:/bin"},
                             capture_output=True, check=True)
        value = json.loads((work / "result.json").read_text())
        reason = value[1].pop("reason")
        expected = "AB" if case == "retained-stdout" else "\udcff|\\udcff|\ud800|é"
        assert reason == expected + ("ERROR: refused" if mode == "activate" else "")
        assert not out.stdout and out.stderr == (b"ERROR: refused\n" if mode == "finalize" else b"")
        value[1]["reason_wtf8"] = list(reason.encode("utf-8", "surrogatepass"))
        records.append(r | dict(stdout=list(out.stdout), stderr=list(out.stderr), value=value))
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n')
