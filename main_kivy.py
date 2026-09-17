#!/usr/bin/env python3
"""
MINKA VOZ - Kivy Multiplataforma
Traductor de voz Kogui <-> Espanol
- Android: APIs nativas (SpeechRecognizer + TTS) via pyjnius
- Desktop: Whisper + sounddevice + gTTS + pygame
"""

import os
import sys
import time
import threading
import tempfile
import warnings
import traceback
import sqlite3

# ── Deteccion de plataforma ────────────────────────────────────────────
IS_ANDROID = (
    hasattr(sys, 'getandroidapilevel')
    or 'ANDROID_PRIVATE' in os.environ
    or os.path.exists('/system/build.prop')
)

# ── Imports condicionales ──────────────────────────────────────────────
if IS_ANDROID:
    import android_backend as audio_backend
else:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    import pygame
    import whisper

import database as db

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

# ── Constantes ─────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS = 1
MIN_DURACION = 0.3
DB_PATH = os.path.expanduser("~/minka/minka.db")

# ── Estado global ──────────────────────────────────────────────────────
grabando = False
audio_chunks = []
modo = "k2e"
procesando = False
modelo_whisper = None

# Referencias UI (se asignan al crear la UI)
_status_label = None
_historial_list = None
_mic_btn = None
_modo_btn = None


# ── Utilidades ─────────────────────────────────────────────────────────

def set_status(texto):
    from kivy.clock import Clock
    def _update(dt):
        if _status_label:
            _status_label.text = texto
    Clock.schedule_once(_update, 0)


def _kivy_ui(callback):
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: callback(), 0)


# ── Cargar modelo Whisper (solo desktop) ───────────────────────────────

def cargar_modelo_whisper():
    global modelo_whisper
    if IS_ANDROID:
        set_status("Listo - Toca el microfono")
        return
    try:
        set_status("Cargando modelo Whisper (base)...")
        modelo_whisper = whisper.load_model("base")
        set_status("Whisper listo - Manten presionado para grabar")
    except Exception as e:
        set_status(f"Error cargando modelo: {e}")
        print(f"Error Whisper: {e}")


# ── Diccionario ────────────────────────────────────────────────────────

