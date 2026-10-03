"""Voice, standard library only: characters speak (text -> WAV) and players are heard (audio -> text).

Providers are found from the environment like text models, never with a guessed model name:
ELEVENLABS_API_KEY, OPENAI_API_KEY, or any OpenAI-compatible voice server (KINLOOM_VOICE_BASE_URL with
KINLOOM_SPEAK_MODEL / KINLOOM_LISTEN_MODEL). The operating system's own voice is always the last one (Windows
System.Speech, macOS `say`, Linux espeak-ng / espeak): with no key and no network, characters still speak, and on
Windows the player is still heard (in the system's language). KINLOOM_VOICE=off|system forces it.

Every provider answers WAV (the one format every engine plays) and never raises: speak() -> (bytes or None, error),
listen() -> (text or None, error)."""
import atexit
import base64
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import wave

from .providers import _Http

# From the API references, read on 2026-09-30 (not called live: no key was available).
OPENAI_URL = "https://api.openai.com/v1"
OPENAI_SPEAK_MODEL = "gpt-4o-mini-tts"
OPENAI_LISTEN_MODEL = "gpt-4o-mini-transcribe"
OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse",
                 "marin", "cedar"]
ELEVEN_URL = "https://api.elevenlabs.io"
ELEVEN_SPEAK_MODEL = "eleven_flash_v2_5"       # the docs' fast multilingual model
ELEVEN_LISTEN_MODEL = "scribe_v2"
ELEVEN_VOICE = "JBFqnCBsd6RMkjVDRZzb"          # the voice id of the docs' own example
ELEVEN_RATE = 22050                            # pcm_22050: WAV at 44.1 kHz needs a paid tier, so the header is ours
MAX_TEXT = 4000                                # characters spoken at once (OpenAI takes 4096)
MAX_AUDIO = 25 * 1024 * 1024                   # bytes heard at once


# ---------------- audio ----------------

def wav_from_pcm(pcm, rate=22050, channels=1, width=2):
    """16-bit little-endian PCM -> a WAV file's bytes."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def wav_seconds(data):
    """Length of a WAV in seconds (0.0 when it is not one we can read)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError, struct.error):
        return _riff_seconds(data)


def _riff_seconds(data):
    """Some writers (OpenAI streams, SAPI) leave sizes the wave module refuses: read the fmt and data chunks by hand."""
    if not (isinstance(data, (bytes, bytearray)) and data[:4] == b"RIFF" and data[8:12] == b"WAVE"):
        return 0.0
    rate = block = 0
    i = 12
    while i + 8 <= len(data):
        cid, size = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        if cid == b"fmt " and i + 20 <= len(data):
            rate, block = struct.unpack("<I", data[i + 12:i + 16])[0], struct.unpack("<H", data[i + 20:i + 22])[0]
        if cid == b"data":
            n = min(size, len(data) - i - 8) if size not in (0, 0xFFFFFFFF) else len(data) - i - 8
            return n / float(rate * block) if rate and block else 0.0
        i += 8 + size + (size & 1)
        if size in (0xFFFFFFFF,):
            break
    return 0.0


def audio_format(data):
    """'wav', 'webm', 'ogg', 'mp3', 'flac', 'm4a' from the first bytes, or '' when unknown."""
    head = bytes(data[:16]) if data else b""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    if head[4:8] == b"ftyp":
        return "m4a"
    return ""


class Audio:
    """A spoken line: data (WAV bytes), path (the cached file), text, who, seconds; b64 for JSON."""
    format = "wav"

    def __init__(self, data, path, text, who, cached=False):
        self.data, self.path, self.text, self.who, self.cached = data, path, text, who, cached
        self.seconds = wav_seconds(data)

    @property
    def b64(self):
        return base64.b64encode(self.data).decode("ascii")

    def __repr__(self):
        return "Audio(%r, %.1f s%s)" % (self.text[:40], self.seconds, ", cached" if self.cached else "")


