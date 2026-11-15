"""
Python execution tool for LLM-generated analysis code.

The code never runs in the app's own process. ``PythonSandboxTool`` first checks it with an AST
validator (a fast, friendly first filter, not the security boundary), then runs it in a separate
locked-down process (see ``sandbox_worker.py``): empty environment, throw-away working folder,
resource limits, an audit hook for network/subprocess/file access, and a hard timeout that kills
the whole process group.
"""

import ast
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

WORKER_PATH = Path(__file__).with_name("sandbox_worker.py")
MAX_RESULT_BYTES = 20 * 1024 * 1024


class TimeoutException(Exception):
    """Exception raised when code execution times out"""
    pass


class CodeValidator(ast.NodeVisitor):
    """
    AST validator to block dangerous operations
    """
    
    # Dangerous functions/modules to block
    BLOCKED_NAMES: Set[str] = {
        'eval', 'exec', 'compile',
        'open', 'file', 'input', 'raw_input',
        'execfile', 'reload', 'breakpoint',
        'exit', 'quit', 'help',
    }
    
    # Dangerous modules to block
    BLOCKED_MODULES: Set[str] = {
        'os', 'sys', 'subprocess', 'socket', 'urllib',
        'requests', 'http', 'ftplib', 'telnetlib',
        'pickle', 'shelve', 'marshal', 'importlib',
    }
    
    def __init__(self):
        self.errors = []
    
    def visit_Import(self, node):
        """Check import statements"""
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if module_name in self.BLOCKED_MODULES:
                self.errors.append(f"Import of '{alias.name}' is not allowed")
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Check from-import statements"""
        if node.module:
            module_name = node.module.split('.')[0]
            if module_name in self.BLOCKED_MODULES:
                self.errors.append(f"Import from '{node.module}' is not allowed")
        self.generic_visit(node)
    
    def visit_Name(self, node):
        """Check for blocked names"""
        if node.id in self.BLOCKED_NAMES:
            self.errors.append(f"Use of '{node.id}' is not allowed")
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        """Check for dangerous attribute access"""
        # Block access to __builtins__, __globals__, etc.
        if isinstance(node.attr, str) and node.attr.startswith('__') and node.attr.endswith('__'):
            if node.attr not in {'__init__', '__str__', '__repr__'}:
                self.errors.append(f"Access to '{node.attr}' is not allowed")
        self.generic_visit(node)


class PythonSandboxTool:
    """Runs analysis code in an isolated child process and returns its result."""

    def __init__(self, timeout: int = 30, memory_mb: int = 4096):
        """
        Args:
            timeout: Maximum execution time in seconds; the process is killed after it.
            memory_mb: Address-space limit for the child process.
        """
        self.timeout = timeout
        self.memory_mb = memory_mb

    @staticmethod
    def _child_env(workdir: str, mpl_dir: str) -> Dict[str, str]:
        """Environment for the child: nothing from the parent, so no API key can leak."""
        return {
            "HOME": workdir,
            "MPLCONFIGDIR": mpl_dir,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
            "LANG": "C.UTF-8",
        }

    def execute(self, code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute Python code in a restricted child process

        Args:
            code: Python code to execute
            file_path: Path to the uploaded Excel/CSV file. The code sees a private copy.

        Returns:
            Dictionary containing:
                - success: bool
                - output: str (stdout)
                - error: str (if any)
                - dataframe: list of records (if a ``df`` or ``result`` DataFrame exists)
                - images: list of base64 encoded PNG images
        """
        result = {"success": False, "output": "", "error": "", "dataframe": None, "images": []}

        try:
            tree = ast.parse(code, filename="<user_code>", mode="exec")
        except SyntaxError as e:
            result["error"] = f"Syntax error: {str(e)}"
            logger.error("Syntax error: %s", e)
            return result

        validator = CodeValidator()
        validator.visit(tree)
        if validator.errors:
            result["error"] = "Security validation failed:\n" + "\n".join(validator.errors)
            logger.error("Validation errors: %s", validator.errors)
            return result

        mpl_dir = os.path.join(tempfile.gettempdir(), "excel-agent-mpl")
        os.makedirs(mpl_dir, mode=0o700, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="excel-agent-") as workdir:
            os.chmod(workdir, 0o700)
            private_file = None
            if file_path:
                if not os.path.isfile(file_path):
                    result["error"] = f"Input file not found: {file_path}"
                    return result
                private_file = os.path.join(workdir, "input" + Path(file_path).suffix.lower())
                shutil.copyfile(file_path, private_file)

            request = {
                "code": code,
                "file_path": private_file,
                "timeout": self.timeout,
                "memory_mb": self.memory_mb,
            }
            Path(workdir, "request.json").write_text(json.dumps(request), encoding="utf-8")

            proc = subprocess.Popen(
                [sys.executable, "-I", str(WORKER_PATH), workdir],
                cwd=workdir,
                env=self._child_env(workdir, mpl_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                _, stderr = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                result["error"] = f"Execution timeout: Code took longer than {self.timeout} seconds"
                logger.error("Timeout: code execution exceeded %s seconds", self.timeout)
                return result

            result_path = Path(workdir, "result.json")
            if not result_path.is_file() or result_path.stat().st_size > MAX_RESULT_BYTES:
                tail = (stderr or b"").decode("utf-8", "replace")[-500:]
                reason = "memory or CPU limit reached" if proc.returncode and proc.returncode < 0 else "worker failed"
                result["error"] = f"Sandbox error: {reason} (exit code {proc.returncode}). {tail}".strip()
                logger.error(result["error"])
                return result

            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            result.update(loaded)
            logger.info("Code executed: success=%s", result["success"])
            return result

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for OpenAI function calling
        
        Returns:
            Tool definition dictionary
        """
        return {
            "type": "function",
            "function": {
                "name": "execute_python_code",
                "description": "Execute Python code to analyze Excel/CSV data. Use pandas (pd), numpy (np), matplotlib (plt), and seaborn (sns). The uploaded file path is available as 'file_path' variable. Store results in 'df' or 'result' variable to return dataframes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute. Must use pandas to read the file (e.g., pd.read_excel(file_path) or pd.read_csv(file_path)). Store final dataframe in 'df' or 'result' variable."
                        }
                    },
                    "required": ["code"]
                }
            }
        }
