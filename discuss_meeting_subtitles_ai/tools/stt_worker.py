# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies (<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions (<https://www.cybrosys.com>)
#
#    This program is free software: you can modify it under the terms of the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful, but
#    WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

"""Standalone speech-to-text worker, shared by every Odoo process on the machine.

Runs as its own process (started by ``stt_client``), so the heavy models live outside Odoo's
memory limits and a crash here can never take Odoo down. It must not import Odoo.

One worker serves all Odoo workers over a Unix socket, so each model is loaded once and only
one transcription uses the CPU at a time, with final captions served before partial ones.

Protocol, one request per connection:
  hello   : the worker sends one JSON line {"pid": int, "loaded": [[engine, model], ...]}
  request : one JSON line {"engine", "language", "model", "keywords", "prompt", "beam_size",
            "main_language", "partial", "lock_timeout", "size"}, then ``size`` raw bytes
  response: one JSON line {"text": str, "language": str|None, "language_probability": float,
            "queue_seconds": float, "stt_seconds": float}, or {"error": str} ("busy" when the
            request waited ``lock_timeout`` seconds without its turn)
"""
import contextlib
import io
import json
import logging
import os
import re
import resource
import select
import signal
import socket
import sys
import tempfile
import threading
import time
import wave

IDLE_EXIT_SECONDS = 900
WHISTLE_LANGUAGES = {"en", "de", "fr", "es", "it", "nl", "pl"}

# Segment quality limits (Whisper's own defaults): beyond these the decode is usually invented text.
MAX_NO_SPEECH_PROB = 0.6
MIN_AVG_LOGPROB = -1.0
MAX_COMPRESSION_RATIO = 2.4
# Whisper's typical output on breathing, typing or silence, compared without case or punctuation.
HALLUCINATIONS = {
    "you", "thank you", "thank you very much", "thanks", "thanks for watching",
    "thank you for watching", "thanks for watching and see you next time", "please subscribe",
    "subscribe to my channel", "like and subscribe", "subtitles by the amaraorg community",
    "subtitles by", "transcribed by", "music", "hmm",
    # the same stock phrases in the other languages the models fall back to on unclear audio
    "vielen dank", "danke", "danke schön", "danke fürs zuschauen", "untertitel der amaraorg community",
    "untertitel im auftrag des zdf", "merci", "merci beaucoup", "merci davoir regardé",
    "soustitres réalisés par la communauté damaraorg", "gracias",
    "muchas gracias", "gracias por ver", "subtítulos realizados por la comunidad de amaraorg",
    "grazie", "grazie mille", "grazie per la visione", "dank je wel", "bedankt voor het kijken",
    "dziękuję", "dziękuję bardzo", "obrigado", "obrigada", "продолжение следует",
    "спасибо", "спасибо за просмотр", "ご視聴ありがとうございました", "谢谢观看", "謝謝觀看",
}
# Auto-detection on a short clip is unreliable: below this confidence the meeting's main
# language is assumed instead (accented English is otherwise often taken for another language).
MIN_AUTO_LANGUAGE_PROBABILITY = 0.7
# A known phrase Whisper hears this confidently was really said ("Thank you." at the end of a
# meeting): on noise and breathing it never got close (real ones: logprob >= -0.35, no-speech
# <= 0.08). Whistle's confidence can't tell them apart, so its known phrases always go.
CONFIDENT_LOGPROB = -0.5
CONFIDENT_NO_SPEECH = 0.2
NON_SPEECH_TAG = re.compile(r"\[[^\]]*\]|\([^)]*\)|[♪♫]+")

_whisper_models = {}
_whistle_loaded = False


_logger = logging.getLogger("stt_worker")


def log(msg):
    _logger.info("%s", msg)


def decode_wav(audio_bytes):
    """Mono float32 samples at 16 kHz from a PCM16 WAV, or None for anything else."""
    if audio_bytes[:4] != b"RIFF":
        return None
    import numpy as np
    with wave.open(io.BytesIO(audio_bytes)) as wav:
        if wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            return None
        frames = wav.readframes(wav.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if wav.getnchannels() > 1:
            samples = samples.reshape(-1, wav.getnchannels()).mean(axis=1)
    return samples


def patch_faster_whisper_av():
    """Strip the unsupported ``metadata_errors`` kwarg from ``av.open``."""
    import faster_whisper.audio
    av = getattr(faster_whisper.audio, "av", None)
    if av is not None and hasattr(av, "open"):
        orig_open = av.open

        def safe_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return orig_open(*args, **kwargs)

        av.open = safe_open


def whisper_model(size):
    model = _whisper_models.get(size)
    if model is None:
        patch_faster_whisper_av()
        from faster_whisper import WhisperModel
        log("loading Whisper model %r" % size)
        # every core: ctranslate2 otherwise caps itself at 4 threads
        model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 0)
        _whisper_models[size] = model
    return model


