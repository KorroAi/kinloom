extends RefCounted
## HTTP for the native brain: HTTPClient polled once per frame (the game never waits), TLS by Godot, SSE lines.

const Py = preload("py.gd")

const TRANSIENT := [408, 409, 429, 500, 502, 503, 504, 529]
const MAX_ANSWER := 4000000


static func now() -> float:
	return Time.get_ticks_usec() / 1000000.0


static func frame() -> Signal:
	return (Engine.get_main_loop() as SceneTree).process_frame


## [tls, host, port, path] or [] for a URL that is not http(s).
static func split_url(url: String) -> Array:
	var tls := false
	var rest := url
	if url.begins_with("https://"):
		tls = true
		rest = url.substr(8)
	elif url.begins_with("http://"):
		rest = url.substr(7)
	else:
		return []
	var slash := rest.find("/")
	var hostport := rest if slash < 0 else rest.substr(0, slash)
	var path := "/" if slash < 0 else rest.substr(slash)
	if hostport.contains("@"):
		hostport = hostport.substr(hostport.rfind("@") + 1)
	var host := hostport
	var port := 443 if tls else 80
	if hostport.begins_with("["):
		var close := hostport.find("]")
		if close < 0:
			return []
		host = hostport.substr(1, close - 1)
		if hostport.substr(close + 1).begins_with(":"):
			port = int(hostport.substr(close + 2))
	elif hostport.contains(":"):
		host = hostport.substr(0, hostport.rfind(":"))
		port = int(hostport.substr(hostport.rfind(":") + 1))
	if host == "" or port <= 0 or port > 65535:
		return []
	if host == "localhost":
		host = "127.0.0.1"
	return [tls, host, port, path]


static func host_of(url: String) -> String:
	var p := split_url(url)
	return Py.lower(p[1]) if not p.is_empty() else ""


static func is_local(url: String, name: String) -> bool:
	return host_of(url) in ["127.0.0.1", "localhost", "::1", "0.0.0.0"] or name == "ollama"


## Requests in flight. stopping (set by Kinloom.shutdown()): open connections close at their next poll and new ones
## are refused, so nothing is left open when the game quits (Godot crashes on exit if a connection is freed then).
static var open := 0
static var stopping := false


## One request: [status or null, PackedByteArray body or error text, headers {lowercase: value}].
## on_line: called with each line of the answer as it arrives (SSE); the body is then empty.
static func request(method: int, url: String, headers: Dictionary, data: PackedByteArray, deadline: float, on_line := Callable()) -> Array:
	if stopping:
		return [null, "closed", {}]
	open += 1
	var r: Array = await _request(method, url, headers, data, deadline, on_line)
	open -= 1
	return r


static func _over(deadline: float) -> bool:
	return stopping or now() > deadline


