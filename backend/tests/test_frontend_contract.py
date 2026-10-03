"""Every API call the frontend makes must have a matching backend route."""

import re
from pathlib import Path

import pytest

APP_JSX = Path(__file__).resolve().parents[2] / "frontend" / "src" / "App.jsx"


@pytest.mark.skipif(not APP_JSX.exists(), reason="frontend not present")
def test_every_frontend_request_has_a_backend_route(client):
    source = APP_JSX.read_text(encoding="utf-8")
    calls = re.findall(r"axios\.(get|post|patch|put|delete)\(`\$\{API\}([^`]+)`", source)
    assert calls, "no axios calls found - did App.jsx change?"

    from main import app
    # The OpenAPI schema is the stable, public list of routes.
    routes = {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}

    for method, path in calls:
        # /emails/${email.id}/read  ->  /emails/{email_id}/read
        template = re.sub(r"\$\{[^}]+\}", "{email_id}", path)
        assert (method.upper(), template) in routes, f"frontend calls {method.upper()} {path} but no route matches"
