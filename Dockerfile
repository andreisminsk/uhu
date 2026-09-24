FROM ubuntu:24.04

# ── Python + system dependencies ─────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        curl git vim nano procps zstd openssh-server \
    && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /run/sshd && \
    echo "PermitRootLogin yes" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config

# ── Install Ollama (install.sh, with direct-binary fallback) ─────
# NOTE: `curl | sh` silently succeeds on empty/failed downloads, which
# produced images without the ollama binary. Download first, sanity-check,
# then fall back to the GitHub release tarball (no API lookup involved).
ARG TARGETARCH
RUN set -eux; \
    arch="${TARGETARCH:-amd64}"; \
    ok=""; \
    if curl -fsSL --retry 3 https://ollama.com/install.sh -o /tmp/ollama-install.sh \
         && test -s /tmp/ollama-install.sh \
         && head -n 1 /tmp/ollama-install.sh | grep -q '#!'; then \
        sh /tmp/ollama-install.sh && ok="1" || ok=""; \
    fi; \
    if [ -z "$ok" ] || ! command -v ollama >/dev/null 2>&1; then \
        echo ">>> install.sh failed or ollama missing — direct binary download"; \
        curl -fsSL --retry 3 -o /tmp/ollama.tgz \
            "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-${arch}.tgz"; \
        tar -xzf /tmp/ollama.tgz -C /usr bin/ollama; \
        rm -f /tmp/ollama.tgz; \
    fi; \
    command -v ollama; \
    ollama --version

# ── Clone uhu (git clone so users can `git pull` later) ──────────
RUN git clone https://github.com/andreisminsk/uhu.git /opt/uhu

# ── Create venv, install uhu (editable, all extras), and pre-download ─
# Chromium for the browser tool. Base install now includes playwright;
# `playwright install --with-deps chromium` fetches the browser binary
# and its system libraries so the browser tool works out of the box.
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    cd /opt/uhu && /opt/venv/bin/pip install --no-cache-dir -e ".[all]" && \
    /opt/venv/bin/playwright install --with-deps chromium

ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# ── Make venv PATH available to SSH login shells ────────────────
RUN echo 'export PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin:$PATH"' >> /root/.bashrc && \
    echo 'export PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin:$PATH"' >> /etc/profile.d/uhu.sh

# ── SANDBOX workspace ────────────────────────────────────────────
RUN mkdir -p /SANDBOX

# ── Entrypoint ──────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /SANDBOX

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