def audio_bytes(audio):
    """A recording as bytes, from bytes, a file path, a data: URL or base64 text (None when it is none of them)."""
    if audio is None:
        return None
    if isinstance(audio, Audio):
        return audio.data
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    if isinstance(audio, str):
        text = audio.strip()
        if text.startswith("data:") and "," in text:
            text = text.split(",", 1)[1]
        if len(text) < 1024 and os.path.isfile(text):
            with open(text, "rb") as f:
                return f.read(MAX_AUDIO + 1)
        try:
            return base64.b64decode(text, validate=True) if text else None
        except ValueError:
            return None
    return None


def play(path, wait=True):
    """Plays a WAV file with the operating system's own player (the terminal tools: `kinloom speak`, `kinloom talk
    --voice`). Games play audio with their engine. True when a player was found."""
    path = os.path.abspath(path)
    if sys.platform.startswith("win"):
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            return False
        cmd = [exe, "-NoProfile", "-NonInteractive", "-Command",
               "(New-Object Media.SoundPlayer $env:KINLOOM_PLAY).PlaySync()"]
        env = dict(os.environ, KINLOOM_PLAY=path)
    else:
        found = next((p for p in ("afplay", "paplay", "aplay", "play") if shutil.which(p)), None)
        if not found:
            return False
        cmd, env = [found, path], None
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if wait:
            proc.wait(timeout=120)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def prune(folder, keep=3000):
    """The voice cache keeps its newest `keep` lines (moods and lines vary: it would grow without end)."""
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".wav")]
    except OSError:
        return 0
    if len(files) <= keep:
        return 0
    files.sort(key=lambda f: os.path.getmtime(f))
    gone = 0
    for f in files[: len(files) - int(keep * 0.8)]:
        try:
            os.remove(f)
            gone += 1
        except OSError:
            pass
    return gone


def tone(seconds=0.25, rate=16000, hz=440.0):
    """A short sine WAV (scripted voices and tests)."""
    import math
    n = int(seconds * rate)
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(n))
    return wav_from_pcm(pcm, rate)


# ---------------- choosing a voice ----------------

_FEMALE = {"woman", "female", "girl", "she", "her", "lady", "mother", "grandmother", "queen", "witch", "sister", "wife",
           "daughter", "princess", "aunt", "widow", "widowed", "femme", "fille", "reine", "mere", "mère", "soeur", "sœur",
           "grand-mère", "sorcière", "veuve", "elle", "mujer", "chica", "frau"}
_MALE = {"man", "male", "boy", "he", "his", "lord", "father", "grandfather", "king", "brother", "husband", "son", "prince",
         "uncle", "sir", "homme", "garçon", "roi", "pere", "père", "frère", "grand-père", "il", "hombre", "mann"}
_STOP = {
    "fr": {"le", "la", "les", "je", "tu", "vous", "et", "est", "pas", "une", "des", "du", "que", "qui", "pour", "dans", "avec",
           "mais", "nous", "sur", "ce", "cette", "moi", "toi", "suis", "ai", "bien", "oui", "non", "au", "aux"},
    "en": {"the", "a", "an", "and", "is", "are", "you", "i", "not", "to", "of", "in", "that", "it", "with", "for", "my",
           "your", "this", "what", "yes", "no", "me", "we", "be", "was", "have", "do"},
    "es": {"el", "la", "los", "las", "y", "es", "no", "que", "un", "una", "de", "en", "por", "con", "para", "yo", "tu",
           "usted", "pero", "muy", "sí"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "ich", "du", "sie", "ein", "eine", "zu", "mit", "für", "auf",
           "den", "dem", "ja", "nein", "aber"},
    "it": {"il", "lo", "la", "gli", "le", "e", "è", "non", "che", "un", "una", "di", "in", "per", "con", "io", "tu", "ma",
           "sì"},
}
_LANGS = {"french": "fr", "français": "fr", "francais": "fr", "english": "en", "anglais": "en", "spanish": "es",
          "español": "es", "german": "de", "deutsch": "de", "italian": "it", "italiano": "it"}


