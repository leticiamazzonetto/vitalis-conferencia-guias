#!/usr/bin/env bash
# Instala/atualiza o site na VPS. Rodar como root, com o codigo ja copiado em /opt/vitalis.
# Idempotente: pode rodar de novo a cada atualizacao.
set -euo pipefail
APP=/opt/vitalis
id -u vitalis >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin vitalis
mkdir -p /etc/vitalis /var/lib/vitalis
[ -f /etc/vitalis/env ] || { echo "ANTHROPIC_API_KEY=" > /etc/vitalis/env; echo "AVISO: /etc/vitalis/env criado vazio; grave a chave nele."; }
chown root:vitalis /etc/vitalis/env && chmod 640 /etc/vitalis/env
chown -R vitalis:vitalis /var/lib/vitalis "$APP"
cd "$APP"
[ -d .venv ] || sudo -u vitalis python3 -m venv .venv
sudo -u vitalis .venv/bin/pip install -q --upgrade pip
sudo -u vitalis .venv/bin/pip install -q -r requirements.txt
sudo -u vitalis .venv/bin/python -m unittest discover -s tests 2>&1 | tail -1
cp deploy/vitalis.service /etc/systemd/system/vitalis.service
cp deploy/vitalis-mcp.service /etc/systemd/system/vitalis-mcp.service
systemctl daemon-reload
systemctl enable --now vitalis vitalis-mcp
systemctl restart vitalis vitalis-mcp
sleep 4
systemctl is-active vitalis vitalis-mcp && curl -s -o /dev/null -w "local 8502: HTTP %{http_code}\n" http://127.0.0.1:8502/
