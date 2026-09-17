#!/usr/bin/env python3
"""
Dashboard del Profesor — MINKA VOZ
==================================
Interfaz web que se conecta al sistema físico de la Raspberry Pi (rpi_api.py)
para:
  • Rectificar palabras del diccionario (corregir Kogui <-> Español).
  • Ayudar al tutor: revisar el historial de lo que dijo el estudiante
    y corregir transcripciones/traducciones.
  • Repetir palabras por el altavoz de la RPi (MAX98357A) y mostrarlas
    en pantalla grande para el estudiante.

Arranque:
  pip install flask requests
  python app.py          → http://localhost:8300   (variable DASH_PORT)

Conexión a la RPi se configura en /config (URL + token) y se guarda en config.json.
"""

import os
import sys
import json
import time
import socket
import threading
import webbrowser
import requests
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash, abort,
)

# Al empaquetar con PyInstaller:
#   - RES_DIR  → carpeta temporal que contiene templates/ y static/
#   - APP_DIR  → junto al .exe (donde vive config.json del profesor)
if getattr(sys, "frozen", False):
    RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    RES_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RES_DIR

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

app = Flask(
    __name__,
    template_folder=os.path.join(RES_DIR, "templates"),
    static_folder=os.path.join(RES_DIR, "static"),
)
app.secret_key = os.environ.get("DASH_SECRET", "minka-profesor-dashboard-secret")


# ── Configuración persistente ──────────────────────────────────────────
def _config_por_defecto():
    return {
        "rpi_url": os.environ.get("MINKA_RPI_URL", "http://192.168.1.100:8290"),
        "token": os.environ.get("MINKA_API_TOKEN", ""),
        "password": os.environ.get("DASH_PASSWORD", "minka"),
    }


def cargar_config():
    cfg = _config_por_defecto()
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                datos = json.load(f)
            cfg.update({k: v for k, v in datos.items() if k in cfg})
    except Exception:
        pass
    return cfg


def guardar_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def normalizar_rpi_url(direccion):
    """Convierte lo que escriba el profesor en una URL válida.
    Acepta: 10.217.168.99 / 10.217.168.99:8290 / http://10.217.168.99:8290
    """
    texto = (direccion or "").strip().rstrip("/")
    if not texto:
        return ""
    if not texto.lower().startswith(("http://", "https://")):
        texto = "http://" + texto
    # Si no trae puerto explícito, usa el 8290 de rpi_api.py
    parte = texto.split("//")[-1] if "://" in texto else texto
    if ":" not in parte.rsplit("/", 1)[0]:
        texto = texto + ":8290"
    return texto


# ── Cliente hacia la API de la RPi ─────────────────────────────────────
def api_rpi(metodo, ruta, datos=None, params=None, timeout=12):
    cfg = cargar_config()
    url = cfg["rpi_url"].rstrip("/") + ruta
    headers = {}
    if cfg.get("token"):
        headers["Authorization"] = "Bearer " + cfg["token"]
    try:
        if metodo == "GET":
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        elif metodo == "POST":
            r = requests.post(url, json=datos, headers=headers, timeout=timeout)
        elif metodo == "PUT":
            r = requests.put(url, json=datos, headers=headers, timeout=timeout)
        elif metodo == "DELETE":
            r = requests.delete(url, headers=headers, timeout=timeout)
        else:
            return {"ok": False, "error": "método no soportado"}
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": f"Respuesta inválida ({r.status_code})"}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "Tiempo de espera agotado (la RPi no responde)"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "No se pudo conectar a la RPi"}
    except Exception as e:
        return {"ok": False, "error": f"Error HTTP: {e}"}


def estado_conectado():
    return api_rpi("GET", "/api/estado")


