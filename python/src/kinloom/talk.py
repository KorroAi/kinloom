"""Talking in a game loop, for any Python engine: a conversation you poll every frame, never blocking, and a ready
dialogue box for Pygame.

    talk = Talk(kl, "MIRA", speaker="Ana", on_action=lambda tool, args: give(args["item"]))
    talk.open()                   # she speaks first
    talk.send("Nice hammer.")     # returns at once; the reply streams in
    talk.update()                 # every frame: talk.lines, talk.current (the reply being written), talk.mood

    box = PygameTalkBox(kl, "MIRA", speaker="Ana")      # Pygame (or pygame-ce), imported only when used
    if event.type == pygame.KEYDOWN and event.key == pygame.K_t and not box.is_open: box.open()
    if box.handle(event): continue                    # typing, Enter to send, Esc to close
    box.update(); box.draw(screen)                    # every frame

Voice: Talk(..., voice=True) says each sentence aloud as soon as it is written (on_audio(audio) gets them in order,
audio.data is WAV); talk.hear(recording) sends what the player said. PygameTalkBox(voice=True) plays the voice itself
and records while a key is held (Tab by default) where pygame can use the microphone.
"""
import re
import threading

_END = re.compile(r"[.!?\u2026]+[\"'\u201d\u2019)\]]*(?:\s+|$)")


class Talk:
    """One conversation with a character. send() never waits; update() (every frame) brings in what arrived:
    `lines` [(who, text)], `current` (the reply as it is written), `waiting`, `mood`, `gesture`. What the character
    decides while talking goes to on_action(tool, args), validated against its tools."""

    def __init__(self, kl, name, speaker="player", facts=None, on_action=None, on_reply=None, keep=40, voice=False,
                 on_audio=None, language=None):
        self.kl, self.name, self.speaker = kl, name, speaker
        self.voice, self.on_audio, self.language = voice, on_audio, language
        self._spoken = 0             # characters of the reply being written already sent to the voice
        self._speaking = []          # futures of lines being spoken, in the order they must be heard
        self._hearing = None         # the recording being understood
        self.heard = ""              # the last thing the player was heard saying
        self.facts = facts               # a dict, or a function returning the facts of the moment
        self.on_action, self.on_reply = on_action, on_reply
        self.keep = keep
        self.lines = []
        self.current = ""
        self.mood, self.gesture = "", ""
        self._lock = threading.Lock()
        self._future = None
        self._pieces = []
        self._queued = None

    @property
    def waiting(self):
        return self._future is not None

    def open(self, speak_first=True):
        """Starts the conversation; the character speaks first unless speak_first=False."""
        if speak_first and not self.waiting:
            self._start("")

    def send(self, text):
        """The player says text. While the character is still answering, it waits its turn (one message at most;
        False when another one is already waiting)."""
        text = (text or "").strip()
        if not text or self._queued is not None:
            return False
        self.lines.append((self.speaker, text))
        if self.waiting:
            self._queued = text
        else:
            self._start(text)
        return True

    def _start(self, text):
        facts = self.facts() if callable(self.facts) else self.facts
        self.current = ""
        self._spoken = 0
        with self._lock:
            self._pieces = []

        def piece(p):
            with self._lock:
                self._pieces.append(p)
        self._future = self.kl.chat_async(self.name, text, facts, speaker=self.speaker, stream=piece)

    def hear(self, recording):
        """The player spoke (WAV/WebM/OGG/MP3 bytes or a path): what they said is sent as soon as it is understood.
        False when a recording is already being understood."""
        if self._hearing is not None or not recording:
            return False
        self._hearing = self.kl.listen_async(recording, self.language)
        return True

    @property
    def hearing(self):
        return self._hearing is not None

    def _say(self, text):
        text = text.strip()
        if self.voice and text:
            self._speaking.append(self.kl.speak_async(self.name, text))

    def _speak_ready(self, final=None):
        """Sends each finished sentence of what is written so far to the voice; with final, the rest too."""
        if not self.voice:
            return
        if final is not None:
            done = self.current if final.startswith(self.current[:self._spoken]) else ""
            rest = final[self._spoken:] if done or not self._spoken else ""
            self._say(rest)
            self._spoken = 0
            return
        ends = [m.end() for m in _END.finditer(self.current) if m.end() > self._spoken and m.group(0)[-1:].isspace()]
        if ends:
            self._say(self.current[self._spoken:ends[-1]])
            self._spoken = ends[-1]

    def _deliver_audio(self):
        changed = False
        while self._speaking and self._speaking[0].done():
            f = self._speaking.pop(0)
            try:
                audio = f.result()
            except Exception:
                audio = None
            if audio is not None:
                changed = True
                if self.on_audio:
                    try:
                        self.on_audio(audio)
                    except Exception:  # a game callback must never break the conversation
                        pass
        return changed

    def update(self):
        """Call every frame (cheap). Returns True when something changed."""
        changed = False
        with self._lock:
            if self._pieces:
                self.current += "".join(self._pieces)
                self._pieces = []
                changed = True
        self._speak_ready()
        changed = self._deliver_audio() or changed
        h = self._hearing
        if h is not None and h.done():
            self._hearing = None
            try:
                self.heard = h.result() or ""
            except Exception:
                self.heard = ""
            if self.heard:
                self.send(self.heard)
            changed = True
        f = self._future
        if f is not None and f.done():
            self._future = None
            try:
                reply = f.result()
            except Exception:  # never break the game loop over a conversation
                reply = ""
            if reply:
                self._speak_ready(final=reply)
            self.current = ""
            queued, self._queued = self._queued, None
            if reply:
                at = len(self.lines) - (1 if queued is not None else 0)     # before the message that waited
                self.lines.insert(at, (self.name, reply))
                if self.on_reply:
                    self.on_reply(reply)
            del self.lines[:-self.keep]
            try:
                soul = self.kl.soul(self.name, self.speaker) or {}
                self.mood = (soul.get("mood") or {}).get("word") or ""
                self.gesture = soul.get("gesture") or ""
            except Exception:
                pass
            for tool, args in self.kl.act(self.name, think=False) if self.on_action else []:
                self.on_action(tool, args)
            if queued is not None:
                self._start(queued)
            changed = True
        return changed