def inicializar_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kogui TEXT,
            spanish TEXT,
            categoria TEXT DEFAULT 'general',
            notas TEXT DEFAULT '',
            fecha TEXT DEFAULT ''
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT DEFAULT 'minka_voz',
            message TEXT DEFAULT '',
            texto_traducido TEXT DEFAULT '',
            direccion TEXT DEFAULT 'k2e',
            fuente TEXT DEFAULT 'diccionario',
            fecha TEXT DEFAULT ''
        )""")
    con.commit()
    cur.execute("SELECT COUNT(*) FROM dictionary")
    total = cur.fetchone()[0]
    if total < 50:
        _inyectar_palabras_base(cur)
        con.commit()
    con.close()


def _inyectar_palabras_base(cur):
    palabras = [
        ("mari", "hola", "saludo", "Saludo comun"),
        ("akua", "gracias", "saludo", "Agradecimiento"),
        ("mari akua", "buenos dias", "saludo", ""),
        ("mari sey", "buenas tardes", "saludo", "Literal: hola sol"),
        ("namu", "adios", "saludo", ""),
        ("akua tayra", "de nada", "saludo", ""),
        ("neisa", "bienvenido", "saludo", ""),
        ("mama", "madre", "familia", ""),
        ("tata", "padre", "familia", ""),
        ("yama", "hermano", "familia", ""),
        ("yaku", "hermana", "familia", ""),
        ("gunmu", "hijo", "familia", ""),
        ("nunu", "hija", "familia", ""),
        ("senenu", "abuelo", "familia", ""),
        ("nunulu", "abuela", "familia", ""),
        ("mauna", "tio", "familia", ""),
        ("naula", "tia", "familia", ""),
        ("kenu", "esposo", "familia", ""),
        ("kenua", "esposa", "familia", ""),
        ("guamnu", "familia", "familia", ""),
        ("guamunu", "nino", "familia", ""),
        ("guamu", "mayor / anciano", "familia", ""),
        ("sey", "sol", "naturaleza", ""),
        ("kunka", "luna", "naturaleza", ""),
        ("guni", "estrella", "naturaleza", ""),
        ("gwa", "agua", "naturaleza", ""),
        ("tayra", "tierra", "naturaleza", "Tambien: territorio"),
        ("uri", "fuego", "naturaleza", ""),
        ("sianku", "viento", "naturaleza", ""),
        ("kan", "rio", "naturaleza", ""),
        ("sia", "lluvia", "naturaleza", ""),
        ("kasku", "montana", "naturaleza", ""),
        ("kuamu", "bosque", "naturaleza", ""),
        ("kamuku", "selva", "naturaleza", ""),
        ("sierra", "sierra nevada", "naturaleza", ""),
        ("dugumu", "rio grande", "naturaleza", ""),
        ("nabusikua", "bahia sin fin", "naturaleza", ""),
        ("tukunu", "laguna", "naturaleza", ""),
        ("duga", "perro", "animal", ""),
        ("kumina", "tortuga", "animal", ""),
        ("tuli", "pez", "animal", ""),
        ("kuamu", "jaguar", "animal", "Tambien: felino grande"),
        ("gawa", "pajaro", "animal", ""),
        ("kuse", "mono", "animal", ""),
        ("sugu", "serpiente", "animal", ""),
        ("tikuku", "rana", "animal", ""),
        ("nusku", "cangrejo", "animal", ""),
        ("uwa", "venado", "animal", ""),
        ("kakua", "cocodrilo", "animal", ""),
        ("nui", "lapa", "animal", ""),
        ("kui", "cabeza", "cuerpo", ""),
        ("tui", "ojo", "cuerpo", ""),
        ("nuaka", "boca", "cuerpo", ""),
        ("tuku", "mano", "cuerpo", ""),
        ("guta", "pie", "cuerpo", ""),
        ("siwa", "pecho", "cuerpo", ""),
        ("duga", "pierna", "cuerpo", ""),
        ("kunu", "comer", "accion", ""),
        ("wina", "beber", "accion", ""),
        ("kua", "ir", "accion", ""),
        ("dama", "hablar", "accion", ""),
        ("nua", "ver", "accion", ""),
        ("kama", "trabajar", "accion", ""),
        ("sama", "dormir", "accion", ""),
        ("bua", "caminar", "accion", ""),
        ("gana", "cantar", "accion", ""),
        ("tama", "bailar", "accion", ""),
        ("kuka", "sembrar", "accion", ""),
        ("nuaka", "cocinar", "accion", ""),
        ("kaku", "pescar", "accion", ""),
        ("siwa", "curar", "accion", ""),
        ("gwa", "cargar", "accion", ""),
        ("musi", "uno", "numero", ""),
        ("maka", "dos", "numero", ""),
        ("tsaipku", "tres", "numero", ""),
        ("tsaink", "cuatro", "numero", ""),
        ("tsaimu", "cinco", "numero", ""),
        ("saiqa", "seis", "numero", ""),
        ("tukusaiqa", "siete", "numero", ""),
        ("musikusa", "diez", "numero", ""),
        ("bunsi", "bueno", "general", ""),
        ("bunsiaku", "muy bueno", "general", ""),
        ("karu", "grande", "general", ""),
        ("uri", "pequeno", "general", ""),
        ("nusu", "yo", "general", ""),
        ("maku", "tu", "general", ""),
        ("gunu", "el / ella", "general", ""),
        ("namu", "nosotros", "general", ""),
        ("makui", "ustedes", "general", ""),
        ("gunu", "ellos", "general", ""),
        ("sia", "si", "general", ""),
        ("nia", "no", "general", ""),
        ("neisa", "verdad", "general", ""),
        ("kama", "asi es", "general", ""),
        ("teku", "lugar", "general", ""),
        ("guamu", "tiempo", "general", ""),
        ("tukui", "mujer", "general", ""),
        ("tuku", "hombre", "general", ""),
        ("daku", "palabra", "general", ""),
        ("kunsamuna", "pensamiento", "general", ""),
        ("gunuku", "camino", "general", ""),
        ("tukunu", "escuela", "general", ""),
        ("kanuku", "gobierno", "general", ""),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO dictionary (kogui, spanish, categoria, notas, fecha) VALUES (?, ?, ?, ?, '')",
        [(k, e, c, n) for k, e, c, n in palabras]
    )


# ── Traduccion ─────────────────────────────────────────────────────────

def buscar_frase_en_diccionario(texto, direccion="k2e"):
    con = db.conectar()
    cur = con.cursor()
    texto_limpio = texto.strip().lower().strip(".,!?;:")
    palabras = texto_limpio.split()
    resultado = []
    i = 0
    while i < len(palabras):
        encontrado = False
        for longitud in range(min(5, len(palabras) - i), 0, -1):
            frase = " ".join(palabras[i:i+longitud])
            if direccion == "k2e":
                cur.execute("SELECT spanish FROM dictionary WHERE LOWER(kogui) = LOWER(?)", (frase,))
            else:
                cur.execute("SELECT kogui FROM dictionary WHERE LOWER(spanish) = LOWER(?)", (frase,))
            res = cur.fetchone()
            if res:
                resultado.append({"frase": frase, "traduccion": res[0], "longitud": longitud})
                i += longitud
                encontrado = True
                break
        if not encontrado:
            resultado.append({"frase": palabras[i], "traduccion": f"[{palabras[i]}]", "longitud": 1})
            i += 1
    con.close()
    return resultado


def traducir_inteligente(texto, direccion):
    texto_limpio = texto.strip().strip(".,!?;:").lower()
    if not texto_limpio:
        return None, "no_encontrado"

    frase_resultado = buscar_frase_en_diccionario(texto_limpio, direccion)
    if frase_resultado:
        traducciones = [r["traduccion"] for r in frase_resultado]
        sin_traducir = [r for r in frase_resultado if r["traduccion"].startswith("[")]
        traduccion_completa = " ".join(traducciones)
        if not sin_traducir:
            return traduccion_completa, "diccionario"
        elif len(sin_traducir) < len(frase_resultado):
            return traduccion_completa, "diccionario_parcial"

    encontradas = db.buscar_en_diccionario(texto_limpio, direccion)
    if encontradas:
        palabras = texto_limpio.split()
        resultado = []
        todas = True
        for p in palabras:
            p_limpia = p.strip(".,!?;:")
            if p_limpia in encontradas:
                resultado.append(encontradas[p_limpia])
            else:
                todas = False
                resultado.append(f"[{p_limpia}]")
        if todas:
            return " ".join(resultado), "diccionario"
        else:
            return " ".join(resultado), "diccionario_parcial"

    return None, "no_encontrado"


# ── Audio Desktop ──────────────────────────────────────────────────────

def _hablar_desktop(texto):
    mp3_path = None
    try:
        from gtts import gTTS
        tts = gTTS(text=texto, lang='es', slow=False)
        mp3_path = tempfile.mktemp(suffix='.mp3')
        tts.save(mp3_path)
        if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
            return
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
    except Exception as e:
        print(f"Error audio desktop: {e}")
    finally:
        if mp3_path and os.path.exists(mp3_path):
            try:
                pygame.mixer.music.unload()
                os.unlink(mp3_path)
            except Exception:
                pass


def hablar(texto):
    if IS_ANDROID:
        audio_backend.hablar(texto)
    else:
        _hablar_desktop(texto)


# ── Grabacion Desktop ──────────────────────────────────────────────────

def _grabar_desktop():
    global grabando, audio_chunks
    audio_chunks = []

    def callback(indata, frames, time_info, status):
        if grabando:
            audio_chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='float32', callback=callback):
        while grabando:
            time.sleep(0.02)


def iniciar_grabacion():
    global grabando
    if IS_ANDROID:
        grabando = True
        return
    grabando = True


def detener_grabacion():
    global grabando
    grabando = False
    if IS_ANDROID:
        return


# ── Procesar resultado ─────────────────────────────────────────────────

def procesar_texto(texto):
    global procesando
    if procesando or not texto:
        return
    procesando = True
    try:
        set_status(f"Original: {texto}")
        origen = "Kogui" if modo == "k2e" else "Espanol"
        destino = "Espanol" if modo == "k2e" else "Kogui"
        traduccion, fuente = traducir_inteligente(texto, modo)

        if fuente == "no_encontrado":
            set_status(f"'{texto}' no encontrado en diccionario")
            return

        db.guardar_conversacion(texto, traduccion, modo, fuente)

        resultado_texto = f"{origen}: {texto}\n{destino}: {traduccion}"
        set_status(resultado_texto)

        _kivy_ui(lambda: agregar_item_historial(texto, traduccion, origen, destino, fuente))

        hablar(traduccion)
        set_status(f"{origen} -> {destino}: {traduccion}")
    except Exception as e:
        set_status(f"Error: {type(e).__name__}: {e}")
        print(f"[MINKA] Error: {traceback.format_exc()}")
    finally:
        procesando = False


def _procesar_android_resultado(texto):
    if texto:
        procesar_texto(texto)
    else:
        set_status("No se entiende, intenta de nuevo")


# ── Historial ──────────────────────────────────────────────────────────

def agregar_item_historial(original, traducido, origen, destino, fuente):
    if _historial_list is None:
        return
    color = [0, 0.6, 0, 1] if fuente == "diccionario" else [1, 0.6, 0, 1]

    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label

    item = BoxLayout(
        orientation='vertical', size_hint_y=None, height=55,
        padding=[8, 4, 8, 4], spacing=1,
    )
    with item.canvas.before:
        from kivy.graphics import Color, RoundedRectangle
        Color(0.92, 0.92, 0.92, 1)
        RoundedRectangle(pos=item.pos, size=item.size, radius=[6])

    header = BoxLayout(size_hint_y=None, height=18, spacing=4)
    header.add_widget(Label(
        text=f"{origen} -> {destino}",
        font_size=10, color=[0.5, 0.5, 0.5, 1], halign='left', size_hint_x=0.7,
        text_size=(None, None),
    ))
    src_label = Label(
        text=fuente, font_size=9, color=[1, 1, 1, 1],
        size_hint_x=0.3, halign='right',
    )
    with src_label.canvas.before:
        from kivy.graphics import Color
        Color(*color)
    header.add_widget(src_label)

    item.add_widget(header)
    item.add_widget(Label(
        text=f"{original}", font_size=12, color=[0.2, 0.2, 0.2, 1],
        halign='left', size_hint_y=None, height=18,
        text_size=(None, None),
    ))
    item.add_widget(Label(
        text=f"{traducido}", font_size=12, color=[0, 0, 0.7, 1],
        halign='left', size_hint_y=None, height=18,
        text_size=(None, None),
    ))

    _historial_list.add_widget(item, index=0)
    if len(_historial_list.children) > 30:
        _historial_list.remove_widget(_historial_list.children[-1])


# ── Interfaz Kivy ──────────────────────────────────────────────────────

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.clock import Clock


class MinkaApp(App):
    def build(self):
        global _status_label, _historial_list, _mic_btn, _modo_btn

        Window.clearcolor = [0.95, 0.95, 0.95, 1]
        if not IS_ANDROID:
            Window.size = (420, 720)

        root = BoxLayout(orientation='vertical', padding=12, spacing=8)

        # ── Header ──
        header = BoxLayout(size_hint_y=None, height=44, spacing=8)
        header.add_widget(Label(
            text="[color=2e7d32][b]MINKA VOZ[/b][/color]",
            font_size=22, markup=True, halign='left', size_hint_x=0.7,
            text_size=(None, None),
        ))
        theme_btn = Button(
            text="[b]Tema[/b]", markup=True, font_size=12,
            size_hint=(0.15, 1), background_color=[0.3, 0.3, 0.3, 1],
            color=[1, 1, 1, 1],
        )
        theme_btn.bind(on_press=self.toggle_theme)
        header.add_widget(theme_btn)
        root.add_widget(header)

        root.add_widget(Label(
            text="Traductor Kogui <-> Espanol",
            font_size=13, color=[0.5, 0.5, 0.5, 1],
            size_hint_y=None, height=20,
        ))

        # ── Botones modo y diccionario ──
        btns_row = BoxLayout(size_hint_y=None, height=36, spacing=8)
        _modo_btn = Button(
            text="[b]Kogui -> Espanol[/b]", markup=True, font_size=12,
            background_color=[0.1, 0.5, 0.9, 1], color=[1, 1, 1, 1],
        )
        _modo_btn.bind(on_press=self.cambiar_modo)
        btns_row.add_widget(_modo_btn)

        dict_btn = Button(
            text="[b]Diccionario[/b]", markup=True, font_size=12,
            background_color=[0.2, 0.7, 0.3, 1], color=[1, 1, 1, 1],
        )
        dict_btn.bind(on_press=self.abrir_diccionario)
        btns_row.add_widget(dict_btn)
        root.add_widget(btns_row)

        # ── Area de estado ──
        _status_label = Label(
            text="Cargando...", font_size=13, color=[0.3, 0.3, 0.3, 1],
            size_hint_y=None, height=40, halign='center',
            text_size=(Window.width - 40, None),
        )
        root.add_widget(_status_label)

        # ── Boton mic ──
        mic_area = BoxLayout(size_hint_y=None, height=100)
        _mic_btn = Button(
            text="[b]MIC[/b]", markup=True, font_size=22,
            background_color=[0.1, 0.4, 0.9, 1], color=[1, 1, 1, 1],
            size_hint=(0.45, 0.9), pos_hint={'center_x': 0.5, 'center_y': 0.5},
        )
        _mic_btn.bind(on_press=self.on_mic_press)
        _mic_btn.bind(on_release=self.on_mic_release)
        mic_area.add_widget(_mic_btn)
        root.add_widget(mic_area)

        # ── Historial ──
        root.add_widget(Label(
            text="[b]Historial[/b]", markup=True, font_size=14,
            halign='left', size_hint_y=None, height=24,
            text_size=(None, None), padding=[4, 0],
        ))

        scroll = ScrollView(size_hint_y=1)
        _historial_list = BoxLayout(
            orientation='vertical', size_hint_y=None, spacing=4, padding=[0, 4],
        )
        _historial_list.bind(minimum_height=_historial_list.setter('height'))
        scroll.add_widget(_historial_list)
        root.add_widget(scroll)

        # ── Cargar modelo en background ──
        threading.Thread(target=cargar_modelo_whisper, daemon=True).start()

        return root

    # ── Eventos ──

    def on_mic_press(self, instance):
        global grabando
        if procesando:
            return
        grabando = True
        _mic_btn.background_color = [0.9, 0.2, 0.2, 1]
        _mic_btn.text = "[b]...[/b]"
        set_status("Grabando... habla ahora")

        if IS_ANDROID:
            def on_resultado(texto):
                global grabando
                grabando = False
                _kivy_ui(lambda: (
                    setattr(_mic_btn, 'background_color', [0.1, 0.4, 0.9, 1]),
                    setattr(_mic_btn, 'text', '[b]MIC[/b]'),
                ))
                _procesar_android_resultado(texto)
            audio_backend.iniciar_grabacion(on_resultado)
        else:
            threading.Thread(target=_grabar_desktop, daemon=True).start()

    def on_mic_release(self, instance):
        global grabando
        if not grabando:
            return
        grabando = False
        _mic_btn.background_color = [0.1, 0.4, 0.9, 1]
        _mic_btn.text = "[b]MIC[/b]"

        if IS_ANDROID:
            audio_backend.detener_grabacion()
        else:
            Clock.schedule_once(lambda dt: self._procesar_desktop(), 0.3)

    def _procesar_desktop(self):
        global audio_chunks
        if not audio_chunks:
            set_status("No se grabo audio")
            return

        audio = np.concatenate(audio_chunks, axis=0)
        duracion = len(audio) / SAMPLE_RATE
        if duracion < MIN_DURACION:
            set_status("Muy corto, habla mas fuerte y mas tiempo")
            return

        set_status("Transcribiendo...")
        tmp_path = os.path.join(tempfile.gettempdir(), f"minka_rec_{int(time.time())}.wav")
        sf.write(tmp_path, audio, SAMPLE_RATE)
        lang = "es" if modo == "e2k" else None
        try:
            resultado = modelo_whisper.transcribe(
                tmp_path, language=lang, fp16=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.4,
                temperature=0,
            )
            texto = resultado["text"].strip()
        except Exception as e:
            texto = ""
            print(f"Error Whisper: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except PermissionError:
                pass

        if texto:
            procesar_texto(texto)
        else:
            set_status("No se entiende, intenta de nuevo")

    def cambiar_modo(self, instance):
        global modo
        modo = "e2k" if modo == "k2e" else "k2e"
        _modo_btn.text = f"[b]{'Espanol' if modo == 'e2k' else 'Kogui'} -> {'Kogui' if modo == 'e2k' else 'Espanol'}[/b]"

    def toggle_theme(self, instance):
        if Window.clearcolor == [0.95, 0.95, 0.95, 1]:
            Window.clearcolor = [0.12, 0.12, 0.14, 1]
            if _status_label:
                _status_label.color = [0.8, 0.8, 0.8, 1]
        else:
            Window.clearcolor = [0.95, 0.95, 0.95, 1]
            if _status_label:
                _status_label.color = [0.3, 0.3, 0.3, 1]

    # ── Diccionario ──

    def abrir_diccionario(self, instance):
        content = BoxLayout(orientation='vertical', spacing=8, padding=8)

        search = TextInput(
            hint_text="Buscar palabra...", size_hint_y=None, height=36,
            multiline=False, font_size=14,
        )
        content.add_widget(search)

        scroll = ScrollView()
        word_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        word_list.bind(minimum_height=word_list.setter('height'))
        scroll.add_widget(word_list)
        content.add_widget(scroll)

        add_row = BoxLayout(size_hint_y=None, height=40, spacing=4)
        add_kogui = TextInput(hint_text="Kogui", size_hint_x=0.3, font_size=12, multiline=False)
        add_espanol = TextInput(hint_text="Espanol", size_hint_x=0.3, font_size=12, multiline=False)
        add_btn = Button(text="Agregar", size_hint_x=0.2, font_size=11, background_color=[0.2, 0.7, 0.3, 1], color=[1, 1, 1, 1])
        add_row.add_widget(add_kogui)
        add_row.add_widget(add_espanol)
        add_row.add_widget(add_btn)
        content.add_widget(add_row)

        popup = Popup(
            title="Diccionario Kogui", content=content,
            size_hint=(0.9, 0.8), auto_dismiss=True,
        )

        def cargar_lista(filtro=""):
            word_list.clear_widgets()
            palabras = db.obtener_todas_palabras()
            for p in palabras:
                pid, kogui, espanol, cat, notas, fecha = p
                if filtro and filtro.lower() not in kogui.lower() and filtro.lower() not in espanol.lower():
                    continue
                row = BoxLayout(size_hint_y=None, height=32, spacing=4)
                row.add_widget(Label(
                    text=f"{espanol} = {kogui}  [{cat}]",
                    font_size=11, halign='left', size_hint_x=0.8,
                    text_size=(None, None),
                ))
                del_btn = Button(text="X", size_hint_x=0.1, font_size=10, background_color=[0.8, 0.2, 0.2, 1], color=[1, 1, 1, 1])
                del_btn.bind(on_press=lambda btn, pid=pid: (db.eliminar_palabra(pid), cargar_lista(search.text)))
                row.add_widget(del_btn)
                word_list.add_widget(row)

        def on_search(text, *args):
            cargar_lista(text)

        def on_add(instance):
            k = add_kogui.text.strip()
            e = add_espanol.text.strip()
            if k and e:
                db.agregar_palabra(k, e)
                add_kogui.text = ""
                add_espanol.text = ""
                cargar_lista(search.text)

        search.bind(text=on_search)
        add_btn.bind(on_press=on_add)
        cargar_lista()
        popup.open()


if __name__ == "__main__":
    inicializar_db()
    MinkaApp().run()