static func _request(method: int, url: String, headers: Dictionary, data: PackedByteArray, deadline: float, on_line: Callable) -> Array:
	var parts := split_url(url)
	if parts.is_empty():
		return [null, "bad url " + url, {}]
	var client := HTTPClient.new()
	var tls_options: TLSOptions = TLSOptions.client() if parts[0] else null
	if client.connect_to_host(parts[1], parts[2], tls_options) != OK:
		return [null, "network error: cannot connect", {}]
	while client.get_status() in [HTTPClient.STATUS_RESOLVING, HTTPClient.STATUS_CONNECTING]:
		client.poll()
		if _over(deadline):
			client.close()
			return [null, "timed out", {}]
		if client.get_status() in [HTTPClient.STATUS_RESOLVING, HTTPClient.STATUS_CONNECTING]:
			await frame()
	if client.get_status() != HTTPClient.STATUS_CONNECTED:
		var why := client.get_status()
		client.close()
		return [null, "network error: connection failed (%d)" % why, {}]
	var lines := PackedStringArray()
	for k in headers:
		lines.append(str(k) + ": " + str(headers[k]))
	if client.request_raw(method, parts[3], lines, data) != OK:
		client.close()
		return [null, "network error: request failed", {}]
	while client.get_status() == HTTPClient.STATUS_REQUESTING:
		client.poll()
		if _over(deadline):
			client.close()
			return [null, "timed out", {}]
		if client.get_status() == HTTPClient.STATUS_REQUESTING:
			await frame()
	if not (client.get_status() in [HTTPClient.STATUS_BODY, HTTPClient.STATUS_CONNECTED]):
		var why := client.get_status()
		client.close()
		return [null, "network error: no answer (%d)" % why, {}]
	var status := client.get_response_code()
	var got := {}
	var raw_headers := client.get_response_headers_as_dictionary()
	for k in raw_headers:
		got[str(k).to_lower()] = str(raw_headers[k])
	var body := PackedByteArray()
	var streaming := on_line.is_valid() and status < 400
	var total := 0
	while client.get_status() == HTTPClient.STATUS_BODY:
		client.poll()
		var chunk := client.read_response_body_chunk()
		if chunk.is_empty():
			if _over(deadline):
				client.close()
				return [null, "timed out", got]
			await frame()
			continue
		total += chunk.size()
		if total > MAX_ANSWER:
			client.close()
			return [null, "answer too large", got]
		body.append_array(chunk)
		if streaming:
			var at := body.find(10)
			while at >= 0:
				var line := body.slice(0, at).get_string_from_utf8()
				body = body.slice(at + 1)
				on_line.call(line.trim_suffix("\r"))
				at = body.find(10)
	client.close()
	if streaming:
		if not body.is_empty():
			on_line.call(body.get_string_from_utf8().trim_suffix("\r"))
		return [status, PackedByteArray(), got]
	return [status, body, got]


## POST with a deadline: one retry on transient failures. body: a Dictionary (JSON) or [content type, bytes].
## [status or null, text (or bytes when raw) or error].
static func post(url: String, headers: Dictionary, body: Variant, deadline: float, on_line := Callable(), raw := false) -> Array:
	var data := PackedByteArray()
	var sent := headers.duplicate()
	if body is Array:
		sent["Content-Type"] = body[0]
		data = body[1]
	else:
		sent["Content-Type"] = "application/json"
		data = Py.compact(body).to_utf8_buffer()
	var attempt := 0
	while attempt < 2:
		var left := deadline - now()
		if left <= 0.05:
			return [null, "timed out"]
		var r: Array = await request(HTTPClient.METHOD_POST, url, sent, data, deadline, on_line)
		if r[0] == null:
			if r[1] == "timed out" or r[1] == "answer too large" or attempt == 1:
				return [null, r[1]]
			attempt += 1
			if deadline - now() <= 0.5:
				return [null, "timed out"]
			await wait(0.4)
			continue
		var status: int = r[0]
		if status >= 400:
			var text: String = r[1].get_string_from_utf8().substr(0, 20000)
			if attempt == 0 and status in TRANSIENT:
				var pause := 0.4
				var ra = Py.float_of(r[2].get("retry-after", "")) if r[2].has("retry-after") else null
				if ra != null and not is_nan(ra) and not is_inf(ra):
					pause = minf(2.0, ra)
				attempt += 1
				if deadline - now() <= pause + 0.1:
					return [null, "timed out"]
				await wait(pause)
				continue
			return [status, text]
		if on_line.is_valid():
			return [200, ""]
		return [status, r[1] if raw else r[1].get_string_from_utf8()]
	return [null, "failed"]


static func wait(seconds: float) -> void:
	await (Engine.get_main_loop() as SceneTree).create_timer(seconds, true, false, true).timeout


## A multipart/form-data body: [content type, bytes]. fields: [[name, value], ...]; file: [name, filename, mime, bytes].
static func form(fields: Array, file: Array) -> Array:
	var boundary := "kinloom" + str(randi()) + str(Time.get_ticks_usec())
	var out := PackedByteArray()
	for f in fields:
		out.append_array(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + f[0] + "\"\r\n\r\n" + str(f[1]) + "\r\n").to_utf8_buffer())
	out.append_array(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + file[0] + "\"; filename=\"" + file[1] +
		"\"\r\nContent-Type: " + file[2] + "\r\n\r\n").to_utf8_buffer())
	out.append_array(file[3])
	out.append_array(("\r\n--" + boundary + "--\r\n").to_utf8_buffer())
	return ["multipart/form-data; boundary=" + boundary, out]
