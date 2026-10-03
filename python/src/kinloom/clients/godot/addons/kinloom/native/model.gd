extends RefCounted
## Model replies, picture and audio helpers shared by the providers and the brain.

const Py = preload("py.gd")

const MAX_IMAGE := 8 * 1024 * 1024
const LANGS := {"french": "fr", "français": "fr", "francais": "fr", "english": "en", "anglais": "en", "spanish": "es",
	"español": "es", "german": "de", "deutsch": "de", "italian": "it", "italiano": "it"}


static func reply(ok: bool, text := "", error: Variant = null, input := 0, cached := 0, output := 0, latency := 0.0) -> Dictionary:
	return {"ok": ok, "text": text, "error": error, "input": input, "cached": cached, "output": output, "latency": latency, "cut": false, "blind": false}


static func int_of(d: Variant, key: String) -> int:
	if d is Dictionary and typeof(d.get(key)) == TYPE_INT:
		return d[key]
	if d is Dictionary and typeof(d.get(key)) == TYPE_FLOAT and d[key] == floorf(d[key]):
		return int(d[key])
	return 0


static func json_prompt(system: String, user: String) -> String:
	return system if Py.lower(system + user).contains("json") else system + "\nAnswer with a single JSON object."


## The same option for the same seed (voices per character that stay the same).
static func stable_pick(options: Array, seed: Variant) -> Variant:
	if options.is_empty():
		return null
	var hex := ("" if seed == null else Py.text_of(seed)).sha1_text()
	var r := 0
	for c in hex:
		r = (r * 16 + c.hex_to_int()) % options.size()
	return options[r]


static func language_code(language: Variant) -> Variant:
	if not Py.truthy(language):
		return null
	var low := Py.lower(Py.strip(Py.text_of(language)))
	if LANGS.has(low):
		return LANGS[low]
	var m := Py.re("^([a-z]{2})(?:[-_][a-z]{2})?$").search(low)
	return m.get_string(1) if m != null else null


static func _ascii(data: PackedByteArray, a: int, b: int) -> String:
	if data.size() < b:
		return ""
	return data.slice(a, b).get_string_from_ascii()


static func audio_format(data: PackedByteArray) -> Variant:
	if _ascii(data, 0, 4) == "RIFF" and _ascii(data, 8, 12) == "WAVE":
		return "wav"
	if data.size() >= 4 and data[0] == 0x1a and data[1] == 0x45 and data[2] == 0xdf and data[3] == 0xa3:
		return "webm"
	if _ascii(data, 0, 4) == "OggS":
		return "ogg"
	if _ascii(data, 0, 3) == "ID3" or (data.size() >= 2 and data[0] == 0xff and (data[1] & 0xe0) == 0xe0):
		return "mp3"
	if _ascii(data, 0, 4) == "fLaC":
		return "flac"
	if _ascii(data, 4, 8) == "ftyp":
		return "m4a"
	return null


static func wav_seconds(data: PackedByteArray) -> float:
	if data.size() < 12:
		return 0.0
	var pos := 12
	var rate := 0
	while pos + 8 <= data.size():
		var id := _ascii(data, pos, pos + 4)
		var size := data.decode_u32(pos + 4)
		if id == "fmt " and pos + 20 <= data.size():
			rate = data.decode_u32(pos + 16)
		if id == "data":
			return mini(size, data.size() - pos - 8) / float(rate) if rate > 0 else 0.0
		pos += 8 + size + (size % 2)
	return 0.0


static func b64decode(text: String) -> Variant:
	var clean := Py.re(Py.SPACE + "+").sub(text, "", true)
	if Py.re("^[A-Za-z0-9+/_-]*={0,2}$").search(clean) == null:
		return null
	clean = clean.replace("-", "+").replace("_", "/")
	while clean.length() % 4 != 0:
		clean += "="
	var out := Marshalls.base64_to_raw(clean)
	return out


## A picture from base64 or a data URI: [{mime, b64, bytes} or null, error or ""].
static func picture_of(value: Variant) -> Array:
	if value == null or (typeof(value) == TYPE_STRING and value == ""):
		return [null, ""]
	if typeof(value) != TYPE_STRING:
		return [null, "image: base64 or a data URI"]
	var text := Py.strip(value)
	var m := Py.re("^data:([\\w.+/-]+);base64,([\\s\\S]*)$").search(text)
	var raw := m.get_string(2) if m != null else text
	if raw.length() > MAX_IMAGE * 4 / 3 + 8:
		return [null, "image larger than 8 MB"]
	var data = b64decode(raw)
	var bad := "image: not a PNG, JPEG, GIF or WebP picture (or a file that does not exist)"
	if data == null or data.is_empty():
		return [null, bad]
	var mime := ""
	if data.size() >= 4 and data[0] == 0x89 and _ascii(data, 1, 4) == "PNG":
		mime = "image/png"
	elif data.size() >= 3 and data[0] == 0xff and data[1] == 0xd8 and data[2] == 0xff:
		mime = "image/jpeg"
	elif _ascii(data, 0, 6) in ["GIF87a", "GIF89a"]:
		mime = "image/gif"
	elif _ascii(data, 0, 4) == "RIFF" and _ascii(data, 8, 12) == "WEBP":
		mime = "image/webp"
	if mime == "":
		return [null, bad]
	return [{"mime": mime, "b64": Marshalls.raw_to_base64(data), "bytes": data.size()}, ""]
