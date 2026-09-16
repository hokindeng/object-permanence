"""Unified CLI for the object-permanence toolkit."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="object-permanence",
        description="object-permanence benchmark toolkit",
    )
    parser.add_argument(
        "--version", action="store_true", help="print version and exit"
    )
    sub = parser.add_subparsers(dest="command")

    from object_permanence.generator.core.generate import build_parser as gen_parser
    from object_permanence.generator.core.generate import main as gen_main

    gen_sub = sub.add_parser("generate", help="Generate video-to-video samples")
    gen_parser(gen_sub)
    gen_sub.set_defaults(func=gen_main)

    from object_permanence.generator.tools.audit import build_parser as audit_parser
    from object_permanence.generator.tools.audit import main as audit_main

    audit_sub = sub.add_parser("audit", help="Audit generated output")
    audit_parser(audit_sub)
    audit_sub.set_defaults(func=audit_main)

    args = parser.parse_args()

    if args.version:
        from object_permanence import __version__

        print(f"object-permanence {__version__}")
        return

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Propagate a handler's return value as the exit code (handlers may also
    # call sys.exit directly; SystemExit passes straight through).
    rc = args.func(args)
    if rc:
        sys.exit(int(rc))
