"""Godot, played like a player: real key events into the addon's AIDialogue box, and quitting while a model request is
still open. Both broke in real games (typing stopped after the first message: Godot 4.4+ LineEdit leaves edit mode;
quitting during a native request crashed Godot on exit). Usage: python conformance/godot_ui.py (needs Godot 4.4+;
GODOT=<path> or Godot found as in run.py). Exit code 0 when every check passed."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
from run import GODOT  # noqa: E402

PROJECT = """config_version=5

[application]
config/name="Kinloom Godot UI checks"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.4")
"""

SCENE = """[gd_scene load_steps=2 format=3]
[ext_resource type="Script" path="res://main.gd" id="1"]
[node name="Main" type="Control"]
script = ExtResource("1")
"""

SCRIPT = """extends Control

func _ready() -> void:
	# 1. AIDialogue: the player types a message, presses Enter, then types the next one
	await Kinloom.offline({"memory": ""})
	var d = load("res://addons/kinloom/ai_dialogue.gd").new()
	d.character_name = "MIRA"
	d.offline_line = "Busy."
	d.speak_first = false
	add_child(d)
	await get_tree().process_frame
	d.open()
	for i in 5:
		await get_tree().process_frame
	var line: LineEdit = d._input
	_type("hello")
	_key(KEY_ENTER)
	for i in 30:
		await get_tree().process_frame
	_type("second")
	await get_tree().process_frame
	print("T: dialogue typing after a message: ", "PASS" if line.text == "second" else "FAIL (got '" + line.text + "')")
	_key(KEY_ESCAPE)
	await get_tree().process_frame
	# 2. a native request the model never answers, then the game quits
	await Kinloom.direct(OS.get_environment("HANG_URL"), "fake-key", "fake-model")
	Kinloom.character("HANG", "a test character", {"offline": "..."})
	Kinloom.chat("HANG", "hello?")
	for i in 20:
		await get_tree().process_frame
	var Http = load("res://addons/kinloom/native/http.gd")
	var before: int = Http.open
	var t0 := Time.get_ticks_msec()
	await Kinloom.shutdown(3.0)
	var took := Time.get_ticks_msec() - t0
	var closed: bool = before >= 1 and Http.open == 0 and took < 2500
	print("T: shutdown closes an open request: ", "PASS" if closed else "FAIL (open before %d, after %d, %d ms)" % [before, Http.open, took])
	get_tree().quit(0)


func _type(text: String) -> void:
	for c in text:
		var e := InputEventKey.new()
		e.unicode = c.unicode_at(0)
		e.pressed = true
		get_viewport().push_input(e)


func _key(k: Key) -> void:
	for p in [true, false]:
		var e := InputEventKey.new()
		e.keycode = k
		e.physical_keycode = k
		e.pressed = p
		get_viewport().push_input(e)
"""


def hanging_server():
    """A model endpoint that accepts connections and never answers."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    held = []

    def run():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            held.append(conn)
    threading.Thread(target=run, daemon=True).start()
    return srv, "https://127.0.0.1:%d/v1" % srv.getsockname()[1]


def main():
    if not GODOT:
        print("godot ui: SKIP (Godot not found; set GODOT)")
        return 0
    work = os.path.join(tempfile.mkdtemp(), "godot-ui")
    os.makedirs(work)
    for name, text in (("project.godot", PROJECT), ("main.tscn", SCENE), ("main.gd", SCRIPT)):
        with open(os.path.join(work, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    from kinloom import init                 # the addon exactly as a developer gets it
    init.setup(work, "godot", agents="minimal")
    subprocess.run([GODOT, "--headless", "--import", "--path", work], capture_output=True, timeout=300)
    srv, url = hanging_server()
    start = time.monotonic()
    r = subprocess.run([GODOT, "--headless", "--path", work], capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, HANG_URL=url))
    srv.close()
    lines = [l[3:] for l in r.stdout.splitlines() if l.startswith("T: ")]
    for l in lines:
        print("godot ui: " + l)
    ok = r.returncode == 0 and len(lines) == 2 and all(l.endswith("PASS") for l in lines)
    print("godot ui: %s (exit %d, %.1f s)" % ("PASS" if ok else "FAIL", r.returncode, time.monotonic() - start))
    if not ok:
        print(r.stdout[-3000:] + r.stderr[-3000:])
    shutil.rmtree(os.path.dirname(work), ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
