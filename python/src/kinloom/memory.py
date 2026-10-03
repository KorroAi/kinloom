"""What characters remember: notes per session and scope (a character, or "world"), ranked by importance,
recency and relevance, saved to a JSON file in the background so games never wait on disk."""
import json
import os
import re
import threading
import time

MAX_NOTES = 120
MAX_NOTE = 300
_WORD = re.compile(r"[a-zA-Z0-9À-ɏ]{3,}")
_STOP = {"the", "and", "for", "with", "that", "this", "you", "your", "are", "was", "has", "have", "not", "but", "from", "they",
         "them", "its", "into", "who", "what", "just"}


def _words(text):
    return {w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP}


class Memory:
    def __init__(self, path=None, clock=time.time):
        self.path = os.path.abspath(path) if path else None    # fixed now: a game that changes folder keeps its memory
        self.clock = clock
        self._notes = {}          # (session, scope) -> [ {t, text, importance} ]
        self._extra = {}          # section -> {key: JSON value}: learned minds, opinions, what was shared
        self._lock = threading.Lock()
        self._dirty = False
        self._timer = None
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for session, scopes in (data.get("sessions") or {}).items():
                    for scope, notes in scopes.items():
                        self._notes[(session, scope)] = [n for n in notes if isinstance(n, dict) and isinstance(n.get("text"), str)]
                extra = data.get("extra")
                if isinstance(extra, dict):
                    self._extra = {str(k): v for k, v in extra.items() if isinstance(v, dict)}
            except (OSError, ValueError, AttributeError):
                pass  # a broken memory file must not stop the game; it is replaced on the next save

    def add(self, session, scope, text, importance=0.5, **meta):
        """meta: small JSON values kept with the note (eid, tag, by, src, orig, impact: what the world layer tracks)."""
        text = " ".join(str(text).split())[:MAX_NOTE]
        if not text:
            return
        try:
            importance = max(0.0, min(1.0, float(importance)))
        except (TypeError, ValueError):
            importance = 0.5
        if importance != importance:
            importance = 0.5
        note = {"t": self.clock(), "text": text, "importance": importance}
        note.update({k: v for k, v in meta.items() if v is not None and isinstance(v, (str, int, float, bool))})
        with self._lock:
            notes = self._notes.setdefault((session, scope), [])
            notes.append(note)
            if len(notes) > MAX_NOTES:
                notes.sort(key=lambda n: (n["importance"], n["t"]))
                del notes[: len(notes) - MAX_NOTES]
                notes.sort(key=lambda n: n["t"])
            self._dirty = True
        self._schedule_save()

    def notes(self, session, scope):
        """Copies of the notes of a scope, oldest first."""
        with self._lock:
            return [dict(n) for n in self._notes.get((session, scope), [])]

    def annotate(self, session, scope, eid, **meta):
        with self._lock:
            for n in self._notes.get((session, scope), []):
                if n.get("eid") == eid:
                    n.update({k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))})
                    self._dirty = True
        self._schedule_save()

    def get(self, section, key, default=None):
        with self._lock:
            return self._extra.get(section, {}).get(key, default)

    def put(self, section, key, value):
        """Stores a JSON value that survives restarts (saved in the background with the notes)."""
        with self._lock:
            self._extra.setdefault(section, {})[key] = value
            self._dirty = True
        self._schedule_save()

    def delete(self, section, key):
        with self._lock:
            if self._extra.get(section, {}).pop(key, None) is not None:
                self._dirty = True
        self._schedule_save()

    def session_notes(self, session):
        """{scope: [notes]} of one session (copies): what a save slot keeps."""
        with self._lock:
            return {scope: [dict(n) for n in notes] for (s, scope), notes in self._notes.items() if s == session and notes}

    def replace_session(self, session, notes):
        """The session's notes become these ({scope: [notes]}, as session_notes gives them): a save slot loaded."""
        with self._lock:
            for key in [k for k in self._notes if k[0] == session]:
                del self._notes[key]
            for scope, items in notes.items():
                kept = [dict(n) for n in items if isinstance(n, dict) and isinstance(n.get("text"), str)
                        and isinstance(n.get("t"), (int, float)) and isinstance(n.get("importance"), (int, float))]
                if kept:
                    self._notes[(session, str(scope))] = kept[-MAX_NOTES:]
            self._dirty = True
        self._schedule_save()

    def all(self, session, scope):
        with self._lock:
            return [n["text"] for n in self._notes.get((session, scope), [])]

    def recall(self, session, scopes, query="", k=6, personal=True):
        """The k most useful notes across scopes: 0.45 importance + 0.35 recency + 0.2 overlap with the query.
        personal=False leaves out notes about one person (what someone said or told): for talking to a stranger."""
        q = _words(query)
        with self._lock:
            notes = [n for s in scopes for n in self._notes.get((session, s), []) if personal or not n.get("about")]
        if not notes:
            return []
        newest = max(n["t"] for n in notes)
        oldest = min(n["t"] for n in notes)
        span = max(1.0, newest - oldest)

        def score(n):
            recency = (n["t"] - oldest) / span
            overlap = len(q & _words(n["text"])) / len(q) if q else 0.0
            return 0.45 * n["importance"] + 0.35 * recency + 0.2 * overlap

        best = sorted(notes, key=score, reverse=True)[:k]
        return [n["text"] for n in sorted(best, key=lambda n: n["t"])]

    # ---------- saving ----------

    def _schedule_save(self):
        if not self.path:
            return
        with self._lock:
            if self._timer is not None:
                return
            self._timer = threading.Timer(1.0, self.save)
            self._timer.daemon = True
            self._timer.start()

    def save(self):
        if not self.path:
            return
        with self._lock:
            self._timer = None
            if not self._dirty:
                return
            data = {"version": 1, "sessions": {}, "extra": self._extra}
            for (session, scope), notes in self._notes.items():
                data["sessions"].setdefault(session, {})[scope] = notes
            data = json.loads(json.dumps(data))   # a snapshot: the game may change values while the file is written
            self._dirty = False
        folder = os.path.dirname(os.path.abspath(self.path))
        try:
            os.makedirs(folder, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
        except OSError:
            with self._lock:
                self._dirty = True  # try again on the next change or on close
