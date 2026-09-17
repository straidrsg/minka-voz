#!/usr/bin/env python3
"""
MINKA VOZ - Mobile (Android)
Traductor de voz Kogui <-> Espanol
APIs nativas Android - Sin internet
"""

import os
import sys
import time
import threading
import warnings
import flet as ft
import database as db

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

is_android = hasattr(sys, 'getandroidapilevel')

if is_android:
    import android_backend as audio
else:
    import tempfile
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    import whisper
    from gtts import gTTS
    import pygame

SAMPLE_RATE = 16000
MIN_DURACION = 0.3

grabando = False
modo = "k2e"
procesando = False
modelo_whisper = None
historial_items = []
historial_column_ref = None
page_ref = None

def snack(msg, color=None):
    if not page_ref:
        return
    snack_bar = ft.SnackBar(content=ft.Text(msg), bgcolor=color, open=True)
    page_ref.overlay.append(snack_bar)
    page_ref.update()
    threading.Thread(target=lambda: (
        time.sleep(3),
        setattr(snack_bar, 'open', False),
        page_ref.update(),
        page_ref.overlay.remove(snack_bar)
    ), daemon=True).start()

def cargar_modelos(status_text):
    global modelo_whisper
    if is_android:
        status_text.value = "Listo - Toca para grabar"
    else:
        status_text.value = "Cargando Whisper (small)..."
        import whisper as w
        modelo_whisper = w.load_model("small")
        status_text.value = "Listo - Manten presionado para grabar"
    if page_ref:
        page_ref.update()

def traducir_inteligente(texto, direccion):
    texto_limpio = texto.strip().strip(".,!?;:").lower()
    if not texto_limpio:
        return None, "no_encontrado"

    frase_resultado = db.buscar_frase_en_diccionario(texto_limpio, direccion)
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

def procesar_texto(texto, status_text, page):
    global procesando
    if procesando or not texto:
        return
    procesando = True
    try:
        status_text.value = f"Original: {texto}"
        page.update()

        origen = "Kogui" if modo == "k2e" else "Espanol"
        destino = "Espanol" if modo == "k2e" else "Kogui"

        traduccion, fuente = traducir_inteligente(texto, modo)

        if fuente == "no_encontrado":
            status_text.value = f"'{texto}' no encontrado"
            page.update()
            return

        agregar_al_historial(texto, traduccion, origen, destino, fuente)
        status_text.value = f"{origen}: {texto}\n{destino}: {traduccion}"
        page.update()

        if is_android:
            audio.hablar(traduccion)
        else:
            _hablar_desktop(traduccion)

        status_text.value = f"{origen} -> {destino}: {traduccion}"
        page.update()
    except Exception as e:
        status_text.value = f"Error: {e}"
        page.update()
    finally:
        procesando = False

if not is_android:
    def _hablar_desktop(texto):
        mp3_path = None
        try:
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
            print(f"Error audio: {e}")
        finally:
            if mp3_path and os.path.exists(mp3_path):
                try:
                    pygame.mixer.music.unload()
                    os.unlink(mp3_path)
                except Exception:
                    pass

def procesar_android_resultado(texto, status_text, page):
    if texto:
        procesar_texto(texto, status_text, page)
    else:
        status_text.value = "No se entiende, intenta de nuevo"
        page.update()

def iniciar_grabacion_btn(icon, status_text, page):
    global grabando
    if grabando or procesando:
        return
    grabando = True
    icon.name = ft.Icons.STOP_CIRCLE
    icon.color = ft.Colors.RED
    status_text.value = "Grabando... habla ahora"
    page.update()

    if is_android:
        def on_resultado(texto):
            global grabando
            grabando = False
            icon.name = ft.Icons.MIC
            icon.color = ft.Colors.BLUE
            page.update()
            procesar_android_resultado(texto, status_text, page)
        audio.iniciar_grabacion(on_resultado)
    else:
        threading.Thread(target=_grabar_desktop, args=(icon, status_text, page), daemon=True).start()

