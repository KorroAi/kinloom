import importlib.util
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("release", os.path.join(HERE, "..", "release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_has_one_zip_per_engine_with_the_license_and_no_build_output(tmp_path):
    clients = os.path.join(HERE, "..", "src", "kinloom", "clients")
    junk = os.path.join(clients, "csharp", "obj", "junk.json")          # a local build left behind is never shipped
    os.makedirs(os.path.dirname(junk), exist_ok=True)
    made_junk = not os.path.exists(junk)
    if made_junk:
        with open(junk, "w") as f:
            f.write("{}")
    try:
        paths = release.build(str(tmp_path))
    finally:
        if made_junk:
            os.remove(junk)
    names = sorted(os.path.basename(p) for p in paths)
    v = release.version()
    assert names == sorted("kinloom-%s-%s.zip" % (e, v) for e in
                           ("unity", "godot", "web", "csharp", "cpp", "rust", "java", "lua"))
    for p in paths:
        with zipfile.ZipFile(p) as z:
            files = z.namelist()
            assert any(f.endswith("LICENSE") for f in files), p
            assert not any("/obj/" in f or "/bin/" in f or f.endswith(".pyc") for f in files), p
    unity = zipfile.ZipFile(os.path.join(str(tmp_path), "kinloom-unity-%s.zip" % v)).namelist()
    assert "com.kinloom.sdk/package.json" in unity and "com.kinloom.sdk/Kinloom.cs" in unity
    assert "com.kinloom.sdk/Unity/KinloomDialogue.cs" in unity
    godot = zipfile.ZipFile(os.path.join(str(tmp_path), "kinloom-godot-%s.zip" % v)).namelist()
    assert "addons/kinloom/plugin.cfg" in godot
    web = zipfile.ZipFile(os.path.join(str(tmp_path), "kinloom-web-%s.zip" % v)).namelist()
    assert {"kinloom/kinloom.js", "kinloom/kinloom.d.ts", "kinloom/kinloom-talk.js"} <= set(web)
    cpp = zipfile.ZipFile(os.path.join(str(tmp_path), "kinloom-cpp-%s.zip" % v)).namelist()
    assert "kinloom/kinloom.hpp" in cpp
