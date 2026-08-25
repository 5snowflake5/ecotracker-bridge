FROM ghcr.io/home-assistant/base:3.22

WORKDIR /app

RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-zeroconf \
    py3-paho-mqtt

COPY bridge.py /app/bridge.py

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Berlin

CMD ["python3", "-u", "/app/bridge.py"]