def language_code(language):
    """'fr', 'en'... from 'French', 'fr-FR', 'fr' (None when unknown)."""
    if not language:
        return None
    low = str(language).strip().lower()
    if low in _LANGS:
        return _LANGS[low]
    m = re.match(r"^([a-z]{2})(?:[-_][a-z]{2})?$", low)
    return m.group(1) if m else None


def guess_language(text):
    """The most likely of fr/en/es/de/it for a short text (None when nothing points to one)."""
    words = re.findall(r"[a-zà-ÿœ']+", (text or "").lower())
    scores = {k: sum(1 for w in words if w in v) for k, v in _STOP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def gender_hint(describe):
    words = set(re.findall(r"[a-zà-ÿœ-]+", (describe or "").lower()))
    f, m = len(words & _FEMALE), len(words & _MALE)
    return "female" if f > m else "male" if m > f else None


def stable_pick(options, seed):
    """The same option for the same seed, spread across seeds (voices per character that stay the same)."""
    if not options:
        return None
    h = int(hashlib.sha1(str(seed or "").encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def _words(text):
    return set(re.findall(r"[a-zà-ÿ]{3,}", (text or "").lower()))


# ---------------- providers ----------------

class VoiceProvider:
    """speak(text, voice, timeout) -> (wav bytes | None, error); listen(data, fmt, language, timeout) -> (text | None,
    error). voice: {"seed": name, "describe": how they sound, "id": exact voice id or None, "language": "fr"...}."""
    name = "voice"
    can_speak = True
    can_listen = True

    def speak(self, text, voice, timeout=15.0):
        return None, "not supported"

    def listen(self, data, fmt, language=None, timeout=20.0):
        return None, "not supported"

    def describe(self):
        return self.name

    def local(self):
        return False

    def close(self):
        pass


def _multipart(fields, file_field, data, filename, mime):
    boundary = "----kinloom" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode("utf-8"))
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                  % (boundary, file_field, filename, mime)).encode("utf-8") + bytes(data) + b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(parts), "multipart/form-data; boundary=%s" % boundary


_MIME = {"wav": "audio/wav", "webm": "audio/webm", "ogg": "audio/ogg", "mp3": "audio/mpeg", "flac": "audio/flac",
         "m4a": "audio/mp4"}


def _error(status, text):
    if status is None:
        return text or "no answer"
    try:
        detail = json.loads(text if isinstance(text, str) else text.decode("utf-8", "replace"))
        detail = detail.get("error") or detail.get("detail") or detail
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail)[:200]
    except (ValueError, AttributeError):
        detail = (text if isinstance(text, str) else text.decode("utf-8", "replace"))[:200]
    return "HTTP %s: %s" % (status, str(detail)[:200])


class OpenAIVoice(VoiceProvider):
    """OpenAI's /audio/speech and /audio/transcriptions, or any server that copies them."""

    def __init__(self, base_url, key, speak_model=OPENAI_SPEAK_MODEL, listen_model=OPENAI_LISTEN_MODEL, name="openai",
                 voices=None):
        self.base_url, self.key, self.name = base_url.rstrip("/"), key, name
        self.speak_model, self.listen_model = speak_model, listen_model
        self.voices = list(voices or OPENAI_VOICES)
        self.can_speak, self.can_listen = bool(speak_model), bool(listen_model)

    def describe(self):
        return "%s (%s / %s)" % (self.name, self.speak_model or "-", self.listen_model or "-")

    def _headers(self):
        return {"Authorization": "Bearer %s" % self.key} if self.key else {}

    def speak(self, text, voice, timeout=15.0):
        if not self.speak_model:
            return None, "no speak model"
        body = {"model": self.speak_model, "input": text[:MAX_TEXT], "response_format": "wav",
                "voice": voice.get("id") or stable_pick(self.voices, voice.get("seed"))}
        if voice.get("describe") and not self.speak_model.startswith("tts-1"):
            body["instructions"] = voice["describe"][:1000]
        status, out = _Http.post(self.base_url + "/audio/speech", self._headers(), body, time.monotonic() + timeout, raw=True)
        if status != 200 or not isinstance(out, bytes):
            return None, _error(status, out)
        return (out, None) if audio_format(out) == "wav" else (None, "the answer is not WAV audio")

    def listen(self, data, fmt, language=None, timeout=20.0):
        if not self.listen_model:
            return None, "no listen model"
        fields = {"model": self.listen_model, "language": language_code(language), "response_format": "json"}
        body, kind = _multipart(fields, "file", data, "speech." + (fmt or "wav"), _MIME.get(fmt, "application/octet-stream"))
        headers = dict(self._headers(), **{"Content-Type": kind})
        status, out = _Http.post(self.base_url + "/audio/transcriptions", headers, body, time.monotonic() + timeout)
        if status != 200:
            return None, _error(status, out)
        try:
            return str(json.loads(out).get("text") or ""), None
        except (ValueError, AttributeError):
            return None, "unreadable answer"


