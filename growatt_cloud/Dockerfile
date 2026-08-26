FROM ghcr.io/home-assistant/base:3.22

WORKDIR /app

RUN apk add --no-cache \
    python3 \
    py3-paho-mqtt

COPY api.py /app/api.py
COPY mqtt_ha.py /app/mqtt_ha.py
COPY growatt_cloud.py /app/growatt_cloud.py

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Berlin

CMD ["python3", "-u", "/app/growatt_cloud.py"]
