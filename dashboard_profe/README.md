# 👨‍🏫 Dashboard del Profesor — MINKA VOZ

Interfaz web para el profesor que se conecta al **sistema físico MINKA VOZ**
que corre en la Raspberry Pi 4 (micrófono INMP441 + altavoz MAX98357A).
No sustituye al traslador de la RPi: se *conecta* a él.

## Arquitectura

```
 Raspberry Pi (sistema físico ya en funcionamiento)
 ┌────────────────────────────────────────────┐
 │  minka_voz.py   (traslador de voz)          │
 │  rpi_api.py     (API HTTP de conexión)      │  ← este repo lo provee
 │  ~/minka/minka.db (diccionario + historial) │
 └──────────────┬─────────────────────────────┘
                │  HTTP (puerto 8290, red local)
 ┌──────────────▼─────────────────────────────┐
 │  dashboard_profe/app.py   (este dashboard)  │  ← corre en el PC del profesor
 │  http://localhost:8300                      │
 └────────────────────────────────────────────┘
```

## Qué hace para el profesor

| Función | Cómo |
|---|---|
| **Rectificar palabras** | Vista *Diccionario*: agrega, edita (rectifica el par Kogui↔Español) o elimina palabras. Los cambios se guardan en la DB de la RPi al instante; el traslador los usa desde la siguiente frase. |
| **Ayuda en tutoría** | Vista *Historial*: revisa lo que dijo realmente el estudiante y cómo lo tradujo MINKA. Al ver la frase («lo dijo bien pero tradujo mal», etc.) el profesor corrige la palabra en el diccionario. |
| **Repetir palabras** | Cada palabra/frase tiene botón 🔊 *Repetir*: lo envía a la RPi y se escucha por el altavoz MAX98357A. También una *pantalla grande* 🖥 para mostrar la palabra en letra grande al estudiante. |
| **Sesión de práctica** | Vista *Tutoría*: arma sesiones por categoría, baraja las palabras y las presenta una a una con reproducción por altavoz. |

## Acceso desde cualquier red (Tailscale)

Para poder abrir el dashboard del profesor **desde cualquier red** (la escuela, la
casa, datos móviles…) la RPi queda conectada a una **VPN privada** llamada Tailscale:
asigna a la RPi una IP fija tipo `100.x.x.x` que es accesible desde todas las redes
sin abrir puertos del router.

### Una vez en la Raspberry Pi

```bash
bash instalar_remoto_rpi.sh
```

El script instala Tailscale, muestra un **enlace de login** (ábrelo en el navegador y
acepta) y deja la API `rpi_api.py` corriendo como servicio.
Cuando termine, anota la IP que muestra `tailscale ip -4` (ej. `100.112.30.7`).

### En el PC del profesor

Instalar Tailscale también en cualquier dispositivo desde el que se vaya a abrir el
dashboard (https://tailscale.com/download) e iniciar sesión **con la misma cuenta**.
En el dashboard, escribir la IP `100.x.x.x` de la RPi en *Configuración*. Se puede
escribir solo la IP; el dashboard agrega `http://` y el puerto `:8290` solo.

> Saber la IP: en la RPi `tailscale ip -4`, o en la consola de
> https://login.tailscale.com/admin/machines (nodo `minka-rpi`).

## Instalación

### Opción A — Para el profesor (sin comandos)

Solo hay que copiar **`MINKA VOZ Profesor.exe`** al escritorio del PC del profesor y
hacer doble clic. Se abre el navegador solo y sale la pantalla de configuración:

1. Escribir la dirección de la Raspberry Pi
   (IP local como `192.168.1.100`, **o** IP Tailscale `100.x.x.x` para usarla
   desde cualquier red).
2. Pulsar **🔌 Probar conexión sin guardar** para comprobar que llega bien a la RPi.
3. Pulsar **💾 Guardar y probar conexión**.
4. ¡Listo para usarse! La configuración queda guardada al lado del `.exe`.

No hay que instalar Python ni escribir comandos. El dashboard se cierra con el
botón **⏻ Apagar** de la barra superior.

> El `.exe` se genera con: `python -m PyInstaller --onefile --windowed --name "MINKA VOZ Profesor" --add-data "templates;templates" --add-data "static;static" app.py` (ejecutar dentro de `dashboard_profe/`).

### Opción B — Desde el código fuente

### 1. En la Raspberry Pi (una vez)

Copiar `rpi_api.py` a la carpeta del sistema (junto a `minka_voz.py` y `database.py`)
y arrancarlo:

```bash
cd ~/minka-voz
source venv/bin/activate
pip install flask requests
nohup python3 rpi_api.py > api.log 2>&1 &
```

Opcional — proteger la API con token y arranque automático:

```bash
echo 'Environment=MINKA_API_TOKEN=tu-token-secreto' | sudo tee -a /etc/systemd/system/minka-voz.service
# y añadir una unidad nueva rpi-api.service con:
# ExecStart=/home/pi/minka-voz/venv/bin/python /home/pi/minka-voz/rpi_api.py
```

### 2. En el PC del profesor

```bash
cd dashboard_profe
pip install -r requirements.txt
python app.py
```

Abrir **http://localhost:8300** y en *Config* indicar la IP de la RPi
(p. ej. `http://192.168.1.100:8290`). Contraseña por defecto: `minka`.

## Puertos / variables

| Dónde | Variable | Puerto / valor por defecto |
|---|---|---|
| RPi | `API_PORT` | 8290 |
| RPi | `API_HOST` | 0.0.0.0 |
| RPi | `MINKA_API_TOKEN` | (vacío = sin token) |
| Dashboard | `DASH_PORT` | 8300 |
| Dashboard | `MINKA_RPI_URL` | http://192.168.1.100:8290 |
| Dashboard | `DASH_PASSWORD` | minka |
| Dashboard | `DASH_SECRET` | clave de sesión |

Los valores del dashboard también se editan desde la página *Config* (se guardan
en `dashboard_profe/config.json`, ignorado por git).

## Notas

- El foco de este dashboard es **corregir el diccionario** para que el traslator
  mejore, **no** sustituir la práctica oral con el estudiante.
- `rpi_api.py` solo funciona con reproducción de audio sobre Linux (RPi); en
  Windows responde el error *"Reproducción solo disponible en la Raspberry Pi"*.