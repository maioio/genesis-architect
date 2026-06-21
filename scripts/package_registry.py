"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/package_registry.py instead."""
import sys
from genesis_architect.core.package_registry import query_package, score_packages

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: package_registry.py <package> <pypi|npm|crates> [<package> <ecosystem> ...]")
        sys.exit(1)

    pairs = []
    i = 0
    while i + 1 < len(args):
        pairs.append((args[i], args[i + 1]))
        i += 2

    signals = score_packages(pairs)
    for s in signals:
        print(s.signal_line)
