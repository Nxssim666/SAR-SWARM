"""``fleet-service`` / ``python -m fleet_service``: see ``fleet_service.cli``."""

import sys

from fleet_service.cli import main as _cli_main


def main() -> None:
    """Console-script entry point."""
    sys.exit(_cli_main())


if __name__ == "__main__":
    main()
