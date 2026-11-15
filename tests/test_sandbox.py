"""The Python sandbox: legitimate analyses must work, escape attempts must fail.

These tests start the real worker process, so they exercise the actual isolation, not a mock.
"""

import base64
import os
import time

import pandas as pd
import pytest

from app_agents.tools.python_tool import PythonSandboxTool


@pytest.fixture(scope="module")
def tool():
    return PythonSandboxTool(timeout=20)


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "sales.csv"
    pd.DataFrame(
        {"region": ["north", "south", "north", "south"], "revenue": [10.0, 20.0, 30.0, 40.0]}
    ).to_csv(path, index=False)
    return str(path)


@pytest.fixture
def xlsx_file(tmp_path):
    path = tmp_path / "sales.xlsx"
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_excel(path, index=False)
    return str(path)


# --- legitimate analyses -------------------------------------------------------------------

def test_groupby_returns_output_and_dataframe(tool, csv_file):
    code = "data = pd.read_csv(file_path)\nresult = data.groupby('region')['revenue'].sum().reset_index()\nprint(result)"
    r = tool.execute(code, csv_file)
    assert r["success"], r["error"]
    assert "north" in r["output"] and "40.0" in r["output"]
    assert r["dataframe"] == [{"region": "north", "revenue": 40.0}, {"region": "south", "revenue": 60.0}]


def test_excel_files_can_be_read(tool, xlsx_file):
    r = tool.execute("df = pd.read_excel(file_path)\nprint(df['b'].sum())", xlsx_file)
    assert r["success"], r["error"]
    assert r["output"].strip() == "15"


def test_matplotlib_chart_is_returned_as_png(tool, csv_file):
    code = "df = pd.read_csv(file_path)\ndf.plot(x='region', y='revenue', kind='bar')\nplt.title('Revenue')"
    r = tool.execute(code, csv_file)
    assert r["success"], r["error"]
    assert len(r["images"]) == 1
    assert base64.b64decode(r["images"][0]).startswith(b"\x89PNG")


def test_seaborn_chart_works(tool, csv_file):
    r = tool.execute("df = pd.read_csv(file_path)\nsns.barplot(data=df, x='region', y='revenue')", csv_file)
    assert r["success"], r["error"]
    assert len(r["images"]) == 1


def test_user_errors_are_reported_not_raised(tool, csv_file):
    r = tool.execute("df = pd.read_csv(file_path)\nprint(df['missing'])", csv_file)
    assert not r["success"]
    assert "KeyError" in r["error"]


def test_syntax_errors_are_reported(tool):
    r = tool.execute("def broken(:")
    assert not r["success"] and "Syntax error" in r["error"]


def test_the_code_works_on_a_private_copy_of_the_file(tool, csv_file):
    before = open(csv_file).read()
    r = tool.execute("pd.DataFrame({'x': [1]}).to_csv(file_path)", csv_file)
    assert r["success"], r["error"]
    assert open(csv_file).read() == before


# --- validator (first filter) ----------------------------------------------------------------

@pytest.mark.parametrize("code", ["import os", "import subprocess", "eval('1')", "open('x')", "print(pd.__class__.__dict__)"])
def test_validator_rejects_obvious_abuse(tool, code):
    r = tool.execute(code)
    assert not r["success"] and "Security validation failed" in r["error"]


# --- escape attempts that get past the validator ---------------------------------------------

def test_the_environment_is_empty(tool, monkeypatch):
    monkeypatch.setenv("FAKE_SECRET", "not-a-real-key")
    r = tool.execute("print(pd.io.common.os.environ.get('FAKE_SECRET'))")
    assert "not-a-real-key" not in r["output"]
    assert r["output"].strip() == "None"


def test_files_outside_the_work_folder_cannot_be_read(tool):
    r = tool.execute("print(pd.read_csv('/etc/hostname', header=None).iloc[0, 0])")
    assert not r["success"]
    assert "Blocked by the sandbox" in r["error"]


def test_files_cannot_be_written_outside_the_work_folder(tool, tmp_path):
    target = tmp_path / "escaped.csv"
    r = tool.execute(f"pd.DataFrame({{'a': [1]}}).to_csv('{target}')")
    assert not r["success"]
    assert not target.exists()


def test_shell_commands_are_blocked(tool):
    r = tool.execute("print(pd.io.common.os.popen('echo shell-ran').read())")
    assert not r["success"]
    assert "shell-ran" not in r["output"]


def test_network_access_is_blocked(tool):
    r = tool.execute("print(pd.read_csv('http://127.0.0.1:9/data.csv'))")
    assert not r["success"]


# --- limits ------------------------------------------------------------------------------------

def test_an_infinite_loop_is_killed_at_the_timeout():
    quick = PythonSandboxTool(timeout=2)
    started = time.time()
    r = quick.execute("while True:\n    pass")
    assert not r["success"] and "timeout" in r["error"].lower()
    assert time.time() - started < 10


def test_memory_hogs_fail_instead_of_taking_the_machine_down(tool):
    r = tool.execute("x = np.ones(10**10)")
    assert not r["success"]


def test_stray_processes_do_not_outlive_the_call():
    quick = PythonSandboxTool(timeout=2)
    quick.execute("while True:\n    pass")
    assert not [p for p in os.listdir("/proc") if p.isdigit() and _is_worker(p)]


def _is_worker(pid):
    try:
        return b"sandbox_worker.py" in open(f"/proc/{pid}/cmdline", "rb").read()
    except OSError:
        return False
