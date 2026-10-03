"""`kinloom bundle`: Kinloom as a program that needs no Python, for engines that are not Python (Godot, Unity,
Unreal...): the game starts `kinloom-server/kinloom serve` itself, the player installs nothing.

    kinloom bundle [--out kinloom-server]

Builds with PyInstaller (a build tool, fetched by `uvx` when it is not installed; never a dependency of the package),
for this machine's system only (build on each system you ship to). The folder holds the program, kinloom.json and a
README for the game. The model is still the developer's choice: an API key in the player's environment, or an online
server (`kinloom deploy`); a coding agent's subscription is the developer's own, not the players'.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ENTRY = "from kinloom.cli import main\nraise SystemExit(main())\n"
README = """Kinloom for this game ({system})

kinloom{ext} serve --quiet --port 7717     starts the server the game talks to (Godot's Kinloom addon starts it by
                                          itself when this folder sits next to the game or in the project)
kinloom{ext} doctor                       what it found: model, key, voice

The model: an API key in the environment of whoever runs the game (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY
+ KINLOOM_MODEL, ...), or point the game at an online server (kinloom deploy). Without one, characters answer with the
game's own lines (offline).
Built with Kinloom {version} by `kinloom bundle` for {system}; build again on each system you ship to.
"""


def _package_root():
    """The folder that holds the kinloom package (src/), to build from."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pyinstaller_command():
    """How to run PyInstaller here: installed, or through uvx. None when neither is available."""
    try:
        import PyInstaller  # noqa: F401
        return [sys.executable, "-m", "PyInstaller"]
    except ImportError:
        pass
    uvx = shutil.which("uvx")
    return [uvx, "--from", "pyinstaller", "pyinstaller"] if uvx else None


def _replaceable(target, folder):
    """None when target may be (re)written, else why not: it is replaced as a whole, so it must be a bundle already
    (never the game's folder, one of its parents, or a folder with other files)."""
    game = os.path.abspath(folder)
    if os.path.normcase(target) == os.path.normcase(game) or os.path.normcase(game).startswith(os.path.normcase(target) + os.sep):
        return "%s holds the game: choose another --out" % target
    if not os.path.exists(target):
        return None
    if not os.path.isdir(target):
        return "%s is a file: choose another --out" % target
    readme = os.path.join(target, "README.txt")
    try:
        with open(readme, encoding="utf-8") as f:
            ours = f.read(40).startswith("Kinloom for this game")
    except OSError:
        ours = False
    if ours or not os.listdir(target):
        return None
    return "%s exists and is not a Kinloom bundle: nothing was changed (choose another --out, or remove it)" % target


def build(folder=".", out="kinloom-server", run=subprocess.run):
    """Builds the program into folder/out. Returns (exit code, message)."""
    from . import __version__
    target = os.path.abspath(os.path.join(folder, out))
    refused = _replaceable(target, folder)
    if refused:
        return 2, "error: " + refused
    cmd = pyinstaller_command()
    if cmd is None:
        return 2, "PyInstaller is needed to build: pip install pyinstaller (or install uv: uvx fetches it)"
    work = tempfile.mkdtemp(prefix="kinloom-bundle-")
    try:
        entry = os.path.join(work, "kinloom_main.py")
        with open(entry, "w", encoding="utf-8") as f:
            f.write(ENTRY)
        args = cmd + ["--noconfirm", "--clean", "--onedir", "--console", "--name", "kinloom",
                      "--distpath", os.path.join(work, "dist"), "--workpath", os.path.join(work, "build"),
                      "--specpath", work, "--paths", _package_root(), "--collect-data", "kinloom",
                      "--collect-submodules", "kinloom", entry]
        r = run(args, capture_output=True, text=True, timeout=1800)
        built = os.path.join(work, "dist", "kinloom")
        if r.returncode != 0 or not os.path.isdir(built):
            return 1, "PyInstaller failed:\n" + ((r.stderr or "") + (r.stdout or ""))[-3000:]
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(built, target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(target, ".gdignore"), "w", encoding="utf-8") as f:
        f.write("")                       # Godot: a program, not game resources (the editor would scan its files)
    config = os.path.join(folder, "kinloom.json")
    if os.path.exists(config):
        shutil.copy2(config, os.path.join(target, "kinloom.json"))
    system = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    ext = ".exe" if os.name == "nt" else ""
    with open(os.path.join(target, "README.txt"), "w", encoding="utf-8") as f:
        f.write(README.format(ext=ext, version=__version__, system=system))
    return 0, "built %s (%s): %s serve --quiet starts it; README.txt says how the game uses it" % (
        target, system, os.path.join(out, "kinloom" + ext))
