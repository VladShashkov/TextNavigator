import subprocess, sys
from pathlib import Path


def test_eval_passes():
    """Эталонный набор eval/cases.json проходит целиком, выдуманных значений нет."""
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "eval/run_eval.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