def clean_text(text, keep_known=False):
    """Strip non-speech tags like [Music] and drop known hallucinated phrases, unless
    ``keep_known``: the engine is confident they were really said."""
    text = re.sub(r"\s+", " ", NON_SPEECH_TAG.sub(" ", text)).strip()
    normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if not normalized or (normalized in HALLUCINATIONS and not keep_known):
        return ""
    return text


def is_confident(segment):
    return segment.avg_logprob >= CONFIDENT_LOGPROB and segment.no_speech_prob < CONFIDENT_NO_SPEECH


def is_reliable(segment):
    return (
        segment.text
        and segment.no_speech_prob < MAX_NO_SPEECH_PROB
        and segment.avg_logprob >= MIN_AVG_LOGPROB
        and segment.compression_ratio <= MAX_COMPRESSION_RATIO
    )


def transcribe_whisper(audio, language, size, keywords, prompt=None, beam_size=5, main_language=None,
                       without_timestamps=False):
    lang = language.split("-")[0] if language and language != "auto" else None
    model = whisper_model(size)
    if lang and lang not in model.supported_languages:
        lang = None
    samples = decode_wav(audio)
    main = main_language.split("-")[0] if main_language else None
    assumed = False
    probability = None
    if not lang and samples is not None:
        # Detect once and hand the result to transcribe(): left to itself it would run the
        # encoder again just to detect, and each encoder pass costs seconds on a CPU.
        lang, probability, _all = model.detect_language(samples)
        if probability < MIN_AUTO_LANGUAGE_PROBABILITY and main in model.supported_languages:
            log("unsure language %s(%.2f): assuming %s" % (lang, probability, main))
            lang = main
            assumed = True
    options = dict(
        language=lang, beam_size=beam_size, condition_on_previous_text=False,
        temperature=0.0, vad_filter=True,
        # live clips fit in one 30 s window, so timestamp tokens are pure decoding cost there;
        # long recordings need them to move from one window to the next without cutting words
        without_timestamps=without_timestamps,
    )
    if keywords:
        options["hotwords"] = " ".join(keywords)
    if prompt:
        # the speaker's previous caption: keeps sentences coherent across utterance cuts
        options["initial_prompt"] = prompt
    if samples is not None:
        segments, info = model.transcribe(samples, **options)
        segments = list(segments)
    else:
        # other containers (webm/ogg) need ffmpeg-style decoding from a file
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio)
            path = tmp.name
        try:
            segments, info = model.transcribe(path, **options)
            segments = list(segments)
        finally:
            os.unlink(path)
    # drop segments Whisper itself flags as unreliable (typical hallucinations on noise)
    reliable = [s for s in segments if is_reliable(s)]
    text = clean_text(" ".join(s.text.strip() for s in reliable),
                      keep_known=bool(reliable) and all(is_confident(s) for s in reliable))
    if probability is None:
        probability = info.language_probability
    log("Whisper[%s] lang=%s(%.2f) text=%r" % (size, info.language, probability, text))
    # an assumed language was not detected: the browser locks the speaker to it only once it repeats
    return {"text": text, "language": info.language,
            "language_probability": 0.0 if assumed else probability, "duration": info.duration}


def transcribe_whistle(audio, language, keywords):
    os.environ.setdefault("NEEDLE_TELEMETRY", "0")
    import needle
    lang = language.split("-")[0] if language and language != "auto" else None
    if lang and lang not in WHISTLE_LANGUAGES:
        log("Whistle does not support language %r" % lang)
        return {"text": ""}
    samples = decode_wav(audio)
    if samples is None:
        return {"text": ""}
    # word timestamps bring each word's probability: misheard words on noisy audio score low
    global _whistle_loaded
    res = needle.transcribe(samples, language=lang, keywords=keywords or None, word_timestamps=True)
    _whistle_loaded = True
    text = clean_text(res.get("text") or "")
    confidence = min((w["probability"] for w in res.get("words") or []), default=None) if text else None
    log("Whistle lang=%s confidence=%s text=%r" % (
        res.get("language"), "-" if confidence is None else "%.2f" % confidence, text))
    # no language confidence is reported, so the language is never treated as reliably detected
    return {"text": text, "language": res.get("language"), "language_probability": 0.0, "confidence": confidence}


def handle(header, audio):
    engine = header.get("engine")
    keywords = header.get("keywords") or []
    if engine == "whistle":
        return transcribe_whistle(audio, header.get("language"), keywords)
    if engine == "whisper":
        return transcribe_whisper(
            audio, header.get("language"), header.get("model") or "small", keywords,
            prompt=header.get("prompt"), beam_size=int(header.get("beam_size") or 5),
            main_language=header.get("main_language"), without_timestamps=True,
        )
    raise ValueError("unknown engine %r" % engine)


