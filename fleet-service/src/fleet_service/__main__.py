"""``fleet-service`` / ``python -m fleet_service``: serve the API with uvicorn."""

import uvicorn

from fleet_service.config import get_settings


def main() -> None:
    """Start the server on the configured host and port."""
    settings = get_settings()
    uvicorn.run(
        "fleet_service.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,  # create_app configures logging
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