if not is_android:
    audio_chunks = []

    def _grabar_desktop(icon, status_text, page):
        global grabando, audio_chunks, modelo_whisper
        audio_chunks = []

        def callback(indata, frames, time_info, status):
            if grabando:
                audio_chunks.append(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', callback=callback):
            while grabando:
                time.sleep(0.02)

        if not audio_chunks:
            return

        audio = np.concatenate(audio_chunks, axis=0)
        duracion = len(audio) / SAMPLE_RATE
        if duracion < MIN_DURACION:
            icon.name = ft.Icons.MIC
            icon.color = ft.Colors.BLUE
            status_text.value = "Muy corto, habla mas fuerte y mas tiempo"
            page.update()
            return

        status_text.value = "Transcribiendo..."
        page.update()
        tmp_path = tempfile.mktemp(suffix='.wav')
        sf.write(tmp_path, audio, SAMPLE_RATE)
        lang = "es" if modo == "e2k" else None
        resultado = modelo_whisper.transcribe(
            tmp_path,
            language=lang,
            fp16=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            temperature=0,
        )
        texto = resultado["text"].strip()
        try:
            os.unlink(tmp_path)
        except PermissionError:
            pass
        procesar_android_resultado(texto, status_text, page)

def detener_grabacion_btn(icon, status_text, page):
    global grabando
    if not grabando:
        return
    grabando = False
    if is_android:
        audio.detener_grabacion()
    icon.name = ft.Icons.MIC
    icon.color = ft.Colors.BLUE
    page.update()

def agregar_al_historial(original, traducido, origen, destino, fuente):
    global historial_items, historial_column_ref
    color = ft.Colors.GREEN if fuente == "diccionario" else ft.Colors.ORANGE
    item = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text(f"{origen} -> {destino}", size=11, color=ft.Colors.GREY),
                ft.Container(
                    content=ft.Text(fuente, size=9, color=ft.Colors.WHITE),
                    bgcolor=color,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=4,
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text(original, size=13, weight=ft.FontWeight.W_500),
            ft.Text(traducido, size=13, color=ft.Colors.BLUE, weight=ft.FontWeight.W_500),
        ], spacing=4),
        padding=10,
        bgcolor=ft.Colors.GREY_50,
        border_radius=8,
        margin=ft.Margin.only(bottom=8),
    )
    historial_items.insert(0, item)
    if historial_column_ref:
        historial_column_ref.controls = historial_items[:20]
        historial_column_ref.update()

def cerrar_dialog(page, dlg):
    dlg.open = False
    page.update()

# ── Diccionario ─────────────────────────────────────────────────────────────────
def abrir_diccionario(page):
    dlg = ft.AlertDialog(
        title=ft.Row([ft.Text("Diccionario Kogui")]),
        content=ft.Container(
            content=crear_vista_diccionario(page),
            width=500,
            height=450,
        ),
        actions=[ft.TextButton(content=ft.Text("Cerrar"), on_click=lambda e: cerrar_dialog(page, dlg))],
        modal=True,
    )
    page.show_dialog(dlg)

def crear_vista_diccionario(page):
    palabras_cache = []
    search_term = ft.Ref[ft.TextField]()
    lista_column = ft.Ref[ft.Column]()

    def cargar_palabras():
        nonlocal palabras_cache
        palabras_cache = db.obtener_todas_palabras()
        filtrar_y_mostrar("")

    def filtrar_y_mostrar(termino):
        if not lista_column.current:
            return
        filtradas = [p for p in palabras_cache if termino.lower() in p[1].lower() or termino.lower() in p[2].lower()]
        lista_column.current.controls = [crear_fila_palabra(p, page, cargar_palabras) for p in filtradas]
        lista_column.current.update()

    def on_search_change(e):
        filtrar_y_mostrar(e.control.value)

    cargar_palabras()

    vista_lista = ft.Container(
        content=ft.Column([
            ft.TextField(ref=search_term, label="Buscar", prefix_icon=ft.Icons.SEARCH, on_change=on_search_change, expand=True),
            ft.Divider(),
            ft.Container(
                content=ft.Column(ref=lista_column, scroll=ft.ScrollMode.AUTO, spacing=4),
                height=320, expand=True,
            ),
        ], spacing=10),
        padding=10, visible=True,
    )

    vista_agregar = crear_formulario_agregar(page, cargar_palabras)
    vista_agregar.visible = False

    def ir_lista(e):
        vista_lista.visible = True
        vista_agregar.visible = False
        page.update()

    def ir_agregar(e):
        vista_lista.visible = False
        vista_agregar.visible = True
        page.update()

    nav = ft.Row([
        ft.TextButton(content=ft.Text("Lista"), on_click=ir_lista, style=ft.ButtonStyle(color=ft.Colors.BLUE)),
        ft.TextButton(content=ft.Text("Agregar"), on_click=ir_agregar, style=ft.ButtonStyle(color=ft.Colors.GREEN)),
    ], alignment=ft.MainAxisAlignment.CENTER)

    return ft.Column([nav, vista_lista, vista_agregar], tight=True)

