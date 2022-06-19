"""APIModel CLI."""

import argparse
import json
import sys

from . import generator

parser: argparse.ArgumentParser = argparse.ArgumentParser()
parser.description = """
Generate API models from JSON data.

The definitions will often not be enough to make fully-usable client models, but they are enough as a starting point.
""".strip()

parser.add_argument(
    "-i",
    "--input",
    help="Input JSON file",
    type=argparse.FileType("r", encoding="utf-8"),
    default=sys.stdin,
)
parser.add_argument(
    "-o",
    "--output",
    help="Output python file",
    type=argparse.FileType("w", encoding="utf-8"),
    default=sys.stdout,
)


def main() -> None:
    """Generate API models from JSON data."""
    args = parser.parse_args()

    data = json.load(args.input or sys.stdin)
    code = generator.generate_models(data)
    args.output.write(code)


if __name__ == "__main__":
    main()
