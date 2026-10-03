"""Runs the client conformance scenario against a real `kinloom serve` with a scripted model (no tokens spent).

    python clients/conformance/run.py            # every client whose runtime is installed (node, python)
Exit code 0 when every transcript matches expected.txt.
"""
import os
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CLI = os.path.join(REPO, "src", "Kinloom.Cli", "bin", "Debug", "net10.0", "kinloom.dll")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    if not os.path.exists(CLI):
        subprocess.run(["dotnet", "build", os.path.join(REPO, "src", "Kinloom.Cli"), "-v", "q", "-nologo"], check=True)
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("KINLOOM_") and k not in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
    env.update(KINLOOM_PROVIDER="scripted", KINLOOM_SCRIPT=os.path.join(HERE, "script.json"))
    server = subprocess.Popen(["dotnet", CLI, "serve", HERE, "--port", str(port), "--no-manifest"], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        expected = open(os.path.join(HERE, "expected.txt"), encoding="utf-8").read().strip()
        clients = []
        if shutil.which("node"):
            clients.append(("javascript", ["node", os.path.join(HERE, "scenario.mjs"), str(port)]))
        clients.append(("python", [sys.executable, os.path.join(HERE, "scenario.py"), str(port)]))
        ok = True
        for name, cmd in clients:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            got = r.stdout.strip().replace("\r\n", "\n")
            if got == expected:
                print(f"{name}: PASS")
            else:
                ok = False
                print(f"{name}: FAIL\n--- expected\n{expected}\n--- got\n{got}\n--- stderr\n{r.stderr[-2000:]}")
        return 0 if ok else 1
    finally:
        server.kill()


if __name__ == "__main__":
    sys.exit(main())