def crear_fila_palabra(palabra, page, callback_recargar):
    pid, kogui, espanol, categoria, notas, fecha = palabra
    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text(espanol, size=13, weight=ft.FontWeight.BOLD),
                ft.Text(kogui, size=11, color=ft.Colors.BLUE),
                ft.Text(f"#{pid} [{categoria}]", size=9, color=ft.Colors.GREY),
            ], spacing=2, expand=True),
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                items=[
                    ft.PopupMenuItem(content=ft.Text("Editar"), on_click=lambda _, p=palabra: abrir_editar(page, p, callback_recargar)),
                    ft.PopupMenuItem(content=ft.Text("Eliminar"), on_click=lambda _, p=palabra: confirmar_eliminar(page, p, callback_recargar)),
                ],
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=10, bgcolor=ft.Colors.GREY_50, border_radius=8,
        border=ft.Border.all(1, ft.Colors.GREY_200),
    )

def crear_formulario_agregar(page, callback_recargar):
    tf_kogui = ft.Ref[ft.TextField]()
    tf_espanol = ft.Ref[ft.TextField]()
    tf_categoria = ft.Ref[ft.Dropdown]()
    tf_notas = ft.Ref[ft.TextField]()

    def guardar(e):
        kogui_val = tf_kogui.current.value.strip()
        espanol_val = tf_espanol.current.value.strip()
        categoria_val = tf_categoria.current.value or "general"
        notas_val = tf_notas.current.value.strip()
        if not kogui_val or not espanol_val:
            snack("Kogui y Espanol son obligatorios", ft.Colors.RED)
            return
        ok, msg = db.agregar_palabra(kogui_val, espanol_val, categoria_val, notas_val)
        if ok:
            snack(f"'{kogui_val}' agregada", ft.Colors.GREEN)
            tf_kogui.current.value = ""
            tf_espanol.current.value = ""
            tf_notas.current.value = ""
            page.update()
            callback_recargar()
        else:
            snack(msg, ft.Colors.ORANGE)

    return ft.Container(
        content=ft.Column([
            ft.TextField(ref=tf_kogui, label="Kogui *", prefix_icon=ft.Icons.TRANSLATE),
            ft.TextField(ref=tf_espanol, label="Espanol *", prefix_icon=ft.Icons.LANGUAGE),
            ft.Dropdown(ref=tf_categoria, label="Categoria", value="general",
                options=[ft.dropdown.Option(c) for c in ["saludo","familia","naturaleza","animal","accion","numero","general"]]),
            ft.TextField(ref=tf_notas, label="Notas", prefix_icon=ft.Icons.NOTES, multiline=True, min_lines=2, max_lines=3),
            ft.ElevatedButton(content=ft.Text("Guardar"), icon=ft.Icons.SAVE, on_click=guardar,
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)),
        ], spacing=15),
        padding=20,
    )

def abrir_editar(page, palabra, callback_recargar):
    pid, kogui, espanol, categoria, notas, fecha = palabra
    tf_kogui = ft.TextField(value=kogui, label="Kogui")
    tf_espanol = ft.TextField(value=espanol, label="Espanol")
    tf_categoria = ft.Dropdown(value=categoria,
        options=[ft.dropdown.Option(c) for c in ["saludo","familia","naturaleza","animal","accion","numero","general"]])
    tf_notas = ft.TextField(value=notas, label="Notas", multiline=True, min_lines=2, max_lines=3)

    def guardar(e):
        ok, msg = db.actualizar_palabra(pid, tf_kogui.value.strip(), tf_espanol.value.strip(), tf_categoria.value or "general", tf_notas.value.strip())
        if ok:
            snack("Actualizada", ft.Colors.GREEN)
            cerrar_dialog(page, dlg)
            callback_recargar()
        else:
            snack(msg, ft.Colors.ORANGE)

    dlg = ft.AlertDialog(
        title=ft.Text(f"Editar #{pid}"),
        content=ft.Container(content=ft.Column([tf_kogui, tf_espanol, tf_categoria, tf_notas], spacing=10, tight=True), width=400),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: cerrar_dialog(page, dlg)),
            ft.ElevatedButton(content=ft.Text("Guardar"), on_click=guardar, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)),
        ], modal=True,
    )
    page.show_dialog(dlg)

