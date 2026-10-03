"""Offline structural check of render.yaml (Sprint 2A closeout).

Render's own validator (`render blueprints validate`) runs server-side and needs a Render login and a
workspace; this test is the offline complement. Allowed values below come from Render's public API
enums as generated in render-oss/cli (commit e864786, 2 Oct 2026: PaidPlan, PostgresPlans,
PostgresVersion, AutoDeployTrigger) and the Blueprint YAML reference (render.com/docs/blueprint-spec).
"""

from pathlib import Path

import yaml

BLUEPRINT = yaml.safe_load((Path(__file__).resolve().parent.parent / "render.yaml").read_text())
SERVICE_PLANS = {"starter", "standard", "pro", "pro_plus", "pro_max", "pro_ultra", "0.5c-512mb", "1c-2g", "2c-4g"}
POSTGRES_PLANS = {"0.1c-256mb", "0.5c-1g", "1c-2g", "1c-4g", "basic-256mb", "basic-1gb", "basic-4gb"}
AUTO_DEPLOY = {"commit", "checksPass", "off"}
SECRET_KEYS = {"ANTHROPIC_API_KEY", "DATABASE_URL", "DJANGO_SECRET_KEY"}


def _services():
    return {s["name"]: s for s in BLUEPRINT["services"]}


def test_top_level_shape_and_no_project_declaration():
    assert set(BLUEPRINT) == {"envVarGroups", "services", "databases"}  # no `projects:` → no duplicate project
    assert set(_services()) == {"room-by-room-web", "room-by-room-receipts"}
    assert [d["name"] for d in BLUEPRINT["databases"]] == ["room-by-room-db"]


def test_services_match_approved_configuration():
    web, worker = _services()["room-by-room-web"], _services()["room-by-room-receipts"]
    assert web["type"] == "web" and worker["type"] == "worker"
    for service in (web, worker):
        assert service["runtime"] == "python" and service["region"] == "frankfurt"
        assert service["plan"] == "0.5c-512mb" and service["plan"] in SERVICE_PLANS
        assert service["autoDeployTrigger"] == "off" and service["autoDeployTrigger"] in AUTO_DEPLOY
        assert "autoDeploy" not in service  # deprecated key not mixed in
        assert {"fromGroup": "room-by-room-shared"} in service["envVars"]
        database_url = [e for e in service["envVars"] if e.get("key") == "DATABASE_URL"]
        assert database_url == [{"key": "DATABASE_URL", "fromDatabase": {"name": "room-by-room-db",
                                                                           "property": "connectionString"}}]
    assert web["healthCheckPath"] == "/healthz/" and "migrate" in web["preDeployCommand"]
    assert worker["startCommand"] == "python manage.py process_receipts --watch --interval 3"
    assert 0 < worker["maxShutdownDelaySeconds"] <= 300


def test_database_matches_approved_configuration():
    db = BLUEPRINT["databases"][0]
    assert db["plan"] == "0.1c-256mb" and db["plan"] in POSTGRES_PLANS
    assert db["postgresMajorVersion"] == "16" and isinstance(db["postgresMajorVersion"], str)
    assert db["diskSizeGB"] == 1  # Render: 1 or a multiple of 5; can grow, never shrink
    assert db["storageAutoscalingEnabled"] is False
    assert db["region"] == "frankfurt" and db["ipAllowList"] == []  # private networking only


def test_no_secret_values_in_git_and_api_key_left_to_private_entry():
    group = BLUEPRINT["envVarGroups"][0]
    assert group["name"] == "room-by-room-shared"
    keys = {e["key"]: e for e in group["envVars"]}
    assert "ANTHROPIC_API_KEY" not in keys  # entered privately in the dashboard after creation
    assert keys["DJANGO_SECRET_KEY"] == {"key": "DJANGO_SECRET_KEY", "generateValue": True}
    for entry in group["envVars"]:
        if entry["key"] in SECRET_KEYS:
            assert "value" not in entry
    assert keys["RECEIPT_MODEL"]["value"] == "claude-haiku-4-5-20251001"
    assert keys["PRIVATE_STORAGE_BACKEND"]["value"] == "database"
    assert keys["DJANGO_DEBUG"]["value"] == "0"
