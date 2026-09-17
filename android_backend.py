"""
Backend Android - APIs nativas de Android via pyjnius
Sin internet, sin Whisper, sin gTTS
Funciona solo cuando se ejecuta en Android (python-for-android)
"""

import os
import time
import threading
import traceback

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

activity = PythonActivity.mActivity


# ── Text-to-Speech ─────────────────────────────────────────────────────

tts_engine = None
tts_ready = False
_tts_lock = threading.Lock()


def init_tts():
    global tts_engine, tts_ready
    with _tts_lock:
        if tts_ready:
            return
    def _init():
        global tts_engine, tts_ready
        try:
            tts_engine = TextToSpeech(activity, None)
            time.sleep(0.5)
            tts_engine.setLanguage(Locale("es"))
            with _tts_lock:
                tts_ready = True
        except Exception as e:
            print(f"[MINKA] Error init TTS: {e}")
    threading.Thread(target=_init, daemon=True).start()


def hablar(texto):
    init_tts()
    for _ in range(40):
        with _tts_lock:
            if tts_ready:
                break
        time.sleep(0.5)
    if tts_engine:
        try:
            tts_engine.speak(str(texto), TextToSpeech.QUEUE_FLUSH, None, "minka_tts")
        except Exception as e:
            print(f"[MINKA] Error TTS: {e}")


# ── Speech-to-Text ─────────────────────────────────────────────────────

grabando = False
_recognizer = None


class _RecognitionListenerImpl(RecognitionListener):
    """Implementacion del RecognitionListener para pyjnius"""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._done = False

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
        if not self._done:
            self._done = True
            print(f"[MINKA] SpeechRecognizer error: {error}")
            self._callback(None)

    def onResults(self, results):
        if not self._done:
            self._done = True
            try:
                matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                if matches and matches.size() > 0:
                    self._callback(matches.get(0))
                else:
                    self._callback(None)
            except Exception as e:
                print(f"[MINKA] Error onResults: {e}")
                self._callback(None)

    def onPartialResults(self, partialResults):
        pass

    def onEvent(self, eventType, params):
        pass


def iniciar_grabacion(callback_resultado):
    """Inicia el reconocimiento de voz nativo de Android"""
    global grabando, _recognizer
    grabando = True

    try:
        _recognizer = SpeechRecognizer.createSpeechRecognizer(activity)
        listener = _RecognitionListenerImpl(callback_resultado)
        _recognizer.setRecognitionListener(listener)

        intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(
            RecognizerIntent.EXTRA_LANGUAGE_MODEL,
            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
        )
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es")
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es")
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)

        _recognizer.startListening(intent)
    except Exception as e:
        print(f"[MINKA] Error starting recognition: {e}\n{traceback.format_exc()}")
        grabando = False
        callback_resultado(None)


def detener_grabacion():
    global grabando, _recognizer
    grabando = False
    if _recognizer:
        try:
            _recognizer.stopListening()
        except Exception:
            pass
        _recognizer = None
