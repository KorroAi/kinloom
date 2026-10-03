"""Pictures a game shows the model (chat(..., image=), create(..., image=)): read from bytes, a file, base64 or a data
URI, checked by their first bytes (PNG, JPEG, GIF, WebP), at most MAX_IMAGE bytes. Standard library only."""
import base64
import binascii
import os
import re

MAX_IMAGE = 8 * 1024 * 1024
_DATA_URI = re.compile(r"^data:([\w.+/-]+);base64,(.*)$", re.S)


class Picture:
    __slots__ = ("mime", "data")

    def __init__(self, mime, data):
        self.mime, self.data = mime, data

    @property
    def b64(self):
        return base64.b64encode(self.data).decode("ascii")

    @property
    def uri(self):
        return "data:%s;base64,%s" % (self.mime, self.b64)

    def describe(self):
        """What a model that cannot see gets instead (scripted models, tests)."""
        return "[image: %s, %d bytes]" % (self.mime, len(self.data))

    def __repr__(self):
        return "Picture(%s, %d bytes)" % (self.mime, len(self.data))


def kind_of(data):
    """The image type from its first bytes, or None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def picture(value):
    """A Picture from bytes, a file path, base64 text or a data URI; None for None/"" ; ValueError when it is not an
    image Kinloom can send (the message says what was wrong)."""
    if value is None or value == "" or value == b"":
        return None
    if isinstance(value, Picture):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
    elif isinstance(value, str):
        text = value.strip()
        m = _DATA_URI.match(text)
        if m:
            data = _b64(m.group(2))
        elif len(text) < 1024 and os.path.isfile(text):
            if os.path.getsize(text) > MAX_IMAGE:
                raise ValueError("image file larger than %d MB" % (MAX_IMAGE // (1024 * 1024)))
            with open(text, "rb") as f:
                data = f.read()
        else:
            data = _b64(text)
    else:
        raise ValueError("image: bytes, a file path, base64 or a data URI (got %s)" % type(value).__name__)
    if len(data) > MAX_IMAGE:
        raise ValueError("image larger than %d MB" % (MAX_IMAGE // (1024 * 1024)))
    mime = kind_of(data)
    if mime is None:
        raise ValueError("image: not a PNG, JPEG, GIF or WebP picture (or a file that does not exist)")
    return Picture(mime, data)


def _b64(text):
    if len(text) > MAX_IMAGE * 4 // 3 + 8:
        raise ValueError("image larger than %d MB" % (MAX_IMAGE // (1024 * 1024)))
    try:
        return base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("image: not a file path, base64 or a data URI")
