"""Checks how a DBOS workflow resumes after the process is killed mid-step.

Run with no arguments. The script starts itself twice as a child process:
  1. first child is killed (SIGKILL) while step 2 is sleeping;
  2. second child launches DBOS again, which recovers the pending workflow.
Every step appends a row to `spike_step_runs` when it starts, so the row counts show
what ran twice. Expected: step 1 once, step 2 twice, step 3 once.
"""

import os
import signal
import subprocess
import sys
import time

import psycopg
from dbos import DBOS, DBOSConfig, SetWorkflowID

DATABASE_URL = os.environ["DATABASE_URL"]
WORKFLOW_ID = f"resume-check-{os.environ.get('RESUME_CHECK_RUN', '0')}"


def record(step: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("INSERT INTO spike_step_runs (step, pid) VALUES (%s, %s)", (step, os.getpid()))


@DBOS.step()
def step_one() -> str:
    record("step_one")
    time.sleep(1)
    return "one"


@DBOS.step()
def step_two() -> str:
    record("step_two")
    time.sleep(1)
    if os.environ.get("CRASH_IN_STEP_TWO"):
        os.kill(os.getpid(), signal.SIGKILL)
    return "two"


@DBOS.step()
def step_three() -> str:
    record("step_three")
    return "three"


@DBOS.workflow()
def three_steps() -> list[str]:
    return [step_one(), step_two(), step_three()]


def child() -> None:
    config: DBOSConfig = {"name": "resume-check", "system_database_url": DATABASE_URL}
    DBOS(config=config)
    DBOS.launch()  # recovers workflows left pending by a previous process
    with SetWorkflowID(WORKFLOW_ID):
        print(f"  pid {os.getpid()} workflow result:", three_steps())
    DBOS.destroy()


def parent() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS spike_step_runs")
        connection.execute(
            "CREATE TABLE spike_step_runs (id serial PRIMARY KEY, step text, pid int, at timestamptz DEFAULT now())"
        )

    environment = {**os.environ, "RESUME_CHECK_RUN": str(int(time.time()))}
    command = [sys.executable, __file__, "child"]
    print("run 1 (killed inside step 2):")
    first = subprocess.run(command, env={**environment, "CRASH_IN_STEP_TWO": "1"})
    print(f"  exit code {first.returncode}")
    print("run 2 (recovery):")
    second = subprocess.run(command, env=environment)
    print(f"  exit code {second.returncode}")

    with psycopg.connect(DATABASE_URL) as connection:
        counts = dict(connection.execute("SELECT step, count(*) FROM spike_step_runs GROUP BY step").fetchall())
    print("step runs:", counts)
    expected = {"step_one": 1, "step_two": 2, "step_three": 1}
    print("RESUME OK" if counts == expected else f"RESUME UNEXPECTED, wanted {expected}")
    sys.exit(0 if counts == expected else 1)


if __name__ == "__main__":
    child() if sys.argv[1:] == ["child"] else parent()
