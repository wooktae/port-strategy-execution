from pathlib import Path

root = Path(r"C:\Workspaces\port_strategy_execution")

requirements_path = root / "requirements.txt"
dockerfile_path = root / "Dockerfile"

requirements_text = """psycopg2-binary
"""

dockerfile_text = """FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY port_strategy_execution/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY port_strategy_execution/ ./

CMD ["python", "daily_auto_buy_execute_run.py"]
"""

requirements_path.write_text(requirements_text, encoding="utf-8")
dockerfile_path.write_text(dockerfile_text, encoding="utf-8")

print("[OK] requirements.txt")
print(requirements_path.read_text(encoding="utf-8"))

print("[OK] Dockerfile")
print(dockerfile_path.read_text(encoding="utf-8"))