def confirmar_eliminar(page, palabra, callback_recargar):
    pid, kogui, espanol, categoria, notas, fecha = palabra
    def ejecutar(e):
        db.eliminar_palabra(pid)
        snack("Eliminada", ft.Colors.GREEN)
        cerrar_dialog(page, dlg)
        callback_recargar()
    dlg = ft.AlertDialog(
        title=ft.Text("Eliminar"),
        content=ft.Text(f"Eliminar '{espanol}' -> '{kogui}'?"),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: cerrar_dialog(page, dlg)),
            ft.ElevatedButton(content=ft.Text("Eliminar"), on_click=ejecutar, style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE)),
        ], modal=True,
    )
    page.show_dialog(dlg)

def cambiar_modo(btn_text, page):
    global modo
    modo = "e2k" if modo == "k2e" else "k2e"
    btn_text.value = "Kogui -> Espanol" if modo == "k2e" else "Espanol -> Kogui"
    page.update()

# ── Main ────────────────────────────────────────────────────────────────────────
def main(page: ft.Page):
    global historial_column_ref, page_ref
    page_ref = page
    page.title = "MINKA VOZ"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20

    if not is_android:
        page.window.width = 500
        page.window.height = 700
        page.window.resizable = True

    status_text = ft.Text("Cargando...", size=14, color=ft.Colors.GREY_600)
    historial_column = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
    historial_column_ref = historial_column

    mic_icon = ft.Icon(ft.Icons.MIC, size=48, color=ft.Colors.BLUE)

    def on_mic_tap_down(e):
        iniciar_grabacion_btn(mic_icon, status_text, page)

    def on_mic_tap_up(e):
        detener_grabacion_btn(mic_icon, status_text, page)

    gesto = ft.GestureDetector(
        content=ft.Container(
            content=mic_icon,
            width=96, height=96,
            border_radius=48,
            bgcolor=ft.Colors.BLUE_50,
            alignment=ft.alignment.Alignment.CENTER,
        ),
        on_tap_down=on_mic_tap_down,
        on_tap_up=on_mic_tap_up,
        on_tap_cancel=on_mic_tap_up,
    )

    btn_modo_text = ft.Text("Kogui -> Espanol")
    btn_modo = ft.TextButton(
        content=btn_modo_text,
        on_click=lambda e: cambiar_modo(btn_modo_text, page),
        style=ft.ButtonStyle(color=ft.Colors.BLUE),
    )

    btn_dict = ft.TextButton(
        content=ft.Text("Diccionario"),
        on_click=lambda e: abrir_diccionario(page),
        style=ft.ButtonStyle(color=ft.Colors.GREEN),
    )

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
        page.update()

    btn_theme = ft.IconButton(icon=ft.Icons.DARK_MODE, icon_size=20, tooltip="Tema", on_click=toggle_theme)

    page.add(
        ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.NATURE, size=32, color=ft.Colors.GREEN),
                ft.Text("MINKA VOZ", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800),
                btn_theme,
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("Traductor Kogui <-> Espanol", size=14, color=ft.Colors.GREY_600),
            ft.Divider(),
            ft.Row([btn_modo, btn_dict], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(content=gesto, alignment=ft.alignment.Alignment.CENTER, padding=20),
            ft.Container(content=status_text, padding=10, alignment=ft.alignment.Alignment.CENTER),
            ft.Divider(),
            ft.Text("Historial", size=16, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Column([historial_column], scroll=ft.ScrollMode.AUTO),
                height=250, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, padding=10,
            ),
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    )

    threading.Thread(target=lambda: cargar_modelos(status_text), daemon=True).start()

if __name__ == "__main__":
    db.inicializar_db()
    ft.app(target=main)