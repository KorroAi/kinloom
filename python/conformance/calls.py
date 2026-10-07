"""Compiles (or parses) every language section of kit/calls.md against its SDK, so the calls agents copy from the brief
always build. Each section is wrapped in a function with the few names it uses as placeholders (typed_text, run, show,
png_bytes...). A language whose toolchain is not installed is skipped, never failed.

    python conformance/calls.py                 # every language found
    python conformance/calls.py js csharp       # these sections only

Toolchains: python (always), js (node), csharp (dotnet), java (javac), rust (cargo), cpp ($CXX, g++ or clang++),
gdscript (Godot: $GODOT or as run.py finds it), lua (luac, or lupa in $LUA_PYTHON / this Python).
Exit code 0 when no section failed."""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KIT = os.path.join(ROOT, "src", "kinloom", "kit", "calls.md")
CLIENTS = os.path.join(ROOT, "src", "kinloom", "clients")


def sections():
    text = open(KIT, encoding="utf-8").read().replace("\r\n", "\n")
    out = {}
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        name, _, body = part.partition("\n")
        out[name.strip()] = body
    return out


def _indent(body, pad):
    return "\n".join(pad + line if line.strip() else line for line in body.split("\n"))


def _run(cmd, cwd=None, timeout=600, env=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def check_python(body, work):
    ast.parse(body)
    return True, ""


def check_js(body, work):
    node = shutil.which("node")
    if not node:
        return None, "node not found"
    path = os.path.join(work, "calls.mjs")
    with open(path, "w", encoding="utf-8") as f:
        f.write('import { Kinloom } from "./kinloom.js";\nconst kl = new Kinloom({ offline: true });\n'
                "let typedText, canvas, recordedBlob; const run = () => {}, show = () => {};\n"
                "async function main() {\n" + _indent(body, "  ") + "\n}\n")
    code, out = _run([node, "--check", path])
    return code == 0, out


def check_csharp(body, work):
    dotnet = shutil.which("dotnet")
    if not dotnet:
        return None, "dotnet not found"
    shutil.copy(os.path.join(CLIENTS, "csharp", "Kinloom.cs"), work)
    with open(os.path.join(work, "calls.csproj"), "w", encoding="utf-8") as f:
        f.write('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Library</OutputType><TargetFramework>netstandard2.1'
                '</TargetFramework><LangVersion>9.0</LangVersion><Nullable>enable</Nullable><NoWarn>CS1998;CS8321;CS0168;CS0219</NoWarn>'
                '</PropertyGroup></Project>')
    with open(os.path.join(work, "Calls.cs"), "w", encoding="utf-8") as f:
        f.write("using System; using System.Collections.Generic; using System.Threading.Tasks; using Kinloom;\n"
                "static class Calls {\n  static void Run(string t, Dictionary<string, object> a) {}\n  static void Show(object a, object b) {}\n"
                "  static async Task M(KinloomClient kl, string typedText, byte[] pngBytes, byte[] wavBytes) {\n" + _indent(body, "    ") + "\n  }\n}\n")
    code, out = _run([dotnet, "build", "-nologo", "-v", "q"], cwd=work)
    return code == 0, "\n".join(l for l in out.splitlines() if "error" in l)


def check_java(body, work):
    javac = shutil.which("javac")
    if not javac:
        return None, "javac not found"
    pkg = os.path.join(work, "kinloom")
    os.makedirs(pkg)
    shutil.copy(os.path.join(CLIENTS, "java", "Kinloom.java"), pkg)
    with open(os.path.join(work, "Calls.java"), "w", encoding="utf-8") as f:
        f.write("import java.util.*;\nimport kinloom.Kinloom;\n@SuppressWarnings(\"unchecked\")\npublic class Calls {\n"
                "  static Map<String, Object> found;\n  static void run(String t, Map<String, Object> a) {}\n  static void show(Object a, Object b) {}\n"
                "  static Map<String, Object> map(Object... kv) { return new HashMap<>(); }\n"
                "  static List<Object> list(Object... xs) { return new ArrayList<>(Arrays.asList(xs)); }\n"
                "  static void m(Kinloom kl, String typedText, byte[] pngBytes, byte[] wavBytes) throws Exception {\n"
                + _indent(body, "    ") + "\n  }\n}\n")
    code, out = _run([javac, "--release", "8", "-Xlint:-options", "-encoding", "UTF-8", "-d", os.path.join(work, "out"),
                      os.path.join(pkg, "Kinloom.java"), os.path.join(work, "Calls.java")])
    return code == 0, out


def check_rust(body, work):
    cargo = shutil.which("cargo")
    if not cargo:
        return None, "cargo not found"
    os.makedirs(os.path.join(work, "src"))
    shutil.copy(os.path.join(CLIENTS, "rust", "kinloom.rs"), os.path.join(work, "src"))
    with open(os.path.join(work, "Cargo.toml"), "w", encoding="utf-8") as f:
        f.write('[package]\nname = "calls"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\n')
    with open(os.path.join(work, "src", "main.rs"), "w", encoding="utf-8") as f:
        f.write("#![allow(unused)]\nmod kinloom;\nuse kinloom::*;\nfn run(t: &str, a: &Json) {}\nfn show(a: &str, b: &str) {}\n"
                "fn m(kl: &Kinloom, typed_text: String, png_bytes: Vec<u8>, wav_bytes: Vec<u8>) {\n" + _indent(body, "    ") + "\n}\nfn main() {}\n")
    code, out = _run([cargo, "build", "-q"], cwd=work, timeout=900)
    return code == 0, out


def check_cpp(body, work):
    cxx = os.environ.get("CXX", "").split() or [x for x in [shutil.which("g++") or shutil.which("clang++")] if x]
    if not cxx:
        return None, "no C++ compiler ($CXX, g++ or clang++)"
    shutil.copy(os.path.join(CLIENTS, "cpp", "kinloom.hpp"), work)
    with open(os.path.join(work, "calls.cpp"), "w", encoding="utf-8") as f:
        f.write('#include "kinloom.hpp"\nusing namespace kinloom;\nvoid run(const std::string&, const Json&) {}\n'
                "void show(const std::string&, const std::string&) {}\n"
                "void m(kinloom::Kinloom& kl, std::string typed_text, std::vector<unsigned char> png_bytes, std::vector<unsigned char> wav_bytes) {\n"
                + _indent(body, "    ") + "\n}\n")
    code, out = _run(cxx + ["-std=c++17", "-c", "calls.cpp", "-o", "calls.o"], cwd=work, timeout=900)
    return code == 0, "\n".join(l for l in out.splitlines() if "error" in l)


def _godot():
    sys.path.insert(0, HERE)
    import run as relay  # noqa: E402  (finds Godot as the conformance runs do)
    return relay.GODOT


def check_gdscript(body, work):
    godot = _godot()
    if not godot:
        return None, "Godot not found"
    shutil.copytree(os.path.join(CLIENTS, "godot", "addons"), os.path.join(work, "addons"))
    with open(os.path.join(work, "project.godot"), "w", encoding="utf-8") as f:
        f.write('config_version=5\n\n[application]\n\nconfig/name="calls"\n')
    # --check-only does not register autoloads: a variable typed with the autoload's script stands in for it (the
    # same static types, so the same inference warnings, which Godot treats as errors)
    with open(os.path.join(work, "calls.gd"), "w", encoding="utf-8", newline="\n") as f:
        f.write('extends Node\n\nconst KinloomScript = preload("res://addons/kinloom/kinloom.gd")\nvar Kinloom: KinloomScript\n\n'
                "func run(t, a):\n\tpass\n\nfunc m(typed_text: String, wav_bytes: PackedByteArray) -> void:\n"
                + _indent(body, "\t") + "\n")
    _run([godot, "--headless", "--path", work, "--import"], timeout=300)
    code, out = _run([godot, "--headless", "--path", work, "--check-only", "-s", "calls.gd"], timeout=300)
    errors = [l for l in out.splitlines() if "ERROR" in l]
    return code == 0 and not errors, "\n".join(errors)


def check_lua(body, work):
    source = "local kl, typed_text, png_bytes, wav_bytes, run, save_file = {}, '', '', '', nil, {}\nreturn function()\n" + body + "\nend\n"
    luac = shutil.which("luac") or shutil.which("luac5.4")
    if luac:
        path = os.path.join(work, "calls.lua")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        code, out = _run([luac, "-p", path])
        return code == 0, out
    python = os.environ.get("LUA_PYTHON") or sys.executable
    probe = ("import sys, lupa.lua54 as l\nr = l.LuaRuntime()\nf = r.eval('load')(sys.stdin.read(), 'calls')\n"
             "print('ok' if f is not None else 'syntax error')")
    try:
        r = subprocess.run([python, "-c", probe], input=source, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except OSError:
        return None, "no luac and no lupa"
    if "No module named" in r.stderr:
        return None, "no luac and no lupa"
    return r.stdout.strip() == "ok", r.stdout + r.stderr


CHECKS = {"python": check_python, "js": check_js, "csharp": check_csharp, "java": check_java, "rust": check_rust,
          "cpp": check_cpp, "gdscript": check_gdscript, "lua": check_lua}


def main(only=()):
    found = sections()
    failed = 0
    for name, check in CHECKS.items():
        if only and name not in only:
            continue
        if name not in found:
            print("%s: FAIL (no section in calls.md)" % name)
            failed += 1
            continue
        work = tempfile.mkdtemp(prefix="kinloom-calls-")
        try:
            ok, out = check(found[name], work)
        except (OSError, SyntaxError, subprocess.TimeoutExpired) as e:
            ok, out = False, "%s: %s" % (type(e).__name__, e)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if ok is None:
            print("%s: SKIP (%s)" % (name, out))
        elif ok:
            print("%s: PASS" % name)
        else:
            failed += 1
            print("%s: FAIL\n%s" % (name, out.strip()[-3000:]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(tuple(sys.argv[1:])))
