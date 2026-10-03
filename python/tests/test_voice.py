"""Voice: providers against local copies of the OpenAI and ElevenLabs APIs (their documented shapes), the system
voice for real where the machine has one, detection, and the chain."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kinloom import voice
from kinloom.voice import (ElevenLabsVoice, OpenAIVoice, ScriptedVoice, SystemVoice, VoiceChain, audio_format,
                           detect_voice, tone, wav_from_pcm, wav_seconds)


class FakeAPI:
    """A local server answering like the documented endpoints and keeping every request."""

    def __init__(self, status=200):
        self.requests, self.status = [], status
        api = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self, code, body, kind):
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                api.requests.append(("GET", self.path, dict(self.headers), b""))
                voices = {"voices": [
                    {"voice_id": "v-old-man", "name": "Grandpa", "labels": {"gender": "male", "age": "old", "accent": "british"},
                     "description": "a raspy, tired old man"},
                    {"voice_id": "v-young-woman", "name": "Lily", "labels": {"gender": "female", "age": "young"},
                     "description": "bright and warm"}]}
                self._answer(200, json.dumps(voices).encode(), "application/json")

            def do_POST(self):
                data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                api.requests.append(("POST", self.path, dict(self.headers), data))
                if api.status != 200:
                    return self._answer(api.status, b'{"error": {"message": "invalid key"}}', "application/json")
                if self.path.endswith("/audio/speech"):
                    return self._answer(200, tone(0.2, 24000), "audio/wav")
                if self.path.startswith("/v1/text-to-speech/"):
                    return self._answer(200, b"\x00\x01" * 2205, "audio/pcm")          # raw PCM, as pcm_22050 is
                if self.path.endswith("/audio/transcriptions") or self.path == "/v1/speech-to-text":
                    return self._answer(200, json.dumps({"text": "bring me three logs"}).encode(), "application/json")
                self._answer(404, b"{}", "application/json")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def api():
    a = FakeAPI()
    yield a
    a.close()


def test_wav_helpers():
    w = wav_from_pcm(b"\x00\x00" * 22050, 22050)
    assert audio_format(w) == "wav" and abs(wav_seconds(w) - 1.0) < 1e-6
    assert audio_format(b"\x1a\x45\xdf\xa3....") == "webm" and audio_format(b"OggS....") == "ogg"
    assert audio_format(b"ID3\x04...") == "mp3" and audio_format(b"hello") == ""
    assert 0.2 < wav_seconds(tone(0.25)) < 0.3


def test_openai_speak_sends_the_documented_request_and_a_stable_voice(api):
    v = OpenAIVoice(api.url + "/v1", "sk-test")
    wav, err = v.speak("Hello there.", {"seed": "MIRA", "describe": "low, tired, warm"})
    assert err is None and audio_format(wav) == "wav"
    method, path, headers, body = api.requests[-1]
    sent = json.loads(body)
    assert path == "/v1/audio/speech" and headers["Authorization"] == "Bearer sk-test"
    assert sent["model"] == "gpt-4o-mini-tts" and sent["response_format"] == "wav" and sent["input"] == "Hello there."
    assert sent["voice"] in voice.OPENAI_VOICES and sent["instructions"] == "low, tired, warm"
    v.speak("Again.", {"seed": "MIRA"})
    assert json.loads(api.requests[-1][3])["voice"] == sent["voice"]          # the same character keeps its voice
    assert "instructions" not in json.loads(api.requests[-1][3])
    OpenAIVoice(api.url + "/v1", "k", speak_model="tts-1").speak("Hi.", {"seed": "X", "describe": "warm"})
    assert "instructions" not in json.loads(api.requests[-1][3])              # tts-1 does not take them
    v.speak("Hi.", {"seed": "X", "id": "cedar"})
    assert json.loads(api.requests[-1][3])["voice"] == "cedar"


def test_openai_listen_sends_multipart_and_reads_the_text(api):
    v = OpenAIVoice(api.url + "/v1", "sk-test")
    text, err = v.listen(tone(0.3), "wav", "French")
    assert (text, err) == ("bring me three logs", None)
    _, path, headers, body = api.requests[-1]
    assert path == "/v1/audio/transcriptions" and headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="model"\r\n\r\ngpt-4o-mini-transcribe' in body and b'name="language"\r\n\r\nfr' in body
    assert b'filename="speech.wav"' in body and b"RIFF" in body


def test_elevenlabs_picks_a_voice_by_its_labels_and_wraps_pcm_in_wav(api):
    v = ElevenLabsVoice("xi-test", base_url=api.url)
    wav, err = v.speak("Aye.", {"seed": "ORRIN", "describe": "an old man, raspy and tired"})
    assert err is None and audio_format(wav) == "wav" and abs(wav_seconds(wav) - 0.1) < 1e-6
    posted = [r for r in api.requests if r[0] == "POST"][-1]
    assert posted[1] == "/v1/text-to-speech/v-old-man?output_format=pcm_22050" and {k.lower(): v for k, v in posted[2].items()}["xi-api-key"] == "xi-test"
    assert json.loads(posted[3]) == {"text": "Aye.", "model_id": "eleven_flash_v2_5"}
    v.speak("Hi!", {"seed": "LILY", "describe": "a bright young woman"})
    assert "/v-young-woman?" in api.requests[-1][1]
    assert len([r for r in api.requests if r[0] == "GET"]) == 1                 # the list is read once
    text, err = v.listen(tone(0.2), "wav")
    assert text == "bring me three logs" and b'name="model_id"\r\n\r\nscribe_v2' in api.requests[-1][3]


def test_a_refused_key_is_an_error_not_an_exception():
    bad = FakeAPI(status=401)
    try:
        wav, err = OpenAIVoice(bad.url + "/v1", "wrong").speak("Hi.", {"seed": "A"})
        assert wav is None and "401" in err and "invalid key" in err
        text, err = ElevenLabsVoice("wrong", base_url=bad.url).listen(tone(0.1), "wav")
        assert text is None and "401" in err
    finally:
        bad.close()
    wav, err = OpenAIVoice("http://127.0.0.1:9/v1", "k").speak("Hi.", {"seed": "A"}, timeout=2)
    assert wav is None and err


def test_the_chain_falls_through_to_the_next_voice(api):
    bad = FakeAPI(status=500)
    try:
        chain = VoiceChain([OpenAIVoice(bad.url + "/v1", "k"), ScriptedVoice()])
        wav, err = chain.speak("Hi.", {"seed": "A"})
        assert err is None and audio_format(wav) == "wav" and chain.last == "scripted"
        text, err = chain.listen(tone(0.1), "wav")
        assert text.startswith("I heard") and chain.last == "scripted"
    finally:
        bad.close()


def test_detection_never_guesses_and_the_system_voice_comes_last():
    assert detect_voice({"KINLOOM_VOICE": "off", "OPENAI_API_KEY": "k"}) is None
    assert isinstance(detect_voice({"KINLOOM_VOICE": "scripted"}), ScriptedVoice)
    assert detect_voice({}, system=False) is None
    v = detect_voice({"OPENAI_API_KEY": "k"}, system=False)
    assert isinstance(v, OpenAIVoice) and v.speak_model == "gpt-4o-mini-tts" and v.listen_model == "gpt-4o-mini-transcribe"
    v = detect_voice({"ELEVENLABS_API_KEY": "x", "OPENAI_API_KEY": "k"}, system=False)
    assert isinstance(v, VoiceChain) and [p.name for p in v.providers] == ["elevenlabs", "openai"]
    v = detect_voice({"KINLOOM_VOICE_BASE_URL": "http://127.0.0.1:8880/v1", "KINLOOM_SPEAK_MODEL": "kokoro"}, system=False)
    assert isinstance(v, OpenAIVoice) and v.name == "custom" and v.can_speak and not v.can_listen
    assert detect_voice({"KINLOOM_VOICE_BASE_URL": "http://x/v1"}, system=False) is None   # no model named: not used
    v = detect_voice({"KINLOOM_VOICE": "system", "OPENAI_API_KEY": "k"})
    assert v is None or isinstance(v, SystemVoice)


def test_languages_and_genders_are_read_from_plain_words():
    assert voice.guess_language("Apporte-moi trois bûches avant la nuit, je suis fatigué.") == "fr"
    assert voice.guess_language("Bring me the wood before night, I am tired.") == "en"
    assert voice.language_code("French") == "fr" and voice.language_code("fr-FR") == "fr" and voice.language_code("?") is None
    assert voice.gender_hint("a widowed blacksmith, she is proud") == "female"
    assert voice.gender_hint("an old king") == "male" and voice.gender_hint("a robot") is None


# ---------------- in the brain ----------------

def _kl(v=None, **kw):
    from kinloom import Kinloom
    return Kinloom(provider=None, memory_path=kw.pop("memory_path", None), voice=v if v is not None else ScriptedVoice(), **kw)


def test_no_voice_by_default_with_a_hand_given_provider_and_no_audio_offline():
    from kinloom import Kinloom
    kl = Kinloom(provider=None, memory_path=None)
    assert kl.brain.voice is None and kl.speak("MIRA", "Hello.") is None and kl.listen(tone(0.1)) == ""
    kl.close()


def test_speak_uses_the_character_voice_soul_and_mood_and_caches(tmp_path):
    v = ScriptedVoice()
    kl = _kl(v, memory_path=str(tmp_path / "m.json"))
    kl.character("MIRA", "a gruff blacksmith", voice="low, tired, warm", language="French")
    a = kl.speak("MIRA", "Bonjour.")
    assert a is not None and audio_format(a.data) == "wav" and a.seconds > 0 and a.path.startswith(str(tmp_path))
    text, spec = v.spoken[-1]
    assert text == "Bonjour." and spec["seed"] == "MIRA" and spec["describe"].startswith("low, tired, warm")
    assert spec["language"] == "French" and spec["id"] is None
    again = kl.speak("MIRA", "Bonjour.")
    assert again.cached and again.data == a.data and len(v.spoken) == 1           # made once
    kl.brain._moods[("default", "MIRA")] = {"word": "furious", "level": 0.9, "t": kl.brain.clock()}
    kl.speak("MIRA", "Bonjour.")
    assert "right now: furious" in v.spoken[-1][1]["describe"]                    # delivery follows the mood
    kl.character("ORRIN", "a keeper", voice={"id": "cedar"})
    kl.speak("ORRIN", "Aye.")
    assert v.spoken[-1][1]["id"] == "cedar"
    kl.speak(None, "Night falls.")
    assert v.spoken[-1][1]["seed"] == "narrator"
    assert kl.brain.stats()["by_kind"]["speak"] == 4
    kl.close()


def test_blocked_text_is_not_spoken_and_failures_are_logged():
    from kinloom import Kinloom
    v = ScriptedVoice(speak_fn=lambda text, voice: None)
    kl = Kinloom(provider=None, memory_path=None, voice=v, content_filter=lambda text: "cursed" not in text)
    assert kl.speak("A", "a cursed word") is None and not v.spoken
    assert kl.speak("A", "Fine words.") is None
    kinds = [e["kind"] for e in kl.brain.journal(20)]
    assert "refused" in kinds and "error" in kinds
    kl.close()


def test_listen_takes_bytes_paths_and_base64(tmp_path):
    v = ScriptedVoice(listen_fn=lambda data, fmt, lang: "take the %s" % fmt)
    kl = _kl(v, language="French")
    w = tone(0.2)
    p = tmp_path / "r.wav"
    p.write_bytes(w)
    import base64
    assert kl.listen(w) == "take the wav" and kl.listen(str(p)) == "take the wav"
    assert kl.listen(base64.b64encode(w).decode()) == "take the wav"
    assert kl.listen("data:audio/wav;base64," + base64.b64encode(w).decode()) == "take the wav"
    assert v.heard[-1] == (len(w), "wav", "French")
    assert kl.listen(b"") == "" and kl.listen(None) == ""
    kl.close()


def test_the_server_and_a_remote_game_speak_and_listen():
    from kinloom import Kinloom
    from kinloom.brain import Brain
    from kinloom.server import make_server
    import base64
    import urllib.request
    brain = Brain(provider=None, memory_path=None, voice=ScriptedVoice(listen_fn=lambda d, f, l: "open the gate"))
    srv = make_server(brain, host="127.0.0.1", port=0, token="admin", public=True, player_token="play")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        def post(verb, body):
            req = urllib.request.Request(url + "/v1/" + verb, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer play"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        post("character", {"name": "GUARD", "personality": "a bored guard", "voice": "gravelly"})
        r = post("speak", {"name": "GUARD", "text": "Halt."})
        assert r["format"] == "wav" and audio_format(base64.b64decode(r["audio"])) == "wav" and r["seconds"] > 0
        assert post("listen", {"audio": base64.b64encode(tone(0.2)).decode()}) == {"text": "open the gate"}
        big = base64.b64encode(b"\x00" * (3 * 1024 * 1024)).decode()                # above the usual 1 MB body
        assert post("listen", {"audio": big}) == {"text": "open the gate"}
        kl = Kinloom(url=url, token="play", voice="auto")
        kl.character("GUARD", "a bored guard", voice="gravelly")
        a = kl.speak("GUARD", "Move along.")
        assert a is not None and audio_format(a.data) == "wav"
        assert kl.listen(tone(0.1)) == "open the gate"
        kl.close()
    finally:
        srv.shutdown()


WINDOWS = sys.platform.startswith("win") and SystemVoice().can_speak


@pytest.mark.skipif(not WINDOWS, reason="the Windows voice is only on Windows")
def test_windows_speaks_and_hears_offline_for_real():
    s = SystemVoice()
    try:
        names = s.voices()
        assert names, "no installed voice"
        wav, err = s.speak("Bonjour, apporte-moi trois bûches avant la nuit.", {"seed": "MIRA", "language": "fr"})
        assert err is None and audio_format(wav) == "wav" and wav_seconds(wav) > 1.0, err
        if s._hears == "fr":                     # the recognizer of the system's language (French on this machine)
            text, err = s.listen(wav, "wav", "fr")
            assert err is None and "bûches" in text, (text, err)
        text, err = s.listen(b"not audio", "webm")
        assert text is None and "WAV" in err
    finally:
        s.close()


def test_the_default_language_forces_neither_the_voice_nor_the_recognizer():
    v = ScriptedVoice(listen_fn=lambda data, fmt, lang: "lang=%s" % lang)
    kl = _kl(v)                                               # the brain's default language is English
    kl.character("MIRA", "a smith")
    kl.speak("MIRA", "Bonjour, la forge est chaude.")
    assert v.spoken[-1][1]["language"] is None                # the voice provider reads the text's own language
    assert kl.listen(tone(0.2)) == "lang=None"                 # not forced to English
    assert kl.listen(tone(0.2), language="fr") == "lang=fr"
    kl.character("JUNO", "a racer", language="French")
    kl.speak("JUNO", "Salut.")
    assert v.spoken[-1][1]["language"] == "French"
    s = SystemVoice(platform="linux")
    s._voices = [("Hortense", "fr", "female"), ("Zira", "en", "female")]
    assert s.pick({"seed": "A"}, "Apporte-moi trois bûches avant la nuit.")[0] == "Hortense"
    assert s.pick({"seed": "A"}, "Bring me three logs before the night.")[0] == "Zira"
    kl.close()
