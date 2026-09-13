import subprocess
import sys

commands = [
    [sys.executable, "-m", "compileall", "-q", "app", "tests", "alembic", "scripts"],
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "pytest", "-q"],
]

for command in commands:
    print("$", " ".join(command))
    result = subprocess.run(command)
    if result.returncode:
        raise SystemExit(result.returncode)
