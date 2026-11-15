"""Child process that runs LLM-generated analysis code.

Started by ``PythonSandboxTool`` as ``python -I sandbox_worker.py <workdir>`` with an empty environment
(no API keys), the working directory set to a throw-away folder and a hard timeout enforced by the
parent. Inside, three layers apply before the generated code runs:

1. resource limits (CPU time, memory, file size);
2. a restricted ``__builtins__`` and an import hook that only allows pandas, numpy, matplotlib, seaborn;
3. an audit hook that refuses network, subprocess and exec calls, and limits file access to the
   work folder (read and write) plus the Python installation (read only).

This raises the bar a lot, but an in-process hook is not a hard security boundary. For untrusted,
multi-tenant use, also run the whole app in a container.
"""

import base64
import io
import json
import math
import os
import resource
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime

WORKDIR = os.path.realpath(sys.argv[1])
MAX_OUTPUT_CHARS = 100_000


def preload():
    """Import everything the analysis needs, before the sandbox closes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.font_manager  # noqa: F401  (builds the font cache while writing is still allowed)
    import matplotlib.pyplot as plt
    import numpy as np
    import openpyxl  # noqa: F401
    import pandas as pd
    import seaborn as sns

    return pd, np, plt, matplotlib, sns


def set_limits(cpu_seconds, memory_mb):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def install_audit_hook():
    mpl_dir = os.path.realpath(os.environ.get("MPLCONFIGDIR", WORKDIR))
    read_roots = tuple(
        sorted(
            {
                os.path.realpath(p)
                for p in (
                    WORKDIR,
                    sys.prefix,
                    sys.base_prefix,
                    sys.exec_prefix,
                    mpl_dir,
                    "/usr/share/zoneinfo",
                    "/etc/localtime",
                    "/dev/urandom",
                    "/dev/null",
                )
            }
        )
    )
    write_roots = (WORKDIR,)
    blocked_prefixes = (
        "socket.", "subprocess.", "ctypes.", "pty.", "shutil.", "smtplib.", "ftplib.", "imaplib.",
        "poplib.", "telnetlib.", "webbrowser.", "urllib.Request", "http.client.", "pickle.find_class",
        "os.exec", "os.fork", "os.spawn", "os.posix_spawn", "os.system", "os.kill", "os.chmod",
        "os.chown", "os.symlink", "os.link", "os.chdir", "os.chroot", "os.setuid", "os.setgid",
    )
    write_events = {"os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.utime", "os.truncate"}
    read_events = {"os.listdir", "os.scandir"}
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

    def inside(path, roots):
        return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)

    def resolve(path):
        return os.path.realpath(os.fsdecode(path))

    def deny(what):
        raise PermissionError(f"Blocked by the sandbox: {what}")

    def hook(event, args):
        if event.startswith(blocked_prefixes):
            deny(event)
        if event == "open":
            path, mode, flags = args
            if isinstance(path, int):
                return
            writing = bool(mode and any(c in str(mode) for c in "wax+")) or bool(
                isinstance(flags, int) and flags & write_flags
            )
            target = resolve(path)
            if not inside(target, write_roots if writing else read_roots):
                deny(f"{'writing' if writing else 'reading'} {target}")
        elif event in write_events:
            for arg in args:
                if isinstance(arg, (str, bytes, os.PathLike)) and not inside(resolve(arg), write_roots):
                    deny(f"{event} on {resolve(arg)}")
        elif event in read_events:
            arg = args[0] if args else None
            if isinstance(arg, (str, bytes, os.PathLike)) and not inside(resolve(arg), read_roots):
                deny(f"listing {resolve(arg)}")

    sys.addaudithook(hook)


def build_namespace(modules, file_path):
    pd, np, plt, matplotlib, sns = modules
    allowed = {"pandas": pd, "numpy": np, "matplotlib": matplotlib, "seaborn": sns}

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in allowed:
            return allowed[name]
        if name.startswith("matplotlib."):
            return matplotlib
        raise ImportError(f"Cannot import '{name}'. Only pandas, numpy, matplotlib, and seaborn are allowed.")

    builtins = {
        name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
        for name in (
            "print", "len", "range", "enumerate", "zip", "map", "filter", "sum", "min", "max", "abs",
            "round", "sorted", "list", "dict", "set", "tuple", "str", "int", "float", "bool",
            "isinstance", "any", "all", "reversed", "divmod", "pow", "repr", "slice",
            "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError",
            "RuntimeError", "ImportError", "ZeroDivisionError",
        )
    }
    builtins.update({"True": True, "False": False, "None": None, "__import__": safe_import})
    namespace = {"__builtins__": builtins, "__name__": "sandbox", "pd": pd, "pandas": pd, "np": np,
                 "numpy": np, "plt": plt, "matplotlib": matplotlib, "sns": sns, "seaborn": sns}
    if file_path:
        namespace["file_path"] = file_path
    return namespace


def json_safe_records(records, pd, np):
    def safe(value):
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

    return [{k: safe(v) for k, v in rec.items()} for rec in records or []]


def main():
    request = json.load(open(os.path.join(WORKDIR, "request.json"), encoding="utf-8"))
    modules = preload()
    pd, np, plt, _, _ = modules
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 2000)
    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.expand_frame_repr", False)

    set_limits(request["timeout"] + 5, request["memory_mb"])
    namespace = build_namespace(modules, request.get("file_path"))
    install_audit_hook()

    result = {"success": False, "output": "", "error": "", "dataframe": None, "images": []}
    out, err = io.StringIO(), io.StringIO()
    try:
        code = compile(request["code"], "<user_code>", "exec")
        with redirect_stdout(out), redirect_stderr(err):
            exec(code, namespace)  # noqa: S102  (this is the sandbox)
        result["output"] = out.getvalue()[:MAX_OUTPUT_CHARS]
        for key in ("df", "result"):
            if isinstance(namespace.get(key), pd.DataFrame):
                records = namespace[key].head(5).to_dict("records")
                result["dataframe"] = json_safe_records(records, pd, np)
                break
        for number in plt.get_fignums():
            buf = io.BytesIO()
            plt.figure(number).savefig(buf, format="png", bbox_inches="tight", dpi=100)
            result["images"].append(base64.b64encode(buf.getvalue()).decode("ascii"))
        plt.close("all")
        result["success"] = True
    except BaseException as exc:  # noqa: BLE001  (everything the generated code raises is reported)
        result["output"] = out.getvalue()[:MAX_OUTPUT_CHARS]
        message = f"{type(exc).__name__}: {exc}"
        result["error"] = f"Runtime error: {message}" + (f"\n{err.getvalue()}" if err.getvalue() else "")

    with open(os.path.join(WORKDIR, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
    sys.stdout.flush()
    os._exit(0)  # also stops any thread the generated code may have started


if __name__ == "__main__":
    main()
