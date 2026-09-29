"""
Wait until MediaMTX serves every mock stream (sim/video/compose.yaml); exit 1 otherwise.

A stream counts once its path is ready with an H.264 track. Standard library only.

    python3 sim/video/check.py --streams 4 [--api http://127.0.0.1:9997] [--timeout 60]
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def ready_paths(api: str) -> dict[str, list[str]]:
    """Ready paths and their track codecs, from the MediaMTX API."""
    with urllib.request.urlopen(f"{api}/v3/paths/list", timeout=5) as response:  # noqa: S310
        items = json.load(response).get("items", [])
    found = {}
    for item in items:
        if item.get("ready"):
            # MediaMTX 1.x lists tracks as codec names ("H264"), newer ones as objects.
            tracks = [t if isinstance(t, str) else t.get("codec", "") for t in item["tracks"]]
            found[item["name"]] = tracks
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--streams", type=int, default=4)
    parser.add_argument("--api", default="http://127.0.0.1:9997")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    expected = {f"aircraft-{n:02d}" for n in range(1, args.streams + 1)}
    deadline = time.monotonic() + args.timeout
    seen: dict[str, list[str]] = {}
    while time.monotonic() < deadline:
        try:
            seen = ready_paths(args.api)
        except (OSError, urllib.error.URLError, ValueError) as error:
            print(f"MediaMTX API not answering yet: {error}")  # noqa: T201
        else:
            h264 = {name for name, tracks in seen.items() if "H264" in tracks}
            if expected <= h264:
                print(f"all {len(expected)} streams ready with H.264: {sorted(expected)}")  # noqa: T201
                return 0
        time.sleep(2.0)
    print(f"::error title=Mock video::not every stream became ready; seen {seen}")  # noqa: T201
    return 1


if __name__ == "__main__":
    sys.exit(main())
