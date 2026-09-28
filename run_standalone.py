#!/usr/bin/env python3
"""
Run the standalone simulator from a source checkout, without installing anything.

Equivalent to ``python3 -m swarm_sar.standalone`` with the package installed;
see ``python3 run_standalone.py --help``.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'src' / 'swarm_sar'))

from swarm_sar.standalone import cli  # noqa: E402

if __name__ == '__main__':
    sys.exit(cli())
