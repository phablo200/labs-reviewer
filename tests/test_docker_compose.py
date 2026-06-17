from pathlib import Path

import yaml


def test_docker_compose_defines_local_celery_stack() -> None:
    compose = yaml.safe_load(Path("docker-compose.yaml").read_text(encoding="utf-8"))

    services = compose["services"]
    assert {"api", "worker", "redis", "mongodb"}.issubset(services)
    assert services["api"]["environment"]["CELERY_BROKER_URL"] == "redis://redis:6379/0"
    assert (
        services["api"]["environment"]["CELERY_RESULT_BACKEND"]
        == "redis://redis:6379/1"
    )
    assert services["api"]["environment"]["MONGODB_URI"] == "mongodb://mongodb:27017"
    assert services["worker"]["environment"]["CELERY_BROKER_URL"] == (
        "redis://redis:6379/0"
    )
    assert services["worker"]["environment"]["CELERY_RESULT_BACKEND"] == (
        "redis://redis:6379/1"
    )
    assert services["worker"]["environment"]["MONGODB_URI"] == (
        "mongodb://mongodb:27017"
    )
    assert services["worker"]["command"] == (
        "celery -A labs.tasks.celery_app.celery_app worker --loglevel=info"
    )
    assert "mongodb_data" in compose["volumes"]
