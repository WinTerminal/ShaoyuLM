#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import urllib.request

LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "9000"))
API_PORT = int(os.environ.get("PORT", "8000"))

print(f"[start] llama-server on 127.0.0.1:{LLAMA_PORT}", flush=True)
llama = subprocess.Popen([
    "llama-server",
    "-m", "models/shaoyu-q4_k_m.gguf",
    "--alias", "shaoyu",
    "--host", "127.0.0.1",
    "--port", str(LLAMA_PORT),
    "-c", "1024",
    "--no-webui",
])

ready = False
for i in range(60):
    if llama.poll() is not None:
        print(f"[start] llama-server 退出 (code={llama.returncode})", flush=True)
        sys.exit(1)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=1)
        print(f"[start] llama-server ready ({i}s)", flush=True)
        ready = True
        break
    except Exception:
        time.sleep(1)

if not ready:
    print("[start] llama-server 60 秒内未 ready", flush=True)
    llama.terminate()
    sys.exit(1)

print(f"[start] api_wrapper on 0.0.0.0:{API_PORT}", flush=True)
wrapper = subprocess.Popen([
    sys.executable, "-u", "api_wrapper.py",
    "--host", "0.0.0.0",
    "--port", str(API_PORT),
    "--upstream", f"http://127.0.0.1:{LLAMA_PORT}",
    "--static", "build",
])

while True:
    if llama.poll() is not None:
        print(f"[start] llama-server 退出 (code={llama.returncode})", flush=True)
        wrapper.terminate()
        sys.exit(1)
    if wrapper.poll() is not None:
        print(f"[start] api_wrapper 退出 (code={wrapper.returncode})", flush=True)
        llama.terminate()
        sys.exit(1)
    time.sleep(1)
