"""Entry point of the Windows package (PyInstaller): the ``fleet-service`` command line."""

import sys

from fleet_service.cli import main

if __name__ == "__main__":
    sys.exit(main())