# ── Autenticación sencilla ─────────────────────────────────────────────
def login_requerido(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logueado"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


# ── Página de acceso ───────────────────────────────────────────────────
def es_primer_uso():
    return not os.path.exists(CONFIG_PATH)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logueado"):
        return redirect(url_for("index"))
    if es_primer_uso():
        return redirect(url_for("configuracion"))
    if request.method == "POST":
        clave = request.form.get("password", "")
        if clave == cargar_config()["password"]:
            session["logueado"] = True
            return redirect(url_for("index"))
        flash("Contraseña incorrecta", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Inicio / estado ────────────────────────────────────────────────────
@app.route("/")
@login_requerido
def index():
    estado = estado_conectado()
    historial = api_rpi("GET", "/api/historial", params={"limite": 8})
    contexto = {
        "estado": estado.get("data") if estado.get("ok") else None,
        "error_estado": estado.get("error") if not estado.get("ok") else None,
        "historial": historial.get("data", []) if historial.get("ok") else [],
    }
    return render_template("index.html", **contexto)


# ── Configuración de conexión ──────────────────────────────────────────
@app.route("/config", methods=["GET", "POST"])
def configuracion():
    primer_uso = es_primer_uso()
    if not primer_uso and not session.get("logueado"):
        return redirect(url_for("login"))
    cfg = cargar_config()
    if request.method == "POST":
        cfg["rpi_url"] = normalizar_rpi_url(request.form.get("rpi_url", cfg["rpi_url"]))
        cfg["token"] = request.form.get("token", cfg["token"]).strip()
        nueva = request.form.get("password", "").strip()
        if nueva:
            cfg["password"] = nueva
        guardar_config(cfg)
        session["logueado"] = True
        # Probamos la conexión Y mostramos el resultado aquí mismo
        pr = probar()
        if pr["ok"]:
            flash("Guardado. Conexión exitosa con la RPi ✔", "success")
        else:
            flash("Guardado, pero no se pudo conectar: " + pr["error"], "danger")
        return redirect(url_for("configuracion"))
    return render_template("config.html", cfg=cfg, primer_uso=primer_uso)


def probar():
    """Prueba la conexión con la URL Y el token ya normalizados/de la config."""
    cfg = cargar_config()
    env = cfg["rpi_url"].rstrip("/")
    tok = cfg.get("token", "")
    headers = {"Authorization": "Bearer " + tok} if tok else {}
    if not env:
        return {"ok": False, "error": "Escribe la dirección de la RPi"}
    try:
        r = requests.get(env + "/api/estado", headers=headers, timeout=6)
        if r.status_code == 401:
            return {"ok": False, "error": "Token incorrecto"}
        datos = r.json().get("data", {})
        return {
            "ok": True,
            "estado": datos.get("plataforma", ""),
            "palabras": datos.get("palabras", 0),
        }
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "No responde (¿La RPi está encendida en esa dirección?)"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "No se pudo conectar (revisa que la IP esté bien y sea 10.217.168.99)"}
    except Exception as e:
        return {"ok": False, "error": f"Error: {e}"}


@app.route("/probar", methods=["POST"])
def probar_conexion():
    env = request.form.get("rpi_url", "").strip()
    tok = request.form.get("token", "").strip()
    if env:
        cfg = cargar_config()
        cfg["rpi_url"] = normalizar_rpi_url(env)
        cfg["token"] = tok
        guardar_config(cfg)
    return jsonify(probar())


@app.route("/apagar", methods=["POST"])
def apagar():
    if not session.get("logueado") and not es_primer_uso():
        return redirect(url_for("login"))
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return render_template("apagando.html")


# ── Diccionario (rectificar palabras) ──────────────────────────────────
categorias_fijas = ["saludo", "familia", "naturaleza", "animal",
                    "cuerpo", "accion", "numero", "general"]


@app.route("/diccionario")
@login_requerido
def diccionario():
    q = request.args.get("q", "")
    cat = request.args.get("cat", "")
    resp = api_rpi("GET", "/api/diccionario",
                   params={"q": q, "cat": cat} if (q or cat) else {})
    palabras = resp.get("data", []) if resp.get("ok") else []
    cats = api_rpi("GET", "/api/categorias")
    cats_lista = cats.get("data") or categorias_fijas
    return render_template(
        "diccionario.html",
        palabras=palabras,
        categorias=cats_lista,
        q=q, cat=cat,
        error=resp.get("error") if not resp.get("ok") else None,
    )


@app.route("/diccionario/agregar", methods=["POST"])
@login_requerido
def diccionario_agregar():
    resp = api_rpi("POST", "/api/diccionario", datos={
        "kogui": request.form.get("kogui", ""),
        "spanish": request.form.get("spanish", ""),
        "categoria": request.form.get("categoria", "general"),
        "notas": request.form.get("notas", ""),
    })
    flash(resp.get("error") if not resp.get("ok") else "Palabra agregada",
          "danger" if not resp.get("ok") else "success")
    return redirect(url_for("diccionario"))


@app.route("/diccionario/editar/<int:pid>", methods=["POST"])
@login_requerido
def diccionario_editar(pid):
    resp = api_rpi("PUT", f"/api/diccionario/{pid}", datos={
        "kogui": request.form.get("kogui", ""),
        "spanish": request.form.get("spanish", ""),
        "categoria": request.form.get("categoria", "general"),
        "notas": request.form.get("notas", ""),
    })
    flash(resp.get("error") if not resp.get("ok") else "Palabra rectificada",
          "danger" if not resp.get("ok") else "success")
    return redirect(url_for("diccionario"))


@app.route("/diccionario/eliminar/<int:pid>", methods=["POST"])
@login_requerido
def diccionario_eliminar(pid):
    resp = api_rpi("DELETE", f"/api/diccionario/{pid}")
    flash(resp.get("error") if not resp.get("ok") else "Palabra eliminada",
          "danger" if not resp.get("ok") else "info")
    return redirect(url_for("diccionario"))


# ── Repetir por el altavoz de la RPi ───────────────────────────────────
@app.route("/repetir", methods=["POST"])
@login_requerido
def repetir():
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "error": "Texto vacío"}), 400
    resp = api_rpi("POST", "/api/repetir", datos={"texto": texto}, timeout=45)
    return jsonify(resp)