def read_exact(stream, size):
    data = b""
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return data


def loaded_models():
    """The [engine, model] pairs already in memory: their requests need no loading time."""
    return [["whisper", size] for size in _whisper_models] + ([["whistle", None]] if _whistle_loaded else [])


class Scheduler:
    """One transcription at a time, final captions first, shared by all connections.

    A partial caption (a preview of speech still going on) never takes the engine while a final
    caption waits for it. Each request waits at most its own ``lock_timeout`` for its turn.
    """

    def __init__(self):
        self._cond = threading.Condition()
        self._busy = False
        self._finals_waiting = 0
        self._waiting = 0
        self.last_activity = time.monotonic()

    def acquire(self, timeout, partial=False):
        deadline = time.monotonic() + timeout
        with self._cond:
            self._waiting += 1
            if not partial:
                self._finals_waiting += 1
            try:
                while self._busy or (partial and self._finals_waiting):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._cond.wait(remaining)
                self._busy = True
                return True
            finally:
                self._waiting -= 1
                if not partial:
                    self._finals_waiting -= 1
                    self._cond.notify_all()  # partials blocked only by this final may go now

    def release(self):
        with self._cond:
            self._busy = False
            self.last_activity = time.monotonic()
            self._cond.notify_all()

    def touch(self):
        with self._cond:
            self.last_activity = time.monotonic()

    def idle_seconds(self):
        with self._cond:
            if self._busy or self._waiting:
                return 0.0
            return time.monotonic() - self.last_activity


def serve_connection(conn, scheduler):
    with conn, conn.makefile("rwb") as stream:
        try:
            stream.write(json.dumps({"pid": os.getpid(), "loaded": loaded_models()}).encode() + b"\n")
            stream.flush()
            line = stream.readline()
            if not line:
                return  # the client only wanted the hello (already loaded), or gave up
            header = json.loads(line)
            audio = read_exact(stream, int(header["size"]))
        except (OSError, ValueError, KeyError, EOFError):
            return
        started = time.monotonic()
        if not scheduler.acquire(float(header.get("lock_timeout") or 0), bool(header.get("partial"))):
            reply = {"error": "busy"}
        else:
            queued = time.monotonic() - started
            try:
                reply = handle(header, audio)
            except ImportError as exc:
                reply = {"error": "not_installed: %s" % exc}
            except Exception as exc:  # keep serving after a bad request
                log("request failed: %r" % exc)
                reply = {"error": repr(exc)}
            finally:
                scheduler.release()
            reply = dict(reply, queue_seconds=queued, stt_seconds=time.monotonic() - started - queued)
        with contextlib.suppress(OSError):  # the client gave up waiting
            stream.write(json.dumps(reply).encode() + b"\n")
            stream.flush()


def main():
    sock_path = sys.argv[1]
    # stderr is inherited from Odoo: these lines land in the Odoo log
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    # Odoo's address-space cap is inherited by child processes; the models need far more.
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    if soft != hard:
        resource.setrlimit(resource.RLIMIT_AS, (hard, hard))
    # Nothing is read from stdout: anything libraries print there goes to the log (stderr).
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    umask = os.umask(0o177)  # the socket is for the Odoo user only
    try:
        server.bind(sock_path)
    finally:
        os.umask(umask)
    bound = os.stat(sock_path).st_ino
    server.listen(32)
    scheduler = Scheduler()
    # It outlives Odoo restarts (the models stay loaded), so after a module update it hands over
    # to a fresh worker running the new code, between two requests.
    code_mtime = os.stat(__file__).st_mtime
    signal.signal(signal.SIGTERM, lambda *_args: sys.exit(0))  # stopped: still remove the socket
    log("ready (pid %d) on %s" % (os.getpid(), sock_path))
    try:
        while True:
            if scheduler.idle_seconds() and os.stat(__file__).st_mtime != code_mtime:
                log("code changed, exiting for a fresh worker")
                return
            if not select.select([server], [], [], 30)[0]:
                if scheduler.idle_seconds() >= IDLE_EXIT_SECONDS:
                    log("idle, exiting to free memory")
                    return
                continue
            conn, _addr = server.accept()
            scheduler.touch()  # a request on its way is not idleness
            threading.Thread(target=serve_connection, args=(conn, scheduler), daemon=True).start()
    finally:
        # Unlink before closing: from then on clients start a fresh worker instead of
        # connecting to this one. A worker started meanwhile owns the path: leave it.
        with contextlib.suppress(OSError):
            if os.stat(sock_path).st_ino == bound:
                os.unlink(sock_path)
        server.close()


if __name__ == "__main__":
    main()
