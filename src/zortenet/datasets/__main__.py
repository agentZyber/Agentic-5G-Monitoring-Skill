"""CLI: python -m zortenet.datasets list | pull <name> [--root DIR]"""

from __future__ import annotations

import argparse

from zortenet.datasets.pull import DEFAULT_ROOT, pull
from zortenet.datasets.registry import list_datasets


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="zortenet-datasets")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List registered datasets with licence flags.")
    pull_parser = sub.add_parser("pull", help="Download (or print fetch guidance for) a dataset.")
    pull_parser.add_argument("name")
    pull_parser.add_argument("--root", default=DEFAULT_ROOT)

    args = parser.parse_args(argv)

    if args.command == "list":
        for ds in list_datasets():
            flag = "✅" if ds.verified else "◑"
            print(f"{flag} {ds.name:<12} {ds.size:<22} licence: {ds.license:<12} roles: {','.join(ds.roles)}")
            if ds.note:
                print(f"   ⚠ {ds.note}")
        return 0

    result = pull(args.name, root=args.root)
    if result["action"] == "guide":
        print(result["guide"])
    else:
        print(f"{result['dataset']}: {result['action']} → {result['path']}")
        if "reminder" in result:
            print(f"⚠ {result['reminder']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
