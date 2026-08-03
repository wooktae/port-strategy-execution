from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO / "Dockerfile"
DOCKERIGNORE = REPO / ".dockerignore"


def test_dockerfile_uses_repository_root_context():
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY requirements.txt ./requirements.txt" in source
    assert "COPY . ./" in source

    assert (
        "COPY port_strategy_execution/requirements.txt"
        not in source
    )
    assert "COPY port_strategy_execution/ ./" not in source


def test_dockerfile_runtime_contract():
    source = DOCKERFILE.read_text(encoding="utf-8")

    required = [
        "FROM python:3.13-slim",
        "WORKDIR /app",
        "ENV PYTHONDONTWRITEBYTECODE=1",
        "ENV PYTHONUNBUFFERED=1",
        "RUN pip install --no-cache-dir -r requirements.txt",
        'CMD ["python", "daily_auto_buy_execute_run.py"]',
    ]

    for marker in required:
        assert marker in source


def test_dockerignore_excludes_local_and_sensitive_files():
    rules = {
        line.strip()
        for line in DOCKERIGNORE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    }

    required = {
        ".git",
        ".github",
        ".devops",
        "__pycache__/",
        ".pytest_cache/",
        ".venv/",
        "venv/",
        ".env",
        ".env.*",
        "access_token.txt",
        "*.log",
        "*.bak",
        "tests/",
        "docs/",
    }

    assert required.issubset(rules)


def test_runtime_sources_are_not_excluded():
    rules = {
        line.strip()
        for line in DOCKERIGNORE.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    }

    forbidden = {
        "*.py",
        "requirements.txt",
        "execution_*.py",
        "daily_*.py",
    }

    assert forbidden.isdisjoint(rules)
