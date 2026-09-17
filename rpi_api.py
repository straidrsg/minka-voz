#!/usr/bin/env python3
"""
rpi_api.py — API de conexión del sistema MINKA VOZ (Raspberry Pi)
===============================================================
Pequeño servidor HTTP/JSON que corre EN la Raspberry Pi, junto a
minka_voz.py, y expone:

  GET    /api/estado                      → estado del sistema (escuchando, modo, audio)
  GET    /api/diccionario                 → lista/diccionario (búsqueda y filtro por categoría)
  POST   /api/diccionario                 → agregar palabra
  PUT    /api/diccionario/<id>            → rectificar palabra
  DELETE /api/diccionario/<id>            → eliminar palabra
  GET    /api/historial                   → historial de conversaciones (paginado/filtros)
  POST   /api/repetir                     → repetir una palabra/frase por el altavoz {texto}
  GET    /api/categorias                  → lista de categorías del diccionario

Uso (en la Raspberry Pi):
  pip install flask requests
  python3 rpi_api.py            # puerto 8290 por defecto (variable API_PORT)

El dashboard del profesor (dashboard_profe/) se conecta a estas rutas.
"""

import os
import sys
import time
import threading
import traceback

from flask import Flask, request, jsonify

import database as db

# ── Configuración ──────────────────────────────────────────────────────
HOST = os.environ.get("API_HOST", "0.0.0.0")
PORT = int(os.environ.get("API_PORT", "8290"))
API_TOKEN = os.environ.get("MINKA_API_TOKEN", "")

app = Flask(__name__)


# ── Autenticación opcional por token ───────────────────────────────────
def requiere_token(fn):
    def wrapper(*args, **kwargs):
        if API_TOKEN:
            auth = request.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else ""
            if token != API_TOKEN:
                return jsonify({"ok": False, "error": "Token inválido"}), 401
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _ok(data=None, extra=None):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    if extra:
        payload.update(extra)
    return jsonify(payload)


def _err(mensaje, status=400):
    return jsonify({"ok": False, "error": mensaje}), status


# ── Estado del sistema (lee lo que detecta el port de la RPi) ─────────
def _estado_audio():
    """Intenta leer la config ALSA para reportar mic/altavoz I2S."""
    info = {
        "inmp441": None,
        "max98357a": None,
    }
    try:
        with open("/proc/asound/cards") as f:
            lineas = f.read().splitlines()
        for i, linea in enumerate(lineas):
            if not linea or i + 1 >= len(lineas):
                continue
            desc = lineas[i + 1].lower()
            if any(k in desc for k in ("hifiberry", "max98357")):
                info["max98357a"] = desc.strip()
            if any(k in desc for k in ("inmp", "adc")):
                info["inmp441"] = desc.strip()
    except Exception:
        pass
    return info


@app.route("/api/estado")
@requiere_token
def api_estado():
    stats = db.estadisticas()
    return _ok({
        "tiempo": time.strftime("%Y-%m-%d %H:%M:%S"),
        "plataforma": sys.platform,
        "db": db.DB_PATH,
        "audio": _estado_audio(),
        "palabras": stats["palabras"],
        "conversaciones": stats["conversaciones"],
    })


# ── Diccionario ────────────────────────────────────────────────────────
@app.route("/api/diccionario")
@requiere_token
def api_diccionario():
    q = request.args.get("q", "")
    cat = request.args.get("cat", "")
    palabras = db.buscar_palabra(q) if q else db.obtener_todas_palabras()
    if cat:
        palabras = [p for p in palabras if p[3] == cat]
    return _ok([{
        "id": p[0], "kogui": p[1], "spanish": p[2],
        "categoria": p[3], "notas": p[4], "fecha": p[5],
    } for p in palabras])


@app.route("/api/diccionario", methods=["POST"])
@requiere_token
def api_diccionario_agregar():
    data = request.get_json(silent=True) or request.form
    kogui = (data.get("kogui") or "").strip()
    spanish = (data.get("spanish") or "").strip()
    if not kogui or not spanish:
        return _err("kogui y spanish son obligatorios")
    ok, msg = db.agregar_palabra(
        kogui, spanish,
        (data.get("categoria") or "general").strip(),
        (data.get("notas") or "").strip(),
    )
    if not ok:
        return _err(msg)
    return _ok()


