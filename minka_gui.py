#!/usr/bin/env python3
"""
MINKA VOZ — GUI con Flet
Traductor de voz Kogui <-> Español
"""

import os
import sys
import time
import asyncio
import tempfile
import threading
import warnings
import traceback
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
from gtts import gTTS
import pygame
import flet as ft
import database as db

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

SAMPLE_RATE = 16000
CHANNELS = 1
MIN_DURACION = 0.3

grabando = False
audio_chunks = []
modo = "k2e"
procesando = False
modelo_whisper = None
hilo_grab = None
historial_items = []
historial_column_ref = None
page_ref = None

def snack(msg, color=None):
    if not page_ref:
        return
    snack_bar = ft.SnackBar(
        content=ft.Text(msg),
        bgcolor=color,
        open=True,
    )
    page_ref.overlay.append(snack_bar)
    _safe_update(page_ref)
    threading.Thread(target=lambda: (time.sleep(3), setattr(snack_bar, 'open', False), _safe_update(page_ref), page_ref.overlay.remove(snack_bar)), daemon=True).start()

def _safe_update(page: ft.Page):
    """Force UI refresh from background threads"""
    try:
        page.update()
    except Exception:
        pass

async def cargar_modelos(page: ft.Page, status_text: ft.Text, progress_bar: ft.ProgressBar):
    global modelo_whisper
    progress_bar.visible = True
    progress_bar.value = None
    status_text.value = "Cargando modelo de voz..."
    page.update()
    await asyncio.to_thread(_cargar_whisper)
    progress_bar.value = 1.0
    status_text.value = "Whisper listo"
    page.update()
    await asyncio.sleep(0.3)
    status_text.value = "Listo - Manten el boton para grabar"
    page.update()
    await asyncio.sleep(0.5)
    progress_bar.visible = False
    page.update()

def _cargar_whisper():
    global modelo_whisper
    modelo_whisper = whisper.load_model("base")

def _hilo_grabacion():
    global audio_chunks, grabando
    audio_chunks = []

    def callback(indata, frames, time_info, status):
        if grabando:
            audio_chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', callback=callback):
        while grabando:
            time.sleep(0.02)

def iniciar_grabacion(icon: ft.Icon, page: ft.Page):
    global grabando, hilo_grab, audio_chunks
    if grabando:
        return
    grabando = True
    audio_chunks = []
    hilo_grab = threading.Thread(target=_hilo_grabacion, daemon=True)
    hilo_grab.start()
    icon.name = ft.Icons.STOP_CIRCLE
    icon.color = ft.Colors.RED
    _safe_update(page)

def detener_grabacion(icon: ft.Icon, page: ft.Page, status_text: ft.Text):
    global grabando, hilo_grab
    if not grabando:
        return
    grabando = False
    if hilo_grab:
        hilo_grab.join(timeout=1)
    icon.name = ft.Icons.MIC
    icon.color = ft.Colors.BLUE
    page.update()
    page.run_task(_procesar_async, page, status_text)

def hablar(texto: str):
    mp3_path = None
    try:
        tts = gTTS(text=texto, lang='es', slow=False)
        mp3_path = tempfile.mktemp(suffix='.mp3')
        tts.save(mp3_path)
        if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
            print("Error audio: archivo MP3 no se genero")
            return
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
    except FileNotFoundError:
        print("Error audio: pygame o SDL no encontrado")
    except Exception as e:
        print(f"Error audio: {e}")
    finally:
        if mp3_path and os.path.exists(mp3_path):
            try:
                pygame.mixer.music.unload()
                os.unlink(mp3_path)
            except Exception:
                pass

def traducir_inteligente(texto: str, direccion: str):
    texto_limpio = texto.strip().strip(".,!?;:").lower()
    if not texto_limpio:
        return None, "no_encontrado"

    # 1. Buscar frase completa primero
    frase_resultado = db.buscar_frase_en_diccionario(texto_limpio, direccion)
    if frase_resultado:
        traducciones = [r["traduccion"] for r in frase_resultado]
        # Verificar si alguna palabra quedó sin traducir (entre corchetes)
        sin_traducir = [r for r in frase_resultado if r["traduccion"].startswith("[")]
        traduccion_completa = " ".join(traducciones)
        if not sin_traducir:
            return traduccion_completa, "diccionario"
        elif len(sin_traducir) < len(frase_resultado):
            return traduccion_completa, "diccionario_parcial"

    # 2. Fallback: buscar palabra por palabra
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

