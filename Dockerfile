FROM python:3.13-alpine3.22
RUN apk add --no-cache bash curl util-linux ca-certificates
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY host ./host
RUN chmod 0755 /app/host/host-helper.sh
ENV ZMM_DATA_DIR=/DATA/AppData/z-mesh-manager ZMM_PORT=8484
EXPOSE 8484
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD wget -qO- http://127.0.0.1:8484/api/health || exit 1
CMD ["python", "-m", "app.main"]
