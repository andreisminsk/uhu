#!/usr/bin/env bash

# ── Inject SSH public keys from SSH_PUBLIC_KEYS env var ─────────
if [ -n "${SSH_PUBLIC_KEYS}" ]; then
  mkdir -p /root/.ssh
  chmod 700 /root/.ssh
  while IFS= read -r key; do
    [ -n "$key" ] && echo "$key" >> /root/.ssh/authorized_keys
  done <<< "${SSH_PUBLIC_KEYS}"
  chmod 600 /root/.ssh/authorized_keys
  echo "SSH public keys injected from SSH_PUBLIC_KEYS"
fi

# ── Start SSH server ────────────────────────────────────────────
/usr/sbin/sshd

# ── Start Ollama server in background ────────────────────────────
echo "Starting Ollama server..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!
sleep 3

# ── Pull Ollama models at startup ───────────────────────────────
echo "Pulling Ollama models (this may take a while on first run)..."
for model in glm-5.3-flash:cloud glm-5.2:cloud glm-5.3:cloud; do
    echo "  → Pulling $model..."
    ollama pull "$model" 2>&1 || echo "  ⚠ Failed to pull $model (will retry on next start)"
done
echo "Model pull complete."
echo

# ── Startup banner ───────────────────────────────────────────────
cat <<'BANNER'

  ╔══════════════════════════════════════════════════════════════╗
  ║                                                              ║
  ║    ██╗   ██╗  ██╗  ██╗  ██╗   ██╗                            ║
  ║    ██║   ██║  ██║  ██║  ██║   ██║                            ║
  ║    ██║   ██║  ███████║  ██║   ██║                            ║
  ║    ██║   ██║  ██╔══██║  ██║   ██║                            ║
  ║    ╚██████╔╝  ██║  ██║  ╚██████╔╝                            ║
  ║     ╚═════╝   ╚═╝  ╚═╝   ╚═════╝                             ║
  ║                                                              ║
  ║    uhu — Minimalistic Agentic Coder  (Docker Edition)        ║
  ║                                                              ║
  ╠══════════════════════════════════════════════════════════════╣
  ║                                                              ║
  ║   Ollama models available:                                   ║
  ║     • glm-5.3-flash:cloud                                    ║
  ║     • glm-5.2:cloud                                          ║
  ║     • glm-5.3:cloud                                          ║
  ║                                                              ║
  ║   uhu source:  /opt/uhu  (git pull to update)                ║
  ║   Workspace:  /SANDBOX  (you are here)                       ║
  ║                                                              ║
  ╠══════════════════════════════════════════════════════════════╣
  ║                                                              ║
  ║   GETTING STARTED:                                           ║
  ║                                                              ║
  ║   1. Create a folder for your project:                       ║
  ║        mkdir my-project && cd my-project                     ║
  ║                                                              ║
  ║   2. Run uhu:                                                ║
  ║        uhu                                                   ║
  ║        uhu --model glm-5.2:cloud --ctx 202752                ║
  ║                                                              ║
  ║   To update uhu:                                             ║
  ║        cd /opt/uhu && git pull                               ║
  ║                                                              ║
  ╚══════════════════════════════════════════════════════════════╝

BANNER

# ── Keep container alive (SSH in for a shell) ───────────────────
exec "$@"
