# utils/renderers.py
"""
Standard response envelope for every API response.

Success:  {"success": true,  "data": <payload>,  "message": <str|null>}
Error:    {"success": false, "error": <str>,      "errors": <list|null>}

The renderer inspects the response status code to decide which envelope
to use, so view code never has to wrap manually.
"""
from __future__ import annotations

from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response


class GrammifyJSONRenderer(JSONRenderer):
    """Wrap every DRF response in a consistent envelope."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if renderer_context is None:
            return super().render(data, accepted_media_type, renderer_context)

        response: Response = renderer_context.get("response")
        if response is None:
            return super().render(data, accepted_media_type, renderer_context)

        status_code: int = response.status_code
        is_success = 200 <= status_code < 300

        if is_success:
            # Some endpoints return data with a top-level "message" key.
            message = None
            if isinstance(data, dict):
                message = data.pop("message", None)
            wrapped = {"success": True, "data": data}
            if message:
                wrapped["message"] = message
        else:
            # DRF error format: {"detail": "..."} or {"field": ["error"]}
            wrapped = _build_error_envelope(data)

        return super().render(wrapped, accepted_media_type, renderer_context)


def _build_error_envelope(data) -> dict:
    """Convert DRF error data into our standard error envelope."""
    if isinstance(data, dict):
        # Single "detail" message (auth errors, permission denied, etc.)
        if "detail" in data and len(data) == 1:
            return {"success": False, "error": str(data["detail"])}

        # Field validation errors → flatten into errors list
        errors = []
        error_msg = "Validation failed."
        for field, messages in data.items():
            if field == "non_field_errors":
                if isinstance(messages, list):
                    error_msg = messages[0] if messages else error_msg
                    errors.extend(str(m) for m in messages)
            elif isinstance(messages, list):
                errors.extend(f"{field}: {m}" for m in messages)
            else:
                errors.append(f"{field}: {messages}")
        return {"success": False, "error": error_msg, "errors": errors or None}

    if isinstance(data, list):
        return {"success": False, "error": "An error occurred.", "errors": [str(d) for d in data]}

    return {"success": False, "error": str(data)}
