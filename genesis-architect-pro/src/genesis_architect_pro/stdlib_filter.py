"""
stdlib_filter.py - Genesis Architect PRO

Complete Python 3.11+ standard library name set for import classification.
Used to distinguish project-internal imports from stdlib/third-party ones.

is_stdlib_import(name) is the public API; everything else is implementation detail.
"""

PYTHON_STDLIB: frozenset[str] = frozenset({
    # --- builtins / internals ---
    # __future__ belongs here: it is a real stdlib module, and omitting it made
    # `from __future__ import annotations` - present in almost every modern
    # module - register as a third-party dependency, so it topped the
    # dependency report of any codebase that uses it.
    "__future__", "_thread", "builtins",
    # --- A ---
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore", "atexit",
    # --- B ---
    "base64", "bdb", "binascii", "bisect",
    # --- C ---
    "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop",
    "collections", "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "csv", "ctypes", "curses",
    # --- D ---
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis", "distutils", "doctest",
    # --- E ---
    "email", "encodings", "enum", "errno",
    # --- F ---
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "fractions", "ftplib",
    "functools",
    # --- G ---
    "gc", "getopt", "getpass", "gettext", "glob", "grp", "gzip",
    # --- H ---
    "hashlib", "heapq", "hmac", "html", "http",
    # --- I ---
    "idlelib", "imaplib", "imghdr", "importlib", "inspect", "io", "ipaddress", "itertools",
    # --- J ---
    "json",
    # --- K ---
    "keyword",
    # --- L ---
    "linecache", "locale", "logging", "lzma",
    # --- M ---
    "mailbox", "marshal", "math", "mimetypes", "mmap", "multiprocessing",
    # --- N ---
    "netrc", "numbers",
    # --- O ---
    "operator", "os",
    # --- P ---
    "pathlib", "pdb", "pickle", "pkgutil", "platform", "pprint", "profile", "pty", "pwd",
    # --- Q ---
    "queue",
    # --- R ---
    "random", "re", "readline", "resource", "runpy",
    # --- S ---
    "sched", "secrets", "select", "shelve", "shlex", "shutil", "signal", "site",
    "smtplib", "socket", "socketserver", "sqlite3", "ssl", "stat", "statistics",
    "string", "struct", "subprocess", "sys", "sysconfig",
    # --- T ---
    "tarfile", "tempfile", "textwrap", "threading", "time", "timeit", "tkinter",
    "token", "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "types", "typing",
    # --- U ---
    "unicodedata", "unittest", "urllib", "uuid",
    # --- V ---
    "venv",
    # --- W ---
    "warnings", "wave", "weakref", "webbrowser",
    # --- X ---
    "xml", "xmlrpc",
    # --- Z ---
    "zipfile", "zipimport", "zlib", "zoneinfo",
})


def is_stdlib_import(module_name: str) -> bool:
    """
    Return True when module_name refers to a Python standard library module.

    Handles dotted names: is_stdlib_import("os.path") -> True
    Empty string returns False (not stdlib).
    """
    if not module_name:
        return False
    top_level = module_name.split(".")[0]
    return top_level in PYTHON_STDLIB
