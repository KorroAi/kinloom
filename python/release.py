"""One zip per engine for a GitHub release, for developers who do not use Python: python release.py [out_dir].

unity  com.kinloom.sdk/ (a UPM package: Packages/ or Assets/)    godot  addons/kinloom/ (unzip at the project root)
web    kinloom/kinloom.js, .ts, .d.ts, kinloom-talk.js           csharp, cpp, rust, java, lua: kinloom/ (the one file)
Each zip carries the LICENSE; local build output (obj/, bin/, target/) is never included.
"""
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENTS = os.path.join(HERE, "src", "kinloom", "clients")
LICENSE = os.path.join(HERE, "LICENSE")
SKIP = {"obj", "bin", "target", "node_modules", "__pycache__"}

# engine -> (folder under clients/, the folder inside the zip, files to take: None = the whole folder)
ZIPS = {
    "unity": ("csharp", "com.kinloom.sdk", None),
    "godot": (os.path.join("godot", "addons", "kinloom"), "addons/kinloom", None),
    "web": ("web", "kinloom", ["kinloom.js", "kinloom.ts", "kinloom.d.ts", "kinloom-talk.js", "package.json"]),
    "csharp": ("csharp", "kinloom", ["Kinloom.cs", "Kinloom.csproj"]),
    "cpp": ("cpp", "kinloom", ["kinloom.hpp"]),
    "rust": ("rust", "kinloom", ["kinloom.rs", "lib.rs", "Cargo.toml"]),
    "java": ("java", "kinloom", ["Kinloom.java"]),
    "lua": ("lua", "kinloom", None),
}


def version():
    text = open(os.path.join(HERE, "src", "kinloom", "__init__.py"), encoding="utf-8").read()
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def _files(src, only):
    if only is not None:
        return [(os.path.join(src, f), f) for f in only]
    out = []
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for f in sorted(files):
            if f.endswith(".pyc"):
                continue
            path = os.path.join(root, f)
            out.append((path, os.path.relpath(path, src).replace(os.sep, "/")))
    return out


def build(out_dir):
    """Writes the zips into out_dir; returns their paths."""
    os.makedirs(out_dir, exist_ok=True)
    v = version()
    paths = []
    for engine, (folder, prefix, only) in ZIPS.items():
        path = os.path.join(out_dir, "kinloom-%s-%s.zip" % (engine, v))
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for src, rel in _files(os.path.join(CLIENTS, folder), only):
                z.write(src, prefix + "/" + rel)
            z.write(LICENSE, prefix + "/LICENSE")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "dist")):
        print(p)
