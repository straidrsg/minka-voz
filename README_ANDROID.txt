MINKA VOZ — Android
====================

Traductor de voz Kogui <-> Español para Android. 100% offline, APIs nativas.

INSTALACION
-----------
1. Copia "minka-voz-main.apk" al celular (USB, Bluetooth, correo, etc.)
2. En el celular: Ajustes > Seguridad > "Instalar apps de fuentes desconocidas" -> ACTIVADO
3. Abre el .apk desde el administrador de archivos e instala
4. Al abrir por primera vez: concede permiso de MICROFONO

USO
---
- TOCA el microfono (icono azul) y habla
- SUELTA para transcribir y traducir (usa SpeechRecognizer nativo de Android)
- Cambia direccion con el boton "Kogui -> Espanol / Espanol -> Kogui"
- Diccionario: busca, agrega, edita o elimina palabras
- Historial: ve tus traducciones recientes
- Modo oscuro: boton de luna en la esquina

REQUISITOS
----------
- Android 7.0 (API 24) o superior
- Microfono
- NO requiere internet (funciona en modo avion)

TRADUCCION
----------
Usa diccionario local SQLite (~108 palabras base Kogui).
Si la frase no esta completa, traduce palabra por palabra
y marca lo no encontrado con [corchetes].

TECNOLOGIA
----------
- SpeechRecognizer (API nativa Android) para voz -> texto
- TextToSpeech (API nativa Android) para texto -> voz
- Python 3.14 + Flet (Flutter) embebido
- PyJNIus para llamadas JNI
- Tamaño: ~613 MB (incluye runtime Python completo)

NOTAS
-----
- Primera ejecucion: tarda ~5-10 seg en cargar el runtime Python
- No usa Whisper ni modelos pesados -- todo nativo Android
- El diccionario se guarda en almacenamiento interno de la app

ARCHIVOS
--------
build/apk/minka-voz-main.apk    -- APK instalable (~613 MB)