def _wrap(font, text, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        test = (line + " " + w).strip()
        if font.size(test)[0] <= width or not line:
            line = test
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


class _Microphone:
    """Push-to-talk recording with pygame's own SDL audio capture (pygame 2 / pygame-ce): 16 kHz mono WAV."""
    RATE = 16000

    def __init__(self, pg):
        self.pg, self.device, self.chunks, self.error = pg, None, [], None

    def start(self):
        self.chunks = []
        try:
            from pygame._sdl2 import audio as sdl
            if not self.pg.mixer.get_init():
                self.pg.mixer.init()
            names = sdl.get_audio_device_names(True)
            if not names:
                self.error = "no microphone"
                return False

            def take(device, memory):
                self.chunks.append(bytes(memory))
            self.device = sdl.AudioDevice(devicename=names[0], iscapture=True, frequency=self.RATE,
                                          audioformat=sdl.AUDIO_S16, numchannels=1, chunksize=512, allowed_changes=0,
                                          callback=take)
            self.device.pause(0)
            return True
        except Exception as e:  # no capture in this pygame build or no device: the keyboard still works
            self.error = "microphone unavailable (%s)" % type(e).__name__
            self.device = None
            return False

    def stop(self):
        """The recording as WAV bytes (None when there was none or it is too short to hold a word)."""
        if self.device is None:
            return None
        try:
            self.device.pause(1)
            self.device.close()
        except Exception:
            pass
        self.device = None
        pcm = b"".join(self.chunks)
        if len(pcm) < self.RATE * 2 * 0.3:            # under 0.3 s: a tap, not speech
            return None
        from .voice import wav_from_pcm
        return wav_from_pcm(pcm[: len(pcm) - len(pcm) % 2], self.RATE)


class PygameTalkBox(Talk):
    """A dialogue box for Pygame / pygame-ce: open(), then handle(event) for every event and update() + draw(surface)
    every frame. The player types; Enter sends; Esc closes. Replies appear as they are written. voice=True: replies
    are spoken sentence by sentence, and holding voice_key (Tab) records the player (released: sent)."""

    def __init__(self, kl, name, speaker="player", facts=None, on_action=None, on_reply=None, font=None,
                 colors=None, rows=5, voice=False, voice_key=None, language=None):
        super().__init__(kl, name, speaker, facts, on_action, on_reply, voice=voice, on_audio=self._queue_audio,
                         language=language)
        import pygame                                  # only for Pygame games: the package itself needs nothing
        self.pg = pygame
        self.voice_key = voice_key if voice_key is not None else pygame.K_TAB
        self._sounds, self._channel, self._mic, self.recording = [], None, None, False
        if not pygame.font.get_init():
            pygame.font.init()
        self.font = font or pygame.font.Font(None, 24)
        self.colors = dict({"panel": (15, 17, 23), "border": (60, 70, 95), "name": (255, 196, 120), "me": (150, 175, 255),
                            "text": (230, 232, 239), "hint": (140, 145, 160)}, **(colors or {}))
        self.rows = rows
        self.typed = ""
        self.is_open = False
        self._fresh = False       # just opened: the text of the key that opened it is not typed

    def open(self, speak_first=True):
        self.is_open = True
        self._fresh = True
        self.pg.key.start_text_input()
        super().open(speak_first and not self.lines)

    def close(self):
        self.is_open = False
        self.pg.key.stop_text_input()
        if self._channel is not None:
            self._channel.stop()
        self._sounds = []

    def _queue_audio(self, audio):
        if not self.is_open:                  # closed while a line was being made: it is not played
            return
        try:
            if not self.pg.mixer.get_init():
                self.pg.mixer.init()
            import io
            self._sounds.append(self.pg.mixer.Sound(file=io.BytesIO(audio.data)))
        except Exception:  # no audio device: the text is still there
            pass

    def _play(self):
        if not self._sounds:
            return
        if self._channel is None:
            self._channel = self.pg.mixer.find_channel(True)
        if self._channel is not None and not self._channel.get_busy():
            self._channel.play(self._sounds.pop(0))

    @property
    def speaking(self):
        return bool(self._sounds) or (self._channel is not None and self._channel.get_busy())

    def handle(self, event):
        """True when the box used the event (the game should then ignore it)."""
        pg = self.pg
        if not self.is_open:
            return False
        if event.type == pg.TEXTINPUT:
            if not self._fresh:
                self.typed = (self.typed + event.text)[:200]
            return True
        if self.voice and event.type in (pg.KEYDOWN, pg.KEYUP) and event.key == self.voice_key:
            if event.type == pg.KEYDOWN and not self.recording:
                self._mic = self._mic or _Microphone(pg)
                self.recording = self._mic.start()
            elif event.type == pg.KEYUP and self.recording:
                self.recording = False
                self.hear(self._mic.stop())
            return True
        if event.type == pg.KEYDOWN:
            if event.key == pg.K_ESCAPE:
                self.close()
            elif event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                if self.send(self.typed):
                    self.typed = ""
            elif event.key == pg.K_BACKSPACE:
                self.typed = self.typed[:-1]
            return True
        return event.type == pg.KEYUP

    def update(self):
        self._fresh = False
        changed = super().update()
        self._play()
        return changed

    def draw(self, surface):
        if not self.is_open:
            return
        pg, f, c = self.pg, self.font, self.colors
        w, h = surface.get_size()
        line_h = f.get_linesize()
        box_w = min(w - 32, 760)
        text_w = box_w - 28
        rows = []
        for who, text in self.lines:
            me = who == self.speaker
            for i, part in enumerate(_wrap(f, text, text_w - (0 if me else 10))):
                rows.append((("%s: " % who if i == 0 else "  ") + part, c["me"] if me else c["text"]))
        if self.current or self.waiting:
            for i, part in enumerate(_wrap(f, self.current or "...", text_w) or ["..."]):
                rows.append((("%s: " % self.name if i == 0 else "  ") + part, c["text"]))
        rows = rows[-self.rows:]
        box_h = (len(rows) + 3) * line_h + 20
        x, y = (w - box_w) // 2, h - box_h - 16
        panel = pg.Surface((box_w, box_h), pg.SRCALPHA)
        panel.fill(c["panel"] + (235,))
        surface.blit(panel, (x, y))
        pg.draw.rect(surface, c["border"], (x, y, box_w, box_h), 1, border_radius=8)
        head = self.name + ("  (%s)" % self.mood if self.mood else "")
        surface.blit(f.render(head, True, c["name"]), (x + 14, y + 8))
        yy = y + 8 + line_h + 4
        for text, color in rows:
            surface.blit(f.render(text, True, color), (x + 14, yy))
            yy += line_h
        if self.recording or self.hearing:
            prompt = "(listening...)" if self.recording else "(...)"
        else:
            prompt = "> " + self.typed + ("_" if (pg.time.get_ticks() // 400) % 2 == 0 else " ")
        surface.blit(f.render(prompt, True, c["me"]), (x + 14, y + box_h - line_h - 10))
        hint = "Enter: send   Esc: close"
        if self.voice:
            mic = self._mic.error if self._mic is not None and self._mic.error else "%s (hold): speak" % pg.key.name(self.voice_key).title()
            hint = mic + "   " + hint
        surface.blit(f.render(hint, True, c["hint"]), (x + box_w - f.size(hint)[0] - 14, y + box_h - line_h - 10))