class ElevenLabsVoice(VoiceProvider):
    """ElevenLabs text to speech (voices chosen from the account's list by their labels) and speech to text."""

    def __init__(self, key, speak_model=ELEVEN_SPEAK_MODEL, listen_model=ELEVEN_LISTEN_MODEL, base_url=ELEVEN_URL,
                 default_voice=ELEVEN_VOICE):
        self.key, self.base_url, self.name = key, base_url.rstrip("/"), "elevenlabs"
        self.speak_model, self.listen_model, self.default_voice = speak_model, listen_model, default_voice
        self._voices, self._lock = None, threading.Lock()

    def describe(self):
        return "elevenlabs (%s / %s)" % (self.speak_model, self.listen_model)

    def voices(self, timeout=8.0):
        """[(voice_id, words describing it)] of the account, read once."""
        with self._lock:
            if self._voices is not None:
                return self._voices
        found = []
        try:
            req = urllib.request.Request(self.base_url + "/v1/voices", headers={"xi-api-key": self.key})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read(4_000_000).decode("utf-8"))
            for v in data.get("voices") or []:
                labels = " ".join(str(x) for x in (v.get("labels") or {}).values())
                found.append((str(v.get("voice_id")), _words("%s %s %s" % (v.get("name"), labels, v.get("description") or ""))))
        except Exception:  # listing voices is a nicety: the default voice still speaks
            found = []
        with self._lock:
            self._voices = [v for v in found if v[0] and v[0] != "None"]
            return self._voices

    def pick(self, voice):
        if voice.get("id"):
            return voice["id"]
        options = self.voices()
        if not options:
            return self.default_voice
        want = _words(voice.get("describe"))
        g = gender_hint(voice.get("describe"))
        if g:
            want.add(g)
        best = max(len(want & words) for _, words in options)
        return stable_pick([vid for vid, words in options if len(want & words) == best], voice.get("seed"))

    def speak(self, text, voice, timeout=15.0):
        url = "%s/v1/text-to-speech/%s?output_format=pcm_%d" % (self.base_url, urllib.parse.quote(self.pick(voice)), ELEVEN_RATE)
        body = {"text": text[:MAX_TEXT], "model_id": self.speak_model}
        status, out = _Http.post(url, {"xi-api-key": self.key}, body, time.monotonic() + timeout, raw=True)
        if status != 200 or not isinstance(out, bytes):
            return None, _error(status, out)
        if audio_format(out) == "wav":
            return out, None
        return wav_from_pcm(out[: len(out) - len(out) % 2], ELEVEN_RATE), None

    def listen(self, data, fmt, language=None, timeout=20.0):
        fields = {"model_id": self.listen_model, "language_code": language_code(language), "tag_audio_events": "false"}
        body, kind = _multipart(fields, "file", data, "speech." + (fmt or "wav"), _MIME.get(fmt, "application/octet-stream"))
        status, out = _Http.post(self.base_url + "/v1/speech-to-text", {"xi-api-key": self.key, "Content-Type": kind}, body,
                                 time.monotonic() + timeout)
        if status != 200:
            return None, _error(status, out)
        try:
            return str(json.loads(out).get("text") or ""), None
        except (ValueError, AttributeError):
            return None, "unreadable answer"


