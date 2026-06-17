from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException


PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", "/app")).resolve()


@dataclass(frozen=True)
class ModuleResult:
    stdout: str
    stderr: str


def build_module_command(module: str, args: dict[str, Any]) -> list[str]:
    cmd: list[str] = [sys.executable, "-m", module]
    for flag, value in args.items():
        if isinstance(value, list):
            cmd.append(flag)
            cmd.extend(str(item) for item in value)
        elif value is None or value == "":
            continue
        else:
            cmd.extend([flag, str(value)])
    return cmd


def run_module(module: str, args: dict[str, Any], timeout: int = 7200) -> ModuleResult:
    env = os.environ.copy()
    project_paths = [str(PROJECT_ROOT)]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        project_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(project_paths)

    completed = subprocess.run(
        build_module_command(module, args),
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if completed.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "module": module,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )
    return ModuleResult(stdout=completed.stdout, stderr=completed.stderr)


def parse_result(stdout: str) -> dict[str, Any]:
    clean = stdout.strip()
    if not clean:
        return {}
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        parsed = ast.literal_eval(clean.splitlines()[-1])
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail=f"Pipeline result is not a dict: {parsed!r}")
    return parsed
