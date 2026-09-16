FROM ubuntu:24.04

# ── Python + system dependencies ─────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        curl git vim nano procps zstd \
    && rm -rf /var/lib/apt/lists/*

# ── Install Ollama ──────────────────────────────────────────────
RUN curl -fsSL https://ollama.com/install.sh | sh

# ── Clone uhu (git clone so users can `git pull` later) ──────────
RUN git clone https://github.com/andreisminsk/uhu.git /opt/uhu

# ── Install uhu in editable mode ────────────────────────────────
RUN cd /opt/uhu && pip install --no-cache-dir -e ".[all]"

# ── SANDBOX workspace ────────────────────────────────────────────
RUN mkdir -p /SANDBOX

# ── Entrypoint ──────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /SANDBOX

ENTRYPOINT ["/entrypoint.sh"]