@app.route("/api/diccionario/<int:pid>", methods=["PUT"])
@requiere_token
def api_diccionario_editar(pid):
    data = request.get_json(silent=True) or request.form
    kogui = (data.get("kogui") or "").strip()
    spanish = (data.get("spanish") or "").strip()
    if not kogui or not spanish:
        return _err("kogui y spanish son obligatorios")
    ok, msg = db.actualizar_palabra(
        pid, kogui, spanish,
        (data.get("categoria") or "general").strip(),
        (data.get("notas") or "").strip(),
    )
    if not ok:
        return _err(msg)
    return _ok()


@app.route("/api/diccionario/<int:pid>", methods=["DELETE"])
@requiere_token
def api_diccionario_eliminar(pid):
    ok = db.eliminar_palabra(pid)
    if not ok:
        return _err("No existe la palabra", 404)
    return _ok()


@app.route("/api/categorias")
@requiere_token
def api_categorias():
    con = db.conectar()
    cur = con.cursor()
    cur.execute("SELECT DISTINCT categoria FROM dictionary ORDER BY categoria")
    cats = [r[0] for r in cur.fetchall() if r[0]]
    con.close()
    return _ok(cats)


# ── Historial ──────────────────────────────────────────────────────────
@app.route("/api/historial")
@requiere_token
def api_historial():
    limite = min(int(request.args.get("limite", "50")), 200)
    offset = max(int(request.args.get("offset", "0")), 0)
    q = request.args.get("q", "")
    if q:
        rows = db.buscar_historial(q)
        rows = rows[offset:offset + limite]
    else:
        # obtener_historial devuelve las más recientes primero
        rows = db.obtener_historial(limite=(offset + limite))
        rows = rows[offset:offset + limite]
    return _ok([{
        "id": r[0], "message": r[1], "texto_traducido": r[2],
        "direccion": r[3], "fuente": r[4], "fecha": r[5],
    } for r in rows])


# ── Repetir por el altavoz ─────────────────────────────────────────────
_tts_lock = threading.Lock()


def _reproducir(texto):
    """Reproduce texto por el altavoz MAX98357A usando aplay (como el port)."""
    try:
        import shutil, subprocess, tempfile, hashlib
        if not texto:
            return False, "Texto vacío"

        # Encontrar tarjeta de salida I2S (MAX98357A)
        dev = None
        try:
            with open("/proc/asound/cards") as f:
                lineas = f.read().splitlines()
            for i, linea in enumerate(lineas):
                if not linea or i + 1 >= len(lineas):
                    continue
                if any(k in lineas[i + 1].lower() for k in ("max98357", "dac", "hifiberry")):
                    cid = linea.split()[0]
                    if os.path.isdir(f"/proc/asound/card{cid}/pcm0p"):
                        dev = f"hw:{cid},0"
                        break
        except Exception:
            pass

        # Sintetizar con espeak-ng (garantizado con instalar.sh)
        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if not espeak:
            return False, "No hay motor TTS (espeak-ng) instalado"

        ttl = os.path.expanduser("~/.cache/minka-tts")
        os.makedirs(ttl, exist_ok=True)
        clave = hashlib.sha1(texto.encode()).hexdigest()
        fpath = os.path.join(ttl, f"rep_{clave}.wav")
        if not os.path.exists(fpath):
            subprocess.run([espeak, "-v", "es", "-s", "155", "-w", fpath, texto],
                           capture_output=True, timeout=30)
        if not os.path.exists(fpath):
            return False, "No se pudo sintetizar el audio"

        cmd = ["aplay", "-q"]
        if dev:
            cmd += ["-D", dev]
        cmd.append(fpath)
        subprocess.run(cmd, capture_output=True, timeout=30)
        return True, "reproducido"
    except Exception as e:
        return False, str(e)


@app.route("/api/repetir", methods=["POST"])
@requiere_token
def api_repetir():
    data = request.get_json(silent=True) or request.form
    texto = (data.get("texto") or "").strip()
    if not texto:
        return _err("texto es obligatorio")
    if sys.platform != "linux":
        return _err("Reproducción solo disponible en la Raspberry Pi", 501)
    with _tts_lock:
        ok, msg = _reproducir(texto)
    if not ok:
        return _err(msg, 500)
    return _ok(extra={"mensaje": msg})


# ── Main ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    db.inicializar_db()
    print(f"\n🌿 MINKA VOZ API  →  http://{HOST}:{PORT}")
    print(f"   Ruta DB: {db.DB_PATH}\n")
    app.run(host=HOST, port=PORT, debug=False)