async def _procesar_async(page: ft.Page, status_text: ft.Text):
    global procesando, audio_chunks, modo
    if procesando or not audio_chunks:
        return
    procesando = True
    try:
        audio = np.concatenate(audio_chunks, axis=0)
        duracion = len(audio) / SAMPLE_RATE
        if duracion < MIN_DURACION:
            status_text.value = "Muy corto, habla mas fuerte y mas tiempo"
            page.update()
            return
        status_text.value = "Transcribiendo..."
        page.update()
        tmp_path = tempfile.mktemp(suffix='.wav')
        sf.write(tmp_path, audio, SAMPLE_RATE)
        lang = "es" if modo == "e2k" else None
        resultado = await asyncio.to_thread(
            modelo_whisper.transcribe,
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
        if not texto:
            status_text.value = "No se entiende, intenta de nuevo"
            page.update()
            return
        origen = "Kogui" if modo == "k2e" else "Espanol"
        destino = "Espanol" if modo == "k2e" else "Kogui"
        status_text.value = "Traduciendo..."
        page.update()
        traduccion, fuente = traducir_inteligente(texto, modo)
        if fuente == "no_encontrado":
            status_text.value = f"'{texto}' no encontrado en diccionario"
            page.update()
            return
        agregar_al_historial(texto, traduccion, origen, destino, fuente)
        status_text.value = f"{origen}: {texto}\n{destino}: {traduccion}"
        page.update()
        status_text.value += "  Reproduciendo..."
        page.update()
        await asyncio.to_thread(hablar, traduccion)
        status_text.value = f"{origen} -> {destino}: {traduccion}"
        page.update()
    except Exception as e:
        status_text.value = f"Error: {type(e).__name__}: {e}"
        page.update()
        print(f"[MINKA] Error en procesar: {traceback.format_exc()}")
    finally:
        procesando = False

def procesar(page: ft.Page, status_text: ft.Text):
    """Legacy sync wrapper"""
    asyncio.run(_procesar_async(page, status_text))

def agregar_al_historial(original, traducido, origen, destino, fuente):
    global historial_items, historial_column_ref
    color = ft.Colors.GREEN if fuente == "diccionario" else ft.Colors.ORANGE
    item = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text(f"{origen} -> {destino}", size=12, color=ft.Colors.GREY),
                ft.Container(
                    content=ft.Text(fuente, size=10, color=ft.Colors.WHITE),
                    bgcolor=color,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=4,
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text(original, size=14, weight=ft.FontWeight.W_500),
            ft.Text(traducido, size=14, color=ft.Colors.BLUE, weight=ft.FontWeight.W_500),
        ], spacing=4),
        padding=12,
        bgcolor=ft.Colors.GREY_50,
        border_radius=8,
        margin=ft.Margin.only(bottom=8),
    )
    historial_items.insert(0, item)
    if historial_column_ref:
        historial_column_ref.controls = historial_items[:20]
        try:
            historial_column_ref.update()
        except Exception:
            pass

def cerrar_dialog(page: ft.Page, dlg):
    dlg.open = False
    page.update()

def abrir_diccionario(page: ft.Page):
    dlg = ft.AlertDialog(
        title=ft.Row([
            ft.Icon(ft.Icons.MENU_BOOK, color=ft.Colors.GREEN),
            ft.Text("Diccionario Kogui"),
        ]),
        content=ft.Container(
            content=crear_vista_diccionario(page),
            width=600,
            height=500,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cerrar"), on_click=lambda e: cerrar_dialog(page, dlg)),
        ],
        modal=True,
    )
    page.show_dialog(dlg)

