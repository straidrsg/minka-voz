#!/usr/bin/env bash
# =====================================================================
#  MINKA VOZ — Instalador de acceso remoto (Tailscale) para la RPi
#  Ejecutar UNA sola vez en la Raspberry Pi:
#      bash instalar_remoto_rpi.sh
#
#  Hace:
#    1. Instala Tailscale (VPN privada) y lo deja con el Mismo nombre
#       de equipo, para que conserve su IP 100.x.x.x siempre.
#    2. Arranca como debe el servicio rpi_api.py (la API que usa el
#       dashboard del profesor) en el puerto 8290.
#
#  Tras ejecutarlo, en pantalla aparecerá un ENLACE DE AUTENTICACIÓN
#  (https://login.tailscale.com/a/xxxx). Ábrelo en el navegador de la
#  misma cuenta de Google/Microsoft y listo.
#
#  Después: en el dashboard del profesor poner la IP que aparece como
#  "100.x.x.x" que asigne Tailscale a la RPi (o leerla con: tailscale ip)
# =====================================================================
set -e

echo "==> 1/3 Instalando Tailscale…"
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo "    (Tailscale ya estaba instalado)"
fi

# El nombre de esta RPi aparece en la cuenta Tailscale con esta etiqueta
NOMBRE="minka-rpi"
tailscale set --hostname="$NOMBRE" || true

echo "==> 2/3 Conectando a Tailscale (copia el enlace de login que saldrá)…"
tailscale up --ssh=false --accept-routes=false || true

echo ""
echo "============================================================="
echo "  IP de la RPi en Tailscale (100.x.x.x):"
tailscale ip -4 2>/dev/null || echo "  (ejecuta: tailscale ip -4)"
echo "============================================================="
echo ""

echo "==> 3/3 Asegurando que la API (rpi_api.py) arranque en el puerto 8290…"

# Ruta típica del sistema MINKA en la RPi
APP_DIR="${MINKA_APP_DIR:-$HOME/minka-voz}"
API_PATH="$APP_DIR/rpi_api.py"

if [ ! -f "$API_PATH" ]; then
    echo "    No se encontró $API_PATH"
    echo "    Copia rpi_api.py de la carpeta minka-voz-main a $APP_DIR"
    echo "    y vuelve a ejecutar este script."
    exit 1
fi

PYTHON="$(command -v python3)"

# Unidad de systemd para que la API corra siempre (al arrancar la RPi)
sudo tee /etc/systemd/system/rpi-api.service >/dev/null <<EOF
[Unit]
Description=MINKA VOZ - API del dashboard del profesor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=$APP_DIR
Environment=MINKA_API_TOKEN=
ExecStart=$PYTHON $API_PATH
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rpi-api.service
sudo systemctl restart rpi-api.service

sleep 2
echo ""
echo "Estado de la API:"
sudo systemctl status rpi-api.service --no-pager | head -n 8
echo ""
echo "✔ Listo. La RPi es ahora alcanzable desde cualquier red mediante la IP 100.x.x.x"
echo "  En el dashboard del profesor pon esa IP, p. ej.:   100.117.42.7"
echo "  (probar con: curl http://<esa-IP>:8290/api/estado)"