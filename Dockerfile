FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY port_strategy_execution/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY port_strategy_execution/ ./

CMD ["python", "daily_auto_buy_execute_run.py"]
