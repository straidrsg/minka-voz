"""
Backend Android - Usa APIs nativas de Android via pyjnius
Sin internet, sin Whisper, sin gTTS
"""

import os
import time
import tempfile
import threading

# pyjnius para acceder a APIs Java de Android
from jnius import autoclass, cast

# Android Java classes
Context = autoclass('android.content.Context')
PythonActivity = autoclass('org.kivy.android.PythonActivity')
SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
RecognitionListener = autoclass('android.speech.RecognitionListener')
Intent = autoclass('android.content.Intent')
RecognizerIntent = autoclass('android.speech.RecognizerIntent')
TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
Locale = autoclass('java.util.Locale')
Bundle = autoclass('android.os.Bundle')
AudioFormat = autoclass('android.media.AudioFormat')
AudioRecord = autoclass('android.media.AudioRecord')
MediaRecorder = autoclass('android.media.MediaRecorder')

activity = PythonActivity.mActivity
SAMPLE_RATE = 16000

# ── Text-to-Speech nativo ───────────────────────────────────────────────────────
tts_engine = None
tts_ready = False

def init_tts():
    global tts_engine, tts_ready
    if tts_ready:
        return
    def _init():
        global tts_engine, tts_ready
        tts_engine = TextToSpeech(activity, None)
        time.sleep(0.5)
        result = tts_engine.setLanguage(Locale("es"))
        tts_ready = True
    threading.Thread(target=_init, daemon=True).start()

def hablar(texto: str):
    init_tts()
    timeout = 0
    while not tts_ready and timeout < 30:
        time.sleep(0.5)
        timeout += 1
    if tts_engine:
        tts_engine.speak(texto, TextToSpeech.QUEUE_FLUSH, None, "minka_tts")

# ── Speech-to-Text nativo ───────────────────────────────────────────────────────
resultado_transcripcion = None
grabando = False

def grabar_y_transcribir(callback_resultado):
    """Usa el reconocimiento de voz nativo de Android"""
    global resultado_transcripcion
    resultado_transcripcion = None

    recognizer = SpeechRecognizer.createSpeechRecognizer(activity)

    class Listener(RecognitionListener):
        def onReadyForSpeech(self, params):
            pass
        def onBeginningOfSpeech(self):
            pass
        def onRmsChanged(self, rmsdB):
            pass
        def onBufferReceived(self, buffer):
            pass
        def onEndOfSpeech(self):
            pass
        def onError(self, error):
            callback_resultado(None)
        def onResults(self, results):
            matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            if matches and matches.size() > 0:
                callback_resultado(matches.get(0))
            else:
                callback_resultado(None)
        def onPartialResults(self, partialResults):
            pass
        def onEvent(self, eventType, params):
            pass

    recognizer.setRecognitionListener(Listener())

    intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
    intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
    intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es")
    intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es")
    intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)

    recognizer.startListening(intent)

def iniciar_grabacion(callback_resultado):
    global grabando
    grabando = True
    grabar_y_transcribir(callback_resultado)

def detener_grabacion():
    global grabando
    grabando = False