# ── Tarjeta grande (modo profesor): mostrar y repetir una palabra ──────
@app.route("/tarjeta")
@login_requerido
def tarjeta():
    kogui = request.args.get("kogui", "")
    spanish = request.args.get("spanish", "")
    return render_template("tarjeta.html", kogui=kogui, spanish=spanish)


# ── Historial (qué dijo el estudiante + corregir) ──────────────────────
@app.route("/historial")
@login_requerido
def historial():
    q = request.args.get("q", "")
    resp = api_rpi("GET", "/api/historial", params={"limite": 100, "q": q})
    registros = resp.get("data", []) if resp.get("ok") else []
    return render_template(
        "historial.html",
        historial=registros,
        q=q,
        error=resp.get("error") if not resp.get("ok") else None,
    )


# ── Tutoría: listas de práctica por categoría ──────────────────────────
@app.route("/tutoria")
@login_requerido
def tutoria():
    cat = request.args.get("cat", "")
    resp = api_rpi("GET", "/api/diccionario",
                   params={"cat": cat} if cat else {})
    palabras = resp.get("data", []) if resp.get("ok") else []
    cats = api_rpi("GET", "/api/categorias")
    cats_lista = cats.get("data") or categorias_fijas
    return render_template("tutoria.html", palabras=palabras,
                           categorias=cats_lista, cat=cat,
                           error=resp.get("error") if not resp.get("ok") else None)


# ── Main ───────────────────────────────────────────────────────────────
def puerto_disponible(preferido):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", preferido))
        s.close()
        return preferido
    except OSError:
        s.close()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
        s.close()
        return port


if __name__ == "__main__":
    preferido = int(os.environ.get("DASH_PORT", "8300"))
    port = puerto_disponible(preferido)
    url_local = f"http://localhost:{port}"
    print(f"\n\U0001F468\u200D\U0001F3EB MINKA VOZ - Dashboard del Profesor  ->  {url_local}")
    print(f"   Conectado a la API de la RPi: {cargar_config()['rpi_url']}\n")

    threading.Timer(1.2, lambda: webbrowser.open(url_local)).start()

    from waitress import serve
    serve(app, host="0.0.0.0", port=port)