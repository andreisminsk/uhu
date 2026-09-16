FROM python:3.12-slim

# ── System dependencies ──────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git vim nano procps \
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