# ---------------- the operating system's voice ----------------

_PS_WORKER = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
[Console]::OutputEncoding = [Text.Encoding]::UTF8
function Say([string]$line) { [Console]::Out.WriteLine($line); [Console]::Out.Flush() }
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($line -eq $null) { break }
  $p = $line.Split("`t")
  try {
    if ($p[0] -eq 'voices') {
      $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
      $all = $s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name + '|' + $_.VoiceInfo.Gender }
      $s.Dispose()
      $r = ''
      try { $e = New-Object System.Speech.Recognition.SpeechRecognitionEngine; $r = $e.RecognizerInfo.Culture.Name; $e.Dispose() } catch {}
      Say ('ok' + "`t" + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($all -join "`n") + "`n#" + $r)))
    } elseif ($p[0] -eq 'speak') {
      $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
      if ($p[1]) { $s.SelectVoice($p[1]) }
      $s.SetOutputToWaveFile($p[2])
      $s.Speak([IO.File]::ReadAllText($p[3], [Text.Encoding]::UTF8))
      $s.Dispose()
      Say 'ok'
    } elseif ($p[0] -eq 'listen') {
      $e = New-Object System.Speech.Recognition.SpeechRecognitionEngine
      $e.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
      $e.SetInputToWaveFile($p[1])
      $out = @()
      for ($i = 0; $i -lt 60; $i++) { try { $res = $e.Recognize() } catch { $res = $null }; if ($res -eq $null) { break }; $out += $res.Text }
      $e.Dispose()
      Say ('ok' + "`t" + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($out -join ' '))))
    } else { Say 'err unknown' }
  } catch { Say ('err ' + ($_.Exception.Message -replace "`r|`n", ' ')) }
}
"""


class SystemVoice(VoiceProvider):
    """The operating system's voice, offline and free: Windows (speaks and hears, through one PowerShell kept open),
    macOS `say`, Linux espeak-ng / espeak (speak only)."""
    name = "system"

    def __init__(self, platform=None):
        self.platform = platform or sys.platform
        self._proc, self._lock, self._voices, self._hears = None, threading.Lock(), None, None
        self._espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        self.can_speak = self.available()
        self.can_listen = self.platform.startswith("win")
        self._dir = tempfile.mkdtemp(prefix="kinloom-voice-")
        atexit.register(self.close)

    def available(self):
        if self.platform.startswith("win"):
            return bool(shutil.which("powershell") or shutil.which("pwsh"))
        if self.platform == "darwin":
            return bool(shutil.which("say"))
        return bool(self._espeak)

    def local(self):
        return True

    def describe(self):
        return "system (%s)" % {"win32": "Windows", "darwin": "macOS"}.get(self.platform, self._espeak or "none")

    # Windows: one PowerShell worker, started on first use (starting one per line would add about a second each)
    def _ask(self, line, timeout):
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                exe = shutil.which("powershell") or shutil.which("pwsh")
                encoded = base64.b64encode(_PS_WORKER.encode("utf-16-le")).decode("ascii")
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._proc = subprocess.Popen([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                               "-EncodedCommand", encoded], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL, creationflags=flags)
            proc = self._proc
            box = {}

            def read():
                box["line"] = proc.stdout.readline()
            try:
                proc.stdin.write((line + "\n").encode("utf-8"))
                proc.stdin.flush()
            except OSError as e:
                self._kill()
                return None, "system voice: %s" % e
            t = threading.Thread(target=read, daemon=True)
            t.start()
            t.join(timeout)
            if "line" not in box:
                self._kill()
                return None, "system voice: timed out"
            answer = box["line"].decode("utf-8", "replace").strip()
            if not answer:
                self._kill()
                return None, "system voice: stopped"
            if answer.startswith("err"):
                return None, "system voice: " + answer[4:][:200]
            parts = answer.split("\t", 1)
            return (base64.b64decode(parts[1]).decode("utf-8", "replace") if len(parts) > 1 else ""), None

    def _kill(self):
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass
        self._proc = None

    def close(self):
        with self._lock:
            self._kill()
        shutil.rmtree(getattr(self, "_dir", ""), ignore_errors=True)

    def voices(self):
        """[(name, language code, 'female'|'male'|None)] installed."""
        if self._voices is not None:
            return self._voices
        found = []
        if self.platform.startswith("win"):
            text, err = self._ask("voices", 30)
            if text:
                body, _, hears = text.rpartition("\n#")
                self._hears = language_code(hears.strip()) if hears.strip() else None
                for row in body.splitlines():
                    bits = row.split("|")
                    if len(bits) == 3 and bits[0]:
                        found.append((bits[0], language_code(bits[1]), bits[2].lower() if bits[2] in ("Female", "Male") else None))
        elif self.platform == "darwin":
            try:
                out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
                for row in out.splitlines():
                    m = re.match(r"^(.+?)\s{2,}([a-z]{2})[_-][A-Za-z]{2}\s+#", row)
                    if m:
                        found.append((m.group(1).strip(), m.group(2), None))
            except (OSError, subprocess.SubprocessError):
                pass
        self._voices = found
        return found

    def pick(self, voice, text):
        lang = language_code(voice.get("language")) or guess_language(text) or "en"
        options = self.voices()
        if voice.get("id") and any(v[0] == voice["id"] for v in options):
            return voice["id"], lang
        same = [v for v in options if lang and v[1] == lang] or options
        g = gender_hint(voice.get("describe"))
        fit = [v for v in same if g and v[2] == g] or same
        chosen = stable_pick([v[0] for v in fit], voice.get("seed"))
        return chosen, lang

    def speak(self, text, voice, timeout=15.0):
        if not self.can_speak:
            return None, "no system voice"
        name, lang = self.pick(voice, text)
        src = os.path.join(self._dir, uuid.uuid4().hex + ".txt")
        out = os.path.join(self._dir, uuid.uuid4().hex + ".wav")
        with open(src, "w", encoding="utf-8") as f:
            f.write(text[:MAX_TEXT])
        try:
            if self.platform.startswith("win"):
                _, err = self._ask("speak\t%s\t%s\t%s" % (name or "", out, src), timeout)
            elif self.platform == "darwin":
                args = ["say"] + (["-v", name] if name else []) + ["-o", out, "--file-format=WAVE", "--data-format=LEI16@22050", "-f", src]
                r = subprocess.run(args, capture_output=True, timeout=timeout)
                err = None if r.returncode == 0 else "say failed"
            else:
                args = [self._espeak] + (["-v", lang] if lang else []) + ["-w", out, "-f", src]
                r = subprocess.run(args, capture_output=True, timeout=timeout)
                err = None if r.returncode == 0 else "espeak failed"
            if err:
                return None, err
            with open(out, "rb") as f:
                data = f.read()
            return (data, None) if audio_format(data) == "wav" else (None, "system voice: no audio")
        except (OSError, subprocess.SubprocessError) as e:
            return None, "system voice: %s" % e
        finally:
            for p in (src, out):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def listen(self, data, fmt, language=None, timeout=20.0):
        if not self.can_listen:
            return None, "no system recognition here"
        if fmt != "wav":
            return None, "system recognition needs WAV"
        self.voices()
        want = language_code(language)
        if want and self._hears and want != self._hears:
            return None, "system recognition only hears %s" % self._hears
        path = os.path.join(self._dir, uuid.uuid4().hex + ".wav")
        with open(path, "wb") as f:
            f.write(data)
        try:
            text, err = self._ask("listen\t%s" % path, timeout)
            return (text, None) if err is None else (None, err)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


class ScriptedVoice(VoiceProvider):
    """For tests and `KINLOOM_VOICE=scripted`: a short tone for every line, a fixed or computed text for every recording."""
    name = "scripted"

    def __init__(self, speak_fn=None, listen_fn=None):
        self.speak_fn, self.listen_fn = speak_fn, listen_fn
        self.spoken, self.heard = [], []

    def local(self):
        return True

    def speak(self, text, voice, timeout=15.0):
        self.spoken.append((text, dict(voice)))
        out = self.speak_fn(text, voice) if self.speak_fn else tone(0.1 + 0.02 * min(len(text), 100))
        return (out, None) if out else (None, "scripted: no audio")

    def listen(self, data, fmt, language=None, timeout=20.0):
        self.heard.append((len(data), fmt, language))
        text = self.listen_fn(data, fmt, language) if self.listen_fn else "I heard %d bytes of %s" % (len(data), fmt or "audio")
        return (text, None) if text is not None else (None, "scripted: nothing heard")


class VoiceChain(VoiceProvider):
    """Providers in order: each call goes to the first one able to do it that answers (the system voice last)."""

    def __init__(self, providers):
        self.providers = [p for p in providers if p is not None]
        self.name = "+".join(p.name for p in self.providers)
        self.can_speak = any(p.can_speak for p in self.providers)
        self.can_listen = any(p.can_listen for p in self.providers)
        self.last = None

    def describe(self):
        return " then ".join(p.describe() for p in self.providers)

    def local(self):
        return all(p.local() for p in self.providers)

    def _each(self, kind, call):
        errors = []
        for p in self.providers:
            if not getattr(p, "can_" + kind):
                continue
            out, err = call(p)
            if out is not None:
                self.last = p.name
                return out, None
            errors.append("%s: %s" % (p.name, err))
        return None, "; ".join(errors) or "no voice"

    def speak(self, text, voice, timeout=15.0):
        return self._each("speak", lambda p: p.speak(text, voice, timeout))

    def close(self):
        for p in self.providers:
            p.close()

    def listen(self, data, fmt, language=None, timeout=20.0):
        return self._each("listen", lambda p: p.listen(data, fmt, language, timeout))


def detect_voice(env=None, system=True):
    """The voice providers from the environment, best first, the system voice last; None when there are none."""
    env = os.environ if env is None else env
    force = (env.get("KINLOOM_VOICE") or "").strip().lower()
    if force in ("off", "none", "0", "false", "no"):
        return None
    if force == "scripted":
        return ScriptedVoice()
    chain = []
    if force != "system":
        speak_model, listen_model = env.get("KINLOOM_SPEAK_MODEL"), env.get("KINLOOM_LISTEN_MODEL")
        if env.get("KINLOOM_VOICE_BASE_URL") and (speak_model or listen_model):
            chain.append(OpenAIVoice(env["KINLOOM_VOICE_BASE_URL"], env.get("KINLOOM_VOICE_API_KEY") or "", speak_model,
                                     listen_model, name="custom"))
        if env.get("ELEVENLABS_API_KEY"):
            chain.append(ElevenLabsVoice(env["ELEVENLABS_API_KEY"], speak_model or ELEVEN_SPEAK_MODEL,
                                         listen_model or ELEVEN_LISTEN_MODEL))
        if env.get("OPENAI_API_KEY"):
            chain.append(OpenAIVoice(env.get("OPENAI_BASE_URL") or OPENAI_URL, env["OPENAI_API_KEY"],
                                     speak_model or OPENAI_SPEAK_MODEL, listen_model or OPENAI_LISTEN_MODEL))
    if system:
        s = SystemVoice()
        if s.can_speak or s.can_listen:
            chain.append(s)
    if not chain:
        return None
    return chain[0] if len(chain) == 1 else VoiceChain(chain)
