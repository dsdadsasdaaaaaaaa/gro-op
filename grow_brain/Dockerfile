# Official multi-arch Python image (the Supervisor's BUILD_FROM arg is intentionally not used:
# its default base image has no Python).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY grow_brain ./grow_brain
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
CMD ["/run.sh"]
