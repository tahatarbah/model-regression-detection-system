#!/usr/bin/env python3
"""End-to-end demo: train toy models, run baseline/candidate, gate, print URLs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / ".mrds" / "demo.db"


def run(cmd: list[str]) -> None:
    print("\n>", " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.check_call(cmd, cwd=ROOT, env=env)


def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()

    print("Training toy iris models…")
    run([sys.executable, str(ROOT / "examples" / "models.py")])

    db_args = ["--db", str(DB)]

    print("\n=== Classical: baseline @prod ===")
    run(
        [
            sys.executable,
            "-m",
            "mrds.cli.main",
            "run",
            "--suite",
            "examples/iris_classification.yaml",
            "--tag",
            "prod",
            "--label",
            "iris-good",
            *db_args,
        ]
    )

    print("\n=== Classical: gate with bad model (expect FAIL) ===")
    try:
        run(
            [
                sys.executable,
                "-m",
                "mrds.cli.main",
                "gate",
                "--suite",
                "examples/iris_classification.yaml",
                "--baseline",
                "@prod",
                "--model",
                str(ROOT / "examples" / "iris_bad.joblib"),
                "--label",
                "iris-bad",
                *db_args,
            ]
        )
    except subprocess.CalledProcessError as e:
        print(f"(expected non-zero exit: {e.returncode})")

    print("\n=== LLM: good mock baseline @prod ===")
    run(
        [
            sys.executable,
            "-m",
            "mrds.cli.main",
            "run",
            "--suite",
            "examples/llm_qa.yaml",
            "--tag",
            "prod",
            "--label",
            "llm-good",
            *db_args,
        ]
    )

    print("\n=== LLM: gate with bad mock suite (expect FAIL) ===")
    try:
        run(
            [
                sys.executable,
                "-m",
                "mrds.cli.main",
                "run",
                "--suite",
                "examples/llm_qa_bad.yaml",
                "--label",
                "llm-bad",
                "--tag",
                "candidate",
                *db_args,
            ]
        )
        run(
            [
                sys.executable,
                "-m",
                "mrds.cli.main",
                "gate",
                "--suite",
                "examples/llm_qa.yaml",
                "--baseline",
                "@prod",
                "--candidate",
                "@candidate",
                *db_args,
            ]
        )
    except subprocess.CalledProcessError as e:
        print(f"(expected non-zero exit: {e.returncode})")

    print("\nDemo data written to", DB)
    print("Start dashboard:")
    print(f"  mrds serve --db {DB}")
    print("  open http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
