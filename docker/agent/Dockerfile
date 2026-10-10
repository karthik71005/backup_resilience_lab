FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    restic \
    iptables iproute2 dnsutils procps net-tools curl iputils-ping \
    cron sudo ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash labuser && \
    mkdir -p /data /data/victim /var/log/lab /var/lib/lab /restore /cache /app && \
    chown -R labuser:labuser /data /var/log/lab /var/lib/lab /restore /cache /app && \
    echo "labuser ALL=(root) NOPASSWD: /usr/sbin/iptables, /sbin/iptables" > /etc/sudoers.d/labuser-iptables && \
    chmod 0440 /etc/sudoers.d/labuser-iptables && visudo -c

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt
COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/
RUN pip3 install --no-cache-dir --break-system-packages -e /app

COPY docker/agent/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER labuser
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
