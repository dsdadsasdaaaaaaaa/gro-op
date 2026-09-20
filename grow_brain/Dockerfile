ARG BUILD_FROM=python:3.12-slim
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Alpine (HA base images) needs build deps for pillow; Debian slim has wheels.
RUN if [ -f /etc/alpine-release ]; then \
      apk add --no-cache libjpeg-turbo zlib && \
      apk add --no-cache --virtual .build jpeg-dev zlib-dev gcc musl-dev python3-dev; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ -f /etc/alpine-release ]; then apk del .build; fi

COPY grow_brain ./grow_brain
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
CMD ["/run.sh"]