def crear_vista_diccionario(page: ft.Page):
    palabras_cache = []
    search_term = ft.Ref[ft.TextField]()
    lista_column = ft.Ref[ft.Column]()

    def cargar_palabras():
        nonlocal palabras_cache
        palabras_cache = db.obtener_todas_palabras()
        filtrar_y_mostrar("")

    def filtrar_y_mostrar(termino: str):
        if not lista_column.current:
            return
        filtradas = [
            p for p in palabras_cache
            if termino.lower() in p[1].lower() or termino.lower() in p[2].lower()
        ]
        lista_column.current.controls = [crear_fila_palabra(p, page, cargar_palabras) for p in filtradas]
        lista_column.current.update()

    def on_search_change(e):
        filtrar_y_mostrar(e.control.value)

    cargar_palabras()

    vista_lista = ft.Container(
        content=ft.Column([
            ft.TextField(
                ref=search_term,
                label="Buscar (Kogui o Espanol)",
                prefix_icon=ft.Icons.SEARCH,
                on_change=on_search_change,
                expand=True,
            ),
            ft.Divider(),
            ft.Container(
                content=ft.Column(
                    ref=lista_column,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=4,
                ),
                height=350,
                expand=True,
            ),
        ], spacing=10),
        padding=10,
        visible=True,
    )

    vista_agregar = crear_formulario_agregar(page, cargar_palabras)
    vista_agregar.visible = False

    btn_lista = ft.Ref[ft.TextButton]()
    btn_agregar = ft.Ref[ft.TextButton]()

    def ir_lista(e):
        vista_lista.visible = True
        vista_agregar.visible = False
        btn_lista.current.opacity = 1.0
        btn_agregar.current.opacity = 0.5
        page.update()

    def ir_agregar(e):
        vista_lista.visible = False
        vista_agregar.visible = True
        btn_lista.current.opacity = 0.5
        btn_agregar.current.opacity = 1.0
        page.update()

    nav = ft.Row([
        ft.TextButton(ref=btn_lista, content=ft.Text("Lista"), on_click=ir_lista, style=ft.ButtonStyle(color=ft.Colors.BLUE)),
        ft.TextButton(ref=btn_agregar, content=ft.Text("Agregar"), on_click=ir_agregar, style=ft.ButtonStyle(color=ft.Colors.GREEN)),
    ], alignment=ft.MainAxisAlignment.CENTER)

    return ft.Column([nav, vista_lista, vista_agregar], tight=True)

def crear_fila_palabra(palabra, page: ft.Page, callback_recargar):
    pid, kogui, espanol, categoria, notas, fecha = palabra
    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text(espanol, size=14, weight=ft.FontWeight.BOLD),
                ft.Text(kogui, size=12, color=ft.Colors.BLUE),
                ft.Row([
                    ft.Container(
                        content=ft.Text(categoria, size=10, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.GREEN,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border_radius=4,
                    ),
                    ft.Text(f"#{pid}", size=10, color=ft.Colors.GREY),
                ], spacing=8),
            ], spacing=2, expand=True),
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                items=[
                    ft.PopupMenuItem(
                        content=ft.Text("Editar"),
                        icon=ft.Icons.EDIT,
                        on_click=lambda _, p=palabra: abrir_editar(page, p, callback_recargar),
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text("Eliminar"),
                        icon=ft.Icons.DELETE,
                        on_click=lambda _, p=palabra: confirmar_eliminar(page, p, callback_recargar),
                    ),
                ],
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=12,
        bgcolor=ft.Colors.GREY_50,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.GREY_200),
    )

def crear_formulario_agregar(page: ft.Page, callback_recargar):
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
            ft.TextField(
                ref=tf_kogui,
                label="Palabra en Kogui *",
                prefix_icon=ft.Icons.TRANSLATE,
            ),
            ft.TextField(
                ref=tf_espanol,
                label="Traduccion Espanol *",
                prefix_icon=ft.Icons.LANGUAGE,
            ),
            ft.Dropdown(
                ref=tf_categoria,
                label="Categoria",
                value="general",
                options=[
                    ft.dropdown.Option("saludo"),
                    ft.dropdown.Option("familia"),
                    ft.dropdown.Option("naturaleza"),
                    ft.dropdown.Option("animal"),
                    ft.dropdown.Option("accion"),
                    ft.dropdown.Option("numero"),
                    ft.dropdown.Option("general"),
                ],
            ),
            ft.TextField(
                ref=tf_notas,
                label="Notas (opcional)",
                prefix_icon=ft.Icons.NOTES,
                multiline=True,
                min_lines=2,
                max_lines=3,
            ),
            ft.ElevatedButton(
                content=ft.Text("Guardar"),
                icon=ft.Icons.SAVE,
                on_click=guardar,
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE),
            ),
        ], spacing=15),
        padding=20,
    )

