#!/usr/bin/env python3
import argparse
from typing import Dict, List
import sys

from sonar.sonar import process_image


def convert_parser_arguments_to_key_value(parameters: List[str]) -> Dict[str, str]:
    """Converts a list of parameters passed to `ArgumentParser` into a dictionary.

    `parser.parse_args` will convert a series of arguments like:

    `sonar.py -p key1=value1 -p key2=value2`

    Into a list with each one of the entries as strings:

    `["key1=value1", "key2=value2"]`

    This function will convert this List into a Dict of (key, value).

    >>> convert_parser_arguments_to_key_value(["a=1", "b=2"])
    {"a": "1", "b": "2"}
    """
    if parameters is None:
        return {}

    d = {}

    for p in parameters:
        entry = p[0].split("=")
        d[entry[0]] = entry[1]

    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("-p", dest="parameters", nargs=1, action="append")
    parser.add_argument("--pipeline", default=False, action="store_true")
    parser.add_argument("--skip-tags", default="", type=str)
    parser.add_argument("--include-tags", default="", type=str)
    parser.add_argument("--inventory", default="inventory.yaml", type=str)

    args = parser.parse_args()

    build_args = convert_parser_arguments_to_key_value(args.parameters)

    process_image(args.image, args.skip_tags, args.include_tags, args.pipeline, build_args, args.inventory)


if __name__ == "__main__":
    sys.exit(main())
