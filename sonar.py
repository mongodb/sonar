#!/usr/bin/env python3
import argparse
from typing import Dict
import sys

from sonar.sonar import process


def args_to_dict(parameters) -> Dict[str, str]:
    if parameters is None:
        return {}

    d = {}

    for p in parameters:
        entry = p[0].split("=")
        d[entry[0]] = entry[1]

    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image")
    parser.add_argument("-p", dest="parameters", nargs=1, action="append")
    parser.add_argument("--pipeline", default=False, action="store_true")
    parser.add_argument("--skip_tags", default="", type=str)
    args = parser.parse_args()

    print(args)
    d = args_to_dict(args.parameters)

    process(args.image, args.pipeline, d)


if __name__ == "__main__":
    sys.exit(main())