def abrir_editar(page: ft.Page, palabra, callback_recargar):
    pid, kogui, espanol, categoria, notas, fecha = palabra

    tf_kogui = ft.TextField(value=kogui, label="Kogui")
    tf_espanol = ft.TextField(value=espanol, label="Espanol")
    tf_categoria = ft.Dropdown(
        value=categoria,
        options=[
            ft.dropdown.Option("saludo"),
            ft.dropdown.Option("familia"),
            ft.dropdown.Option("naturaleza"),
            ft.dropdown.Option("animal"),
            ft.dropdown.Option("accion"),
            ft.dropdown.Option("numero"),
            ft.dropdown.Option("general"),
        ],
    )
    tf_notas = ft.TextField(value=notas, label="Notas", multiline=True, min_lines=2, max_lines=3)

    def guardar(e):
        ok, msg = db.actualizar_palabra(
            pid,
            tf_kogui.value.strip(),
            tf_espanol.value.strip(),
            tf_categoria.value or "general",
            tf_notas.value.strip()
        )
        if ok:
            snack("Actualizada", ft.Colors.GREEN)
            cerrar_dialog(page, dlg)
            callback_recargar()
        else:
            snack(msg, ft.Colors.ORANGE)

    dlg = ft.AlertDialog(
        title=ft.Text(f"Editar #{pid}"),
        content=ft.Container(
            content=ft.Column([tf_kogui, tf_espanol, tf_categoria, tf_notas], spacing=10, tight=True),
            width=400,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: cerrar_dialog(page, dlg)),
            ft.ElevatedButton(content=ft.Text("Guardar"), on_click=guardar, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)),
        ],
        modal=True,
    )
    page.show_dialog(dlg)

def confirmar_eliminar(page: ft.Page, palabra, callback_recargar):
    pid, kogui, espanol, categoria, notas, fecha = palabra

    def ejecutar_eliminar(e):
        db.eliminar_palabra(pid)
        snack("Eliminada", ft.Colors.GREEN)
        cerrar_dialog(page, dlg)
        callback_recargar()

    dlg = ft.AlertDialog(
        title=ft.Text("Eliminar"),
        content=ft.Text(f"Eliminar '{espanol}' -> '{kogui}' [#{pid}]?"),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: cerrar_dialog(page, dlg)),
            ft.ElevatedButton(
                content=ft.Text("Eliminar"),
                on_click=ejecutar_eliminar,
                style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
            ),
        ],
        modal=True,
    )
    page.show_dialog(dlg)

def cambiar_modo(btn_text: ft.Text, page: ft.Page):
    global modo
    modo = "e2k" if modo == "k2e" else "k2e"
    btn_text.value = "Kogui -> Espanol" if modo == "k2e" else "Espanol -> Kogui"
    page.update()

def main(page: ft.Page):
    global historial_column_ref, page_ref
    page_ref = page
    page.title = "MINKA VOZ"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 500
    page.window.height = 700
    page.window.resizable = True
    page.padding = 20

    status_text = ft.Text("Cargando modelo...", size=14, color=ft.Colors.GREY_600)
    progress_bar = ft.ProgressBar(visible=False, color=ft.Colors.GREEN, bgcolor=ft.Colors.GREY_300, width=300)
    historial_column = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
    historial_column_ref = historial_column

    mic_icon = ft.Icon(ft.Icons.MIC, size=48, color=ft.Colors.BLUE)

    gesto = ft.GestureDetector(
        content=ft.Container(
            content=mic_icon,
            width=96, height=96,
            border_radius=48,
            bgcolor=ft.Colors.BLUE_50,
            alignment=ft.alignment.Alignment.CENTER,
        ),
        on_tap_down=lambda e: iniciar_grabacion(mic_icon, page),
        on_tap_up=lambda e: detener_grabacion(mic_icon, page, status_text),
        on_tap_cancel=lambda e: detener_grabacion(mic_icon, page, status_text),
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

    dark_icon = ft.Icon(ft.Icons.DARK_MODE, size=20)
    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
            dark_icon.name = ft.Icons.LIGHT_MODE
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
            dark_icon.name = ft.Icons.DARK_MODE
        page.update()

    btn_theme = ft.IconButton(
        icon=ft.Icons.DARK_MODE,
        icon_size=20,
        tooltip="Modo oscuro/claro",
        on_click=toggle_theme,
    )

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
            ft.Container(
                content=gesto,
                alignment=ft.alignment.Alignment.CENTER,
                padding=20,
            ),
            ft.Container(
                content=status_text,
                padding=10,
                alignment=ft.alignment.Alignment.CENTER,
            ),
            ft.Container(
                content=progress_bar,
                padding=ft.Padding.only(left=20, right=20),
                alignment=ft.alignment.Alignment.CENTER,
            ),
            ft.Divider(),
            ft.Text("Historial", size=16, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Column([historial_column], scroll=ft.ScrollMode.AUTO),
                height=250,
                border=ft.Border.all(1, ft.Colors.GREY_300),
                border_radius=8,
                padding=10,
            ),
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    )

    page.run_task(cargar_modelos, page, status_text, progress_bar)

if __name__ == "__main__":
    db.inicializar_db()
    ft.app(target=main)
