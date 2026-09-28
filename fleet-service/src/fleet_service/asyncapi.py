"""
The AsyncAPI 3.0 document of the WebSocket API, generated from ``api.ws_messages``
(ADR 0013, ADR 0020). Emitted as JSON (``docs/api/asyncapi.json``), which avoids a
runtime YAML dependency; JSON is valid YAML for tools that insist.
"""

from typing import Any

from pydantic.json_schema import models_json_schema

from fleet_service import __version__
from fleet_service.api.ws_messages import CLIENT_MESSAGES, SERVER_MESSAGES

REF = "#/components/schemas/{model}"


def asyncapi_document() -> dict[str, Any]:
    """Build the AsyncAPI document."""
    models = [*CLIENT_MESSAGES, *SERVER_MESSAGES]
    _, schema = models_json_schema(
        [(m, "validation" if m in CLIENT_MESSAGES else "serialization") for m in models],
        ref_template=REF,
    )
    schemas = schema.get("$defs", {})

    def message(model: type[Any]) -> dict[str, Any]:
        return {
            "name": model.__name__,
            "title": model.__name__,
            "summary": (model.__doc__ or "").strip().splitlines()[0],
            "contentType": "application/json",
            "payload": {"$ref": REF.format(model=model.__name__)},
        }

    messages = {m.__name__: message(m) for m in models}
    channel_ref = {"$ref": "#/channels/fleet"}
    return {
        "asyncapi": "3.0.0",
        "info": {
            "title": "SAR Fleet Service WebSocket API",
            "version": __version__,
            "description": (
                "Live telemetry, alerts, commands and control changes. Connect, send `auth` "
                "with a session token within 5 s, then `subscribe`. Close codes: 4400 "
                "malformed message, 4401 not authenticated or session ended, 4403 not "
                "permitted, 4408 timeout, 4429 too slow (reconnect and resync)."
            ),
        },
        "servers": {
            "station": {
                "host": "{station}",
                "protocol": "wss",
                "pathname": "/api/v1/ws",
                "description": "The ground station, behind its gateway (ADR 0016).",
                "variables": {"station": {"default": "localhost"}},
            }
        },
        "channels": {
            "fleet": {
                "address": "/api/v1/ws",
                "messages": {name: {"$ref": f"#/components/messages/{name}"} for name in messages},
            }
        },
        "operations": {
            "receiveFromConsole": {
                "action": "receive",
                "channel": channel_ref,
                "summary": "Messages a console sends to the station.",
                "messages": [
                    {"$ref": f"#/channels/fleet/messages/{m.__name__}"} for m in CLIENT_MESSAGES
                ],
            },
            "sendToConsole": {
                "action": "send",
                "channel": channel_ref,
                "summary": "Messages the station sends to a console.",
                "messages": [
                    {"$ref": f"#/channels/fleet/messages/{m.__name__}"} for m in SERVER_MESSAGES
                ],
            },
        },
        "components": {"messages": messages, "schemas": schemas},
    }
