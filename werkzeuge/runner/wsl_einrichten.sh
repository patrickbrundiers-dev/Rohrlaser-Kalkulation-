#!/bin/bash
# Richtet in WSL-Ubuntu 24.04 auf Patricks PC den eigenen GitHub-Runner für die Tests ein (Job „tests“, Label rohrlaser).
# Anleitung: werkzeuge/runner/ANLEITUNG.md. Aufruf im Ubuntu-Fenster:
#   bash wsl_einrichten.sh <Token von GitHub>
# Installiert die Systempakete, die der Workflow auf GitHub-Runnern per apt holt, und richtet den Runner
# „rohrlaser-wsl“ als systemd-Dienst ein. Erneut ausführbar.
set -euo pipefail
TOKEN="${1:?Token fehlt: bash wsl_einrichten.sh <Token>}"
REPO="https://github.com/patrickbrundiers-dev/Rohrlaser-Kalkulation-"
ORDNER="$HOME/actions-runner"

echo "1/3 Systempakete ..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends git curl ca-certificates python3 python3-pip libegl1 libxkbcommon0 \
  poppler-utils xvfb xauth libgl1-mesa-dri libglx-mesa0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3

if ! grep -qs "systemd=true" /etc/wsl.conf; then
  printf '[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf > /dev/null
  echo "systemd eingeschaltet: in Windows-PowerShell 'wsl --shutdown' ausführen, Ubuntu neu öffnen, Skript erneut starten."
  exit 0
fi

echo "2/3 Runner herunterladen nach $ORDNER ..."
mkdir -p "$ORDNER" && cd "$ORDNER"
if [ ! -f config.sh ]; then
  V=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'][1:])")
  curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v$V/actions-runner-linux-x64-$V.tar.gz"
  tar xzf runner.tar.gz && rm runner.tar.gz
fi

echo "3/3 Runner anmelden und als Dienst starten ..."
if [ ! -f .runner ]; then
  ./config.sh --unattended --url "$REPO" --token "$TOKEN" --name rohrlaser-wsl --labels rohrlaser --work _work
fi
sudo ./svc.sh install "$USER" || true
sudo ./svc.sh start
echo "Fertig. Unter GitHub → Settings → Actions → Runners steht jetzt „rohrlaser-wsl“ (Idle)."
