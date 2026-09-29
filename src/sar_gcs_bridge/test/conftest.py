"""Make the bridge, the onboard package and its message fakes importable from a checkout."""

import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[2]
for path in (SRC / 'sar_gcs_bridge', SRC / 'swarm_sar', SRC / 'swarm_sar' / 'test'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
