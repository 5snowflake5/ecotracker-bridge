FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY bridge.py /app/bridge.py

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Berlin
CMD ["python3", "-u", "/app/bridge.py"]
