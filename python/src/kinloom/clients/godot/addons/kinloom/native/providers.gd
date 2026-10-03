extends RefCounted
## Models: any chat-completions endpoint, Claude, scripted answers, fallbacks, the environment's keys, voices.

const Py = preload("py.gd")
const Http = preload("http.gd")
const M = preload("model.gd")

const DEAD := ["HTTP 401", "HTTP 402", "HTTP 403"]
const EFFORTS := ["none", "minimal"]
const REFUSED := ["unsupported", "not supported", "invalid", "unrecognized", "unknown", "not permitted", "unexpected", "not allowed", "extra"]
const BLIND := ["image", "vision", "multimodal", "multi-modal"]
const HOSTED := [
	["GEMINI_API_KEY", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai"],
	["GROQ_API_KEY", "groq", "https://api.groq.com/openai/v1"],
	["MISTRAL_API_KEY", "mistral", "https://api.mistral.ai/v1"],
	["TOGETHER_API_KEY", "together", "https://api.together.xyz/v1"],
	["XAI_API_KEY", "xai", "https://api.x.ai/v1"],
	["FIREWORKS_API_KEY", "fireworks", "https://api.fireworks.ai/inference/v1"],
	["CEREBRAS_API_KEY", "cerebras", "https://api.cerebras.ai/v1"],
]
const OPENAI_VOICES := ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse", "marin", "cedar"]
const VOICE_MAX_TEXT := 4000
const MAX_IMAGE := 8 * 1024 * 1024
const LANGS := {"french": "fr", "français": "fr", "francais": "fr", "english": "en", "anglais": "en", "spanish": "es",
	"español": "es", "german": "de", "deutsch": "de", "italian": "it", "italiano": "it"}


static func env(name: String) -> String:
	return OS.get_environment(name)


## The providers the environment allows, best first (the same order as Python's), as makers.
static func candidates() -> Array:
	var model := env("KINLOOM_MODEL")
	var out := []
	if env("KINLOOM_BASE_URL") != "" and model != "":
		var key := env("KINLOOM_API_KEY")
		if key == "":
			key = env("DEEPSEEK_API_KEY")
		if key == "":
			key = env("OPENAI_API_KEY")
		var base := env("KINLOOM_BASE_URL")
		out.append(func(): return OpenAICompatible.new(base, key, model, "custom", base.contains("deepseek")))
	if env("OPENROUTER_API_KEY") != "" and model.contains("/"):
		out.append(func(): return OpenAICompatible.new("https://openrouter.ai/api/v1", env("OPENROUTER_API_KEY"), model, "openrouter"))
	if env("DEEPSEEK_API_KEY") != "" and (model == "" or Py.lower(model).contains("deepseek") or env("DEEPSEEK_BASE_URL") != ""):
		var base := env("DEEPSEEK_BASE_URL") if env("DEEPSEEK_BASE_URL") != "" else "https://api.deepseek.com"
		out.append(func(): return OpenAICompatible.new(base, env("DEEPSEEK_API_KEY"), model if model != "" else "deepseek-flash", "deepseek", true))
	if env("ANTHROPIC_API_KEY") != "" and (model == "" or Py.lower(model).contains("claude") or env("ANTHROPIC_BASE_URL") != ""):
		var base := env("ANTHROPIC_BASE_URL") if env("ANTHROPIC_BASE_URL") != "" else "https://api.anthropic.com"
		out.append(func(): return Anthropic.new(env("ANTHROPIC_API_KEY"), model if model != "" else "claude-haiku-4-5", base))
	if env("OPENAI_API_KEY") != "" and model != "":
		var base := env("OPENAI_BASE_URL") if env("OPENAI_BASE_URL") != "" else "https://api.openai.com/v1"
		out.append(func(): return OpenAICompatible.new(base, env("OPENAI_API_KEY"), model, "openai"))
	for h in HOSTED:
		if env(h[0]) != "" and model != "":
			var hv: Array = h
			out.append(func(): return OpenAICompatible.new(hv[2], env(hv[0]), model, hv[1]))
	if env("OPENROUTER_API_KEY") != "" and model != "" and not model.contains("/"):
		out.append(func(): return OpenAICompatible.new("https://openrouter.ai/api/v1", env("OPENROUTER_API_KEY"), model, "openrouter"))
	return out


static func _first_of(makers: Array) -> Variant:
	while not makers.is_empty():
		var first = makers.pop_front().call()
		if first != null:
			return Fallback.new(first, makers) if not makers.is_empty() else first
	return null


## The provider from the environment (KINLOOM_SCRIPT / KINLOOM_OFFLINE / keys), or null.
static func detect() -> Variant:
	if Py.lower(env("KINLOOM_OFFLINE")) in ["1", "true", "yes"]:
		return null
	if env("KINLOOM_SCRIPT") != "" and FileAccess.file_exists(env("KINLOOM_SCRIPT")):
		var r := Py.loads(FileAccess.get_file_as_string(env("KINLOOM_SCRIPT")))
		if r[0]:
			return Scripted.new(r[1], "script")
	return _first_of(candidates())


## A provider from what the game gave: null, "auto", a Callable, a list, an object with complete(), or a spec
## {kind, url, key, model, name, script}.
static func provider_of(option: Variant) -> Variant:
	if option == null:
		return null
	if typeof(option) == TYPE_STRING and option == "auto":
		return detect()
	if option is Callable:
		return Scripted.new(option)
	if option is Array:
		var makers := []
		for spec in option:
			var s = spec
			makers.append(func(): return provider_of(s))
		return _first_of(makers)
	if option is Object and option.has_method("complete"):
		return option
	if not (option is Dictionary):
		return null
	var spec: Dictionary = option
	if spec.get("script") != null:
		return Scripted.new(spec["script"], "script")
	var url: String = str(spec.get("url", "")) if spec.get("url") != null else ""
	var model: String = str(spec.get("model", "")) if spec.get("model") != null else ""
	var key: String = str(spec.get("key", "")) if spec.get("key") != null else ""
	var kind := ""
	if spec.get("kind") != null and str(spec["kind"]) != "":
		kind = str(spec["kind"])
	elif url.contains("anthropic.com"):
		kind = "anthropic"
	elif Py.lower(model).begins_with("claude") and url == "":
		kind = "anthropic"
	else:
		kind = "openai"
	kind = Py.lower(kind)
	if kind == "anthropic":
		return Anthropic.new(key, model if model != "" else "claude-haiku-4-5", url if url != "" else "https://api.anthropic.com")
	if kind == "deepseek":
		return OpenAICompatible.new(url if url != "" else "https://api.deepseek.com", key, model if model != "" else "deepseek-flash", "deepseek", true)
	if kind == "openrouter" or url.contains("openrouter.ai"):
		return OpenAICompatible.new(url if url != "" else "https://openrouter.ai/api/v1", key, model, "openrouter")
	if url == "" and model == "":
		return null
	if url == "":
		url = "https://api.openai.com/v1"
	var name: String = str(spec["name"]) if spec.get("name") != null else ("deepseek" if url.contains("deepseek") else "custom")
	return OpenAICompatible.new(url, key, model, name, url.contains("deepseek"))


## Any chat-completions endpoint: OpenAI, OpenRouter, DeepSeek, Groq, Gemini, Mistral, Together, xAI, Ollama, LM Studio...
class OpenAICompatible:
	var adapt := {}
	var base_url := ""
	var key := ""
	var model := ""
	var name := ""
	var deepseek := false
	var effort := 0

	func _init(base_url_: String, key_: String, model_: String, name_ := "openai-compatible", deepseek_ := false) -> void:
		base_url = base_url_
		while base_url.ends_with("/"):
			base_url = base_url.substr(0, base_url.length() - 1)
		key = key_
		model = model_
		name = name_
		deepseek = deepseek_
		effort = 0 if not (name in ["deepseek", "openrouter"]) and not deepseek else EFFORTS.size()

	## The same endpoint and key with another model id (models per task).
	func with_model(m: String) -> Variant:
		return get_script().new(base_url, key, m, name, deepseek)

	func local() -> bool:
		return Http.is_local(base_url, name)

	func patient() -> bool:
		return local()

	func describe() -> String:
		return name + " (" + model + ")"

	func body(system: String, user: String, json: bool, max_tokens: int, temperature: float, images: Variant) -> Dictionary:
		var content: Variant = user
		if images is Array and not images.is_empty():
			content = [{"type": "text", "text": user}]
			for p in images:
				content.append({"type": "image_url", "image_url": {"url": "data:" + p.mime + ";base64," + p.b64}})
		var b := {"model": model, "messages": [{"role": "system", "content": M.json_prompt(system, user) if json else system}, {"role": "user", "content": content}]}
		b["max_completion_tokens" if adapt.has("max_tokens") else "max_tokens"] = max_tokens
		if not adapt.has("temperature"):
			b["temperature"] = temperature
		if json and not adapt.has("response_format"):
			b["response_format"] = {"type": "json_object"}
		if deepseek:
			b["thinking"] = {"type": "disabled"}
		if name == "openrouter" and not adapt.has("reasoning"):
			b["reasoning"] = {"enabled": false}
		if effort < EFFORTS.size():
			b["reasoning_effort"] = EFFORTS[effort]
		return b

	func learn(status: Variant, text: String, images: Variant) -> bool:
		if status != 400:
			return false
		var low := Py.lower(text)
		if images is Array and not images.is_empty() and not adapt.has("images"):
			for w in BLIND:
				if low.contains(w):
					adapt["images"] = true
					return true
		var refused := false
		for w in REFUSED:
			if low.contains(w):
				refused = true
		if not refused:
			return false
		if low.contains("reasoning_effort") and effort < EFFORTS.size():
			effort += 1
			return true
		for param in ["max_tokens", "temperature", "response_format", "reasoning"]:
			if low.contains(param) and not adapt.has(param):
				adapt[param] = true
				return true
		return false

	func warm() -> void:
		if local():
			await complete("Kinloom task: warm", "Say OK.", {"max_tokens": 1, "timeout": 120.0})

	func headers() -> Dictionary:
		return {"Authorization": "Bearer " + key} if key != "" else {}

	## o: {json, max_tokens, temperature, timeout, images, on_text}.
	func complete(system: String, user: String, o := {}) -> Dictionary:
		var json: bool = o.get("json", false)
		var max_tokens: int = o.get("max_tokens", 400)
		var temperature: float = o.get("temperature", 0.8)
		var start := Http.now()
		var deadline: float = start + float(o.get("timeout", 15.0))
		var url := base_url + "/chat/completions"
		var images = o.get("images")
		var has_images: bool = images is Array and not images.is_empty()
		var status = null
		var text := "failed"
		for i in 7:
			var sent = images if has_images and not adapt.has("images") else null
			var b := body(system, user, json, max_tokens, temperature, sent)
			if o.get("on_text") is Callable:
				var r: Dictionary = await stream(url, b, deadline, start, o["on_text"])
				var err: String = r.error if r.error != null else ""
				if not r.ok and learn(400 if err.begins_with("HTTP 400") else 0, err, sent):
					continue
				r.blind = has_images and sent == null
				return r
			var got: Array = await Http.post(url, headers(), b, deadline)
			status = got[0]
			text = got[1]
			if not learn(status, text, sent):
				break
		var blind: bool = has_images and adapt.has("images")
		if status != 200:
			return M.reply(false, "", ("HTTP " + str(status) + ": " + text.substr(0, 200)) if status != null else text, 0, 0, 0, Http.now() - start)
		var root := Py.loads(text)
		var content := ""
		var usage := {}
		var ok: bool = root[0] and root[1] is Dictionary and root[1].get("choices") is Array and not root[1]["choices"].is_empty() \
			and root[1]["choices"][0] is Dictionary and root[1]["choices"][0].get("message") is Dictionary
		if not ok:
			return M.reply(false, "", "unreadable answer: " + text.substr(0, 200), 0, 0, 0, Http.now() - start)
		var c = root[1]["choices"][0]["message"].get("content")
		content = c if typeof(c) == TYPE_STRING else ""
		usage = root[1].get("usage") if root[1].get("usage") is Dictionary else {}
		var cached := M.int_of(usage, "prompt_cache_hit_tokens")
		if cached == 0:
			cached = M.int_of(usage.get("prompt_tokens_details", {}), "cached_tokens")
		if Py.strip(content) == "":
			return M.reply(false, "", "empty answer", 0, 0, 0, Http.now() - start)
		var r := M.reply(true, content, null, M.int_of(usage, "prompt_tokens"), cached, M.int_of(usage, "completion_tokens"), Http.now() - start)
		r.blind = blind
		return r

	func stream(url: String, b: Dictionary, deadline: float, start: float, on_text: Callable) -> Dictionary:
		var parts := []
		var usage := {}
		var line := func(l: String) -> void:
			if not l.begins_with("data:"):
				return
			var payload := Py.strip(l.substr(5))
			if payload == "[DONE]":
				return
			var r := Py.loads(payload)
			if not r[0] or not (r[1] is Dictionary):
				return
			if r[1].get("usage") is Dictionary:
				usage.merge(r[1]["usage"], true)
			if r[1].get("choices") is Array:
				for c in r[1]["choices"]:
					var piece = c.get("delta", {}).get("content") if c is Dictionary and c.get("delta") is Dictionary else null
					if typeof(piece) == TYPE_STRING and piece != "":
						parts.append(piece)
						on_text.call(piece)
		var sent := b.duplicate()
		sent["stream"] = true
		sent["stream_options"] = {"include_usage": true}
		var got: Array = await Http.post(url, headers(), sent, deadline, line)
		var text := "".join(parts)
		if got[0] != 200:
			return M.reply(false, text, ("HTTP " + str(got[0]) + ": " + str(got[1]).substr(0, 200)) if got[0] != null else str(got[1]), 0, 0, 0, Http.now() - start)
		if Py.strip(text) == "":
			return M.reply(false, "", "empty answer", 0, 0, 0, Http.now() - start)
		var cached := M.int_of(usage, "prompt_cache_hit_tokens")
		if cached == 0:
			cached = M.int_of(usage.get("prompt_tokens_details", {}), "cached_tokens")
		return M.reply(true, text, null, M.int_of(usage, "prompt_tokens"), cached, M.int_of(usage, "completion_tokens"), Http.now() - start)


## Claude through the Messages API.
class Anthropic:
	var name := "anthropic"
	var key := ""
	var model := ""
	var base_url := ""

	func _init(key_: String, model_ := "claude-haiku-4-5", base_url_ := "https://api.anthropic.com") -> void:
		key = key_
		model = model_
		base_url = base_url_
		while base_url.ends_with("/"):
			base_url = base_url.substr(0, base_url.length() - 1)

	func with_model(m: String) -> Variant:
		return get_script().new(key, m, base_url)

	func local() -> bool:
		return Http.is_local(base_url, name)

	func patient() -> bool:
		return local()

	func describe() -> String:
		return name + " (" + model + ")"

	func complete(system: String, user: String, o := {}) -> Dictionary:
		var start := Http.now()
		var deadline: float = start + float(o.get("timeout", 15.0))
		var sys := system + ("\nAnswer with a single JSON object and nothing else." if o.get("json", false) else "")
		var content: Variant = user
		var images = o.get("images")
		if images is Array and not images.is_empty():
			content = []
			for p in images:
				content.append({"type": "image", "source": {"type": "base64", "media_type": p.mime, "data": p.b64}})
			content.append({"type": "text", "text": user})
		var b := {"model": model, "max_tokens": int(o.get("max_tokens", 400)),
			"system": [{"type": "text", "text": sys, "cache_control": {"type": "ephemeral"}}], "messages": [{"role": "user", "content": content}]}
		var hdrs := {"x-api-key": key, "anthropic-version": "2023-06-01"}
		var url := base_url + "/v1/messages"
		if o.get("on_text") is Callable:
			var on_text: Callable = o["on_text"]
			var parts := []
			var usage := {}
			var stop := {}
			var line := func(l: String) -> void:
				if not l.begins_with("data:"):
					return
				var r := Py.loads(Py.strip(l.substr(5)))
				if not r[0] or not (r[1] is Dictionary):
					return
				var e: Dictionary = r[1]
				if e.get("type") == "message_start":
					if e.get("message") is Dictionary and e["message"].get("usage") is Dictionary:
						usage.merge(e["message"]["usage"], true)
				elif e.get("type") == "content_block_delta":
					var piece = e.get("delta", {}).get("text") if e.get("delta") is Dictionary else null
					if typeof(piece) == TYPE_STRING and piece != "":
						parts.append(piece)
						on_text.call(piece)
				elif e.get("type") == "message_delta":
					if e.get("usage") is Dictionary:
						usage.merge(e["usage"], true)
					if e.get("delta") is Dictionary:
						stop.merge(e["delta"], true)
			var sent := b.duplicate()
			sent["stream"] = true
			var got: Array = await Http.post(url, hdrs, sent, deadline, line)
			var text := "".join(parts)
			if got[0] != 200 or stop.get("stop_reason") == "refusal" or Py.strip(text) == "":
				return M.reply(false, text, got[1] if got[1] is String and got[1] != "" else "refused or empty", 0, 0, 0, Http.now() - start)
			var cached := M.int_of(usage, "cache_read_input_tokens")
			return M.reply(true, text, null, M.int_of(usage, "input_tokens") + cached + M.int_of(usage, "cache_creation_input_tokens"), cached,
				M.int_of(usage, "output_tokens"), Http.now() - start)
		var got: Array = await Http.post(url, hdrs, b, deadline)
		if got[0] != 200:
			return M.reply(false, "", ("HTTP " + str(got[0]) + ": " + str(got[1]).substr(0, 200)) if got[0] != null else str(got[1]), 0, 0, 0, Http.now() - start)
		var root := Py.loads(got[1])
		if not root[0] or not (root[1] is Dictionary):
			return M.reply(false, "", "unreadable answer", 0, 0, 0, Http.now() - start)
		if root[1].get("stop_reason") == "refusal":
			return M.reply(false, "", "refusal", 0, 0, 0, Http.now() - start)
		var out := ""
		if root[1].get("content") is Array:
			for blk in root[1]["content"]:
				if blk is Dictionary and blk.get("type") == "text" and typeof(blk.get("text")) == TYPE_STRING:
					out += blk["text"]
		var usage: Dictionary = root[1].get("usage") if root[1].get("usage") is Dictionary else {}
		var cached := M.int_of(usage, "cache_read_input_tokens")
		if Py.strip(out) == "":
			return M.reply(false, "", "empty answer", 0, 0, 0, Http.now() - start)
		return M.reply(true, out, null, M.int_of(usage, "input_tokens") + cached + M.int_of(usage, "cache_creation_input_tokens"), cached,
			M.int_of(usage, "output_tokens"), Http.now() - start)


## Tests and replays: fn(kind, system, user) -> text or null (null = a failed call); or a script {task: answer | [answers]}.
class Scripted:
	var name := "scripted"
	var model := "scripted"
	var fn = null
	var queues := {}
	var single := {}

	func _init(given: Variant, name_ := "scripted") -> void:
		name = name_
		model = name_
		if given is Callable:
			fn = given
		elif given is Dictionary:
			for k in given:
				var v = given[k]
				queues[k] = v.duplicate() if v is Array else [v]
				if not (v is Array):
					single[k] = true

	func describe() -> String:
		return name

	func with_model(m: String) -> Variant:
		var s = get_script().new(null, name)
		s.fn = fn
		s.queues = queues
		s.single = single
		s.model = m
		return s

	func local() -> bool:
		return false

	func patient() -> bool:
		return false

	func _answer(system: String) -> Variant:
		var m := Py.re("Kinloom task: ([A-Za-z0-9_]+)").search(system)
		var t := m.get_string(1) if m != null else "*"
		var own = queues.get(t)
		var a = null
		if own != null and not own.is_empty() and single.has(t):
			a = own[0]
		elif own != null and not own.is_empty():
			a = own.pop_front()
		else:
			var shared = queues.get("*")
			if shared == null or shared.is_empty():
				return null
			a = shared.pop_front() if shared.size() > 1 else shared[0]
		return a if typeof(a) == TYPE_STRING else Py.dumps(a)

	func complete(system: String, user: String, o := {}) -> Dictionary:
		var images = o.get("images")
		if images is Array and not images.is_empty():
			var l := []
			for p in images:
				l.append("[image: " + p.mime + ", " + str(p.bytes) + " bytes]")
			user = user + "\n" + " ".join(l)
		var text = null
		if fn != null:
			text = await fn.call("json" if o.get("json", false) else "text", system, user)
		else:
			text = _answer(system)
		if text == null:
			return M.reply(false, "", "no scripted answer")
		if o.get("on_text") is Callable:
			o["on_text"].call(text)
		return M.reply(true, text, null, (system.length() + user.length()) / 4, 0, text.length() / 4, 0.0)


## Several providers in order: a dead key (401, 402, 403) hands over to the next one for good.
class Fallback:
	var switched: Array = []
	var current
	var rest: Array = []

	func _init(first, rest_: Array) -> void:
		current = first
		rest = rest_

	var name: String:
		get:
			return current.name

	var model: String:
		get:
			return current.model

	var base_url: String:
		get:
			return current.base_url if "base_url" in current else ""

	func local() -> bool:
		return current.local() if current.has_method("local") else false

	func patient() -> bool:
		return current.patient() if current.has_method("patient") else local()

	func describe() -> String:
		return current.describe() if current.has_method("describe") else current.name

	func with_model(m: String) -> Variant:
		return current.with_model(m) if current.has_method("with_model") else null

	func warm() -> void:
		if current.has_method("warm"):
			await current.warm()

	func complete(system: String, user: String, o := {}) -> Dictionary:
		var start := Http.now()
		var timeout: float = float(o.get("timeout", 15.0))
		while true:
			var used = current
			var oo := o.duplicate()
			oo["timeout"] = maxf(0.5, timeout - (Http.now() - start))
			var r: Dictionary = await used.complete(system, user, oo)
			var err: String = r.error if r.error != null else ""
			var dead := false
			for d in DEAD:
				if err.begins_with(d):
					dead = true
			if r.ok or not dead or r.text != "":
				return r
			if current == used:
				var next = null
				while not rest.is_empty() and next == null:
					next = rest.pop_front().call()
				if next == null:
					return r
				switched.append((used.describe() if used.has_method("describe") else used.name) + ": " + err.substr(0, 60) + " -> " +
					(next.describe() if next.has_method("describe") else next.name))
				current = next
			if Http.now() - start >= timeout:
				return r
		return M.reply(false)


# ---------------- voice: OpenAI-compatible speech and transcription ----------------

class OpenAIVoice:
	var base_url := ""
	var key := ""
	var speak_model = "gpt-4o-mini-tts"
	var listen_model = "gpt-4o-mini-transcribe"
	var voices: Array = OPENAI_VOICES
	var name := "openai"

	func _init(spec: Dictionary) -> void:
		base_url = str(spec.get("url", "https://api.openai.com/v1")) if spec.get("url") != null else "https://api.openai.com/v1"
		while base_url.ends_with("/"):
			base_url = base_url.substr(0, base_url.length() - 1)
		key = str(spec.get("key", "")) if spec.get("key") != null else ""
		if spec.has("speak_model"):
			speak_model = spec["speak_model"]
		if spec.has("listen_model"):
			listen_model = spec["listen_model"]
		if spec.get("voices") is Array:
			voices = spec["voices"]
		if spec.get("name") != null:
			name = str(spec["name"])

	func can_speak() -> bool:
		return Py.truthy(speak_model)

	func can_listen() -> bool:
		return Py.truthy(listen_model)

	func describe() -> String:
		return name + " (" + (str(speak_model) if Py.truthy(speak_model) else "-") + " / " + (str(listen_model) if Py.truthy(listen_model) else "-") + ")"

	func headers() -> Dictionary:
		return {"Authorization": "Bearer " + key} if key != "" else {}

	## voice: {id, seed, describe}. [wav bytes or null, error].
	func speak(text: String, voice: Dictionary, timeout := 15.0) -> Array:
		if not Py.truthy(speak_model):
			return [null, "no speak model"]
		var b := {"model": speak_model, "input": text.substr(0, VOICE_MAX_TEXT), "response_format": "wav",
			"voice": voice["id"] if Py.truthy(voice.get("id")) else M.stable_pick(voices, voice.get("seed"))}
		if Py.truthy(voice.get("describe")) and not str(speak_model).begins_with("tts-1"):
			b["instructions"] = str(voice["describe"]).substr(0, 1000)
		var got: Array = await Http.post(base_url + "/audio/speech", headers(), b, Http.now() + timeout, Callable(), true)
		if got[0] != 200 or not (got[1] is PackedByteArray):
			var t: String = got[1].slice(0, 200).get_string_from_utf8() if got[1] is PackedByteArray else str(got[1]).substr(0, 200)
			return [null, "HTTP " + str(got[0]) + ": " + t]
		return [got[1], ""] if M.audio_format(got[1]) == "wav" else [null, "the answer is not WAV audio"]

	func listen(data: PackedByteArray, fmt: Variant, language: Variant = null, timeout := 20.0) -> Array:
		if not Py.truthy(listen_model):
			return [null, "no listen model"]
		var fields := [["model", listen_model]]
		var code = M.language_code(language)
		if code != null:
			fields.append(["language", code])
		fields.append(["response_format", "json"])
		var mimes := {"wav": "audio/wav", "webm": "audio/webm", "ogg": "audio/ogg", "mp3": "audio/mpeg", "flac": "audio/flac", "m4a": "audio/mp4"}
		var f: String = fmt if typeof(fmt) == TYPE_STRING and fmt != "" else "wav"
		var body := Http.form(fields, ["file", "speech." + f, mimes.get(f, "application/octet-stream"), data])
		var got: Array = await Http.post(base_url + "/audio/transcriptions", headers(), body, Http.now() + timeout)
		if got[0] != 200:
			return [null, "HTTP " + str(got[0]) + ": " + str(got[1]).substr(0, 200)]
		var r := Py.loads(got[1])
		if not r[0] or not (r[1] is Dictionary):
			return [null, "unreadable answer"]
		return [Py.text_of(r[1].get("text", "")) if r[1].get("text") != null else "", ""]
