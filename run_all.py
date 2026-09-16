#!/usr/bin/env python3
# run_all.py - 跨平台一键启动：llama.cpp / PyTorch + Cloudflare Tunnel
import os
import re
import sys
import time
import signal
import argparse
import subprocess
from shutil import which

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")
BUILD_DIR = os.path.join(SCRIPT_DIR, "build")
LEGACY_DIR = os.path.join(SCRIPT_DIR, "legacy")
IS_WINDOWS = sys.platform.startswith("win")

CF_TOKEN_DIR = os.path.join(os.path.expanduser("~"), ".shaoyu")
CF_TOKEN_PATH = os.path.join(CF_TOKEN_DIR, "cloudflare_token")
CF_DOMAIN_PATH = os.path.join(CF_TOKEN_DIR, "cloudflare_domain")

processes = []

LLAMA_MODEL_CHOICES = [
    ("shaoyu-q4_k_m.gguf", "Q4_K_M", "量化, 约 22MB, ~200 t/s, 推荐"),
    ("shaoyu-f16.gguf",    "F16",    "未量化, 约 66MB, ~130 t/s"),
]


def log(tag, msg):
    print(f"[{tag}] {msg}", flush=True)


def find_exe(name):
    exe = which(name)
    if exe:
        return exe
    if IS_WINDOWS:
        exe = which(name + ".exe")
        if exe:
            return exe
    return None


def kill_existing():
    if IS_WINDOWS:
        for proc in ("llama-server.exe", "llama-server", "cloudflared.exe", "cloudflared"):
            subprocess.call(
                ["taskkill", "/F", "/IM", proc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return

    if which("sv"):
        subprocess.call(["sv", "down", "cloudflared"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if which("sv-disable"):
        subprocess.call(["sv-disable", "cloudflared"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for pat in ("llama-server", "api_wrapper.py", "legacy/app.py", "app.py",
                "cloudflared tunnel"):
        subprocess.call(["pkill", "-f", pat],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def spawn(cmd, cwd, log_path, tag, env=None):
    log("run", f"[{tag}] " + " ".join(cmd))
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    kwargs = {"cwd": cwd, "stdout": log_file, "stderr": subprocess.STDOUT}
    if env is not None:
        kwargs["env"] = env
    if not IS_WINDOWS:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(cmd, **kwargs)
    processes.append((p, log_file))
    return p


def shutdown(signum=None, frame=None):
    log("stop", "正在关闭所有子进程...")
    for p, log_file in processes:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    for p, log_file in processes:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        try:
            log_file.close()
        except Exception:
            pass
    log("stop", "已退出")
    sys.exit(0)


def status():
    if IS_WINDOWS:
        subprocess.call('tasklist | findstr /I "llama python cloudflared"', shell=True)
        return
    for name in ("llama-server", "api_wrapper.py", "legacy/app.py", "app.py", "cloudflared"):
        print(f"=== {name} ===")
        subprocess.call(["pgrep", "-af", name])
    print()


def _list_gguf_models():
    if not os.path.isdir(MODELS_DIR):
        return []
    return sorted(f for f in os.listdir(MODELS_DIR) if f.endswith(".gguf"))


# ==================== Cloudflare 凭据 ====================
def cf_load_token():
    if os.path.isfile(CF_TOKEN_PATH):
        try:
            with open(CF_TOKEN_PATH, encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                return t
        except Exception:
            pass
    return None


def cf_save_token(token):
    os.makedirs(CF_TOKEN_DIR, exist_ok=True)
    with open(CF_TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(token)
    try:
        os.chmod(CF_TOKEN_PATH, 0o600)
    except Exception:
        pass


def cf_forget_token():
    if os.path.isfile(CF_TOKEN_PATH):
        os.remove(CF_TOKEN_PATH)
        return True
    return False


def cf_load_domain():
    if os.path.isfile(CF_DOMAIN_PATH):
        try:
            with open(CF_DOMAIN_PATH, encoding="utf-8") as f:
                d = f.read().strip()
            if d:
                return d
        except Exception:
            pass
    return None


def cf_save_domain(domain):
    os.makedirs(CF_TOKEN_DIR, exist_ok=True)
    with open(CF_DOMAIN_PATH, "w", encoding="utf-8") as f:
        f.write(domain)
    try:
        os.chmod(CF_DOMAIN_PATH, 0o600)
    except Exception:
        pass


def cf_forget_domain():
    if os.path.isfile(CF_DOMAIN_PATH):
        os.remove(CF_DOMAIN_PATH)
        return True
    return False


def cf_prompt_token():
    print()
    print("  输入 Cloudflare Tunnel Token")
    print("  获取: https://one.dash.cloudflare.com/ -> Networks -> Tunnels")
    print()
    try:
        t = input("  Token: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not t:
        return None
    cf_save_token(t)
    print(f"  Token 已保存到 {CF_TOKEN_PATH}")
    return t


def cf_prompt_domain():
    saved = cf_load_domain()
    if saved:
        print()
        print(f"  已保存的域名: {saved}")
        try:
            c = input("  直接回车使用，或输入新域名: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not c:
            return saved
        domain = c
    else:
        print()
        print("  输入公网域名（在 Cloudflare Dashboard 配置的 Public Hostname）")
        print("  例如: https://shaoyu.example.com")
        print()
        try:
            domain = input("  域名: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

    if not domain:
        return None
    if not domain.startswith("http://") and not domain.startswith("https://"):
        domain = "https://" + domain
    domain = domain.rstrip("/")
    cf_save_domain(domain)
    print(f"  域名已保存: {CF_DOMAIN_PATH}")
    return domain


# ==================== 交互式 ====================
def interactive_choose_backend(args):
    print()
    print("  === 选择推理后端 ===")
    print()
    print("    [1] llama.cpp   (GGUF, ~200 t/s, 推荐)")
    print("    [2] PyTorch     (原始 .pth, ~15 t/s, 兼容性好)")
    print()
    while True:
        try:
            c = input("  请输入 [1/2] (默认 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if c in ("", "1"):
            return "llama"
        if c == "2":
            return "pytorch"
        print("  无效输入，请重新输入")


def interactive_choose_model(args):
    if args.model is not None:
        return args.model

    available = _list_gguf_models()
    if not available:
        print()
        print(f"  {MODELS_DIR} 下没有 .gguf 文件")
        sys.exit(1)

    presets = [(f, name, desc) for f, name, desc in LLAMA_MODEL_CHOICES if f in available]
    preset_files = {f for f, _, _ in presets}
    extras = [(f, f, "自定义模型") for f in available if f not in preset_files]
    choices = presets + extras

    print()
    print("  === 选择模型精度 ===")
    print()
    for i, (f, name, desc) in enumerate(choices, 1):
        print(f"    [{i}] {name:<10s} {desc}")
    print()
    while True:
        try:
            c = input(f"  请输入 [1-{len(choices)}] (默认 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not c:
            return choices[0][0]
        try:
            idx = int(c)
            if 1 <= idx <= len(choices):
                return choices[idx - 1][0]
        except ValueError:
            pass
        print("  无效输入，请重新输入")


def interactive_choose_tunnel():
    print()
    print("  === Cloudflare Tunnel ===")
    print()
    print("    [1] 不启用      仅本地/局域网访问")
    print("    [2] 临时隧道    trycloudflare.com 随机域名，无需账号")
    print("    [3] 正式隧道    需要 Token + 公网域名")
    print()

    if cf_load_token():
        print(f"    检测到已保存的 Token ({CF_TOKEN_PATH})")
    if cf_load_domain():
        print(f"    检测到已保存的域名 ({cf_load_domain()})")
    if cf_load_token() or cf_load_domain():
        print()

    while True:
        try:
            c = input("  请输入 [1/2/3] (默认 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not c or c == "1":
            return None
        if c == "2":
            return "quick"
        if c == "3":
            return "named"
        print("  无效输入，请重新输入")


# ==================== llama.cpp 后端 ====================
def start_llama(args):
    llama_server = find_exe("llama-server")
    if not llama_server:
        print("找不到 llama-server")
        print("   Termux: pkg install llama-cpp")
        sys.exit(1)

    model_path = os.path.join(MODELS_DIR, args.model)
    if not os.path.isfile(model_path):
        print(f"找不到模型文件: {model_path}")
        sys.exit(1)

    if not os.path.isfile(os.path.join(BUILD_DIR, "index.html")):
        log("warn", f"{BUILD_DIR}/index.html 不存在，前端会显示错误页")

    llama_log = os.path.join(SCRIPT_DIR, "llama-server.log")
    spawn(
        [
            llama_server,
            "-m", model_path,
            "--alias", "shaoyu",
            "--host", "127.0.0.1",
            "--port", str(args.backend_port),
            "-c", str(args.ctx_size),
            "--no-webui",
        ],
        cwd=SCRIPT_DIR, log_path=llama_log, tag="llama",
    )
    log("llama", f"PID 已启动，日志: {llama_log}")
    log("llama", "等待模型加载 (~4 秒)...")
    time.sleep(4)

    wrapper_log = os.path.join(SCRIPT_DIR, "api_wrapper.log")
    spawn(
        [
            sys.executable, "-u",
            os.path.join(SCRIPT_DIR, "api_wrapper.py"),
            "--host", args.host,
            "--port", str(args.port),
            "--upstream", f"http://127.0.0.1:{args.backend_port}",
            "--static", BUILD_DIR,
        ],
        cwd=SCRIPT_DIR, log_path=wrapper_log, tag="wrapper",
    )
    log("wrapper", f"PID 已启动，日志: {wrapper_log}")
    time.sleep(2)


# ==================== PyTorch 后端 ====================
def start_pytorch(args):
    app_py = None
    for c in [os.path.join(SCRIPT_DIR, "app.py"),
              os.path.join(LEGACY_DIR, "app.py")]:
        if os.path.isfile(c):
            app_py = c
            break

    if not app_py:
        print("找不到 app.py")
        sys.exit(1)

    app_dir = os.path.dirname(app_py)
    for f in ["model_loader.py", "model_minimind.py"]:
        if not os.path.isfile(os.path.join(app_dir, f)):
            print(f"缺少文件: {f}（在 {app_dir}）")
            sys.exit(1)

    candidates = [
        os.path.join(app_dir, "full_sft_512.pth"),
        os.path.join(MODELS_DIR, "full_sft_512.pth"),
    ]
    if not any(os.path.isfile(p) for p in candidates):
        print("找不到 full_sft_512.pth")
        sys.exit(1)

    if not os.path.isdir(os.path.join(app_dir, "tokenizer")):
        print("找不到 tokenizer 目录")
        sys.exit(1)

    env = os.environ.copy()
    env["SHAOYU_HOST"] = args.host
    env["SHAOYU_PORT"] = str(args.port)

    flask_log = os.path.join(SCRIPT_DIR, "flask.log")
    spawn([sys.executable, "-u", "app.py"],
          cwd=app_dir, log_path=flask_log, tag="flask", env=env)
    log("flask", f"PID 已启动，日志: {flask_log}")
    log("flask", "等待模型加载 (~5 秒)...")
    time.sleep(5)


# ==================== Cloudflare Tunnel ====================
def cf_wait_quick_url(log_path, timeout=30):
    # 只匹配真正分配的 URL，排除 api.trycloudflare.com
    pattern = re.compile(r"https://(?!api\.)([a-z0-9-]+\.trycloudflare\.com)")
    start = time.time()
    while time.time() - start < timeout:
        if os.path.isfile(log_path):
            try:
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                # 优先从 "Your quick Tunnel has been created" 之后找
                idx = content.find("Your quick Tunnel has been created")
                search = content[idx:] if idx >= 0 else content
                m = pattern.search(search)
                if m:
                    return m.group(0)
            except Exception:
                pass
        time.sleep(1)
    return None


def start_cloudflared(mode, target_port, args):
    cf = find_exe("cloudflared")
    if not cf:
        print()
        print("找不到 cloudflared")
        print("   Termux:  pkg install cloudflared")
        print("   其他系统: https://github.com/cloudflare/cloudflared/releases")
        return None

    cf_log = os.path.join(SCRIPT_DIR, "cloudflared.log")
    target = f"http://127.0.0.1:{target_port}"

    if mode == "quick":
        for attempt in range(1, 4):
            log("cf", f"Quick Tunnel 尝试 {attempt}/3 ...")
            p = spawn([cf, "tunnel", "--url", target, "--no-autoupdate"],
                      cwd=SCRIPT_DIR, log_path=cf_log, tag="cf")
            log("cf", f"PID 已启动，日志: {cf_log}")
            log("cf", "等待 Cloudflare 分配域名（约 5~30 秒）...")

            url = cf_wait_quick_url(cf_log, timeout=30)

            if p.poll() is not None:
                log("cf", f"第 {attempt} 次失败，cloudflared 已退出")
                try:
                    with open(cf_log, encoding="utf-8", errors="replace") as f:
                        tail = f.read()[-400:]
                    log("cf", f"最后日志: {tail}")
                except Exception:
                    pass
                if attempt < 3:
                    log("cf", "3 秒后重试...")
                    time.sleep(3)
                    open(cf_log, "w").close()
                    processes[:] = [(pp, lf) for pp, lf in processes if pp is not p]
                    continue
                log("cf", "3 次都失败，跳过隧道，仅本地可用")
                return None
            else:
                if url:
                    return url
                url = cf_wait_quick_url(cf_log, timeout=20)
                if url:
                    return url
                log("cf", "进程在运行但未拿到 URL")
                return None
        return None

    elif mode == "named":
        token = args.tunnel_token or cf_load_token()
        if not token:
            token = cf_prompt_token()
        if not token:
            print("  未提供 Token，跳过 Tunnel")
            return None

        domain = args.public_url or cf_load_domain()
        if not domain:
            domain = cf_prompt_domain()
        if not domain:
            print("  未提供公网域名，仅启动 Tunnel")

        spawn([cf, "tunnel", "--no-autoupdate", "run", "--token", token],
              cwd=SCRIPT_DIR, log_path=cf_log, tag="cf")
        log("cf", f"PID 已启动，日志: {cf_log}")
        log("cf", "Tunnel 建立中（域名由 Dashboard 配置决定，本地无法探测）")
        time.sleep(2)
        return domain

    return None


# ==================== 主流程 ====================
def main():
    parser = argparse.ArgumentParser(description="ShaoyuLM 一键启动")
    parser.add_argument("--backend", default="auto",
                        choices=["auto", "llama", "pytorch"])
    parser.add_argument("--model", default=None,
                        help="GGUF 文件名（相对 models/）")
    parser.add_argument("--tunnel", default="auto",
                        choices=["auto", "none", "quick", "named"])
    parser.add_argument("--tunnel-token", default=None)
    parser.add_argument("--public-url", default=None)
    parser.add_argument("--forget-token", action="store_true")
    parser.add_argument("--forget-domain", action="store_true")
    parser.add_argument("--forget-all", action="store_true")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--backend-port", type=int, default=9000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-kill", action="store_true")
    parser.add_argument("--package", action="store_true",
                        help="完整打包（q4_k_m + f16 + pth）后退出")
    parser.add_argument("--package-lite", action="store_true",
                        help="精简打包（仅 q4_k_m）")
    parser.add_argument("--package-no-models", action="store_true",
                        help="打包时不包含模型")
    parser.add_argument("--package-output", default="ShaoyuLM.zip",
                        help="打包输出文件名")
    args = parser.parse_args()

    if args.forget_all:
        t = cf_forget_token()
        d = cf_forget_domain()
        print(f"{'已删除' if t else '无'} Token")
        print(f"{'已删除' if d else '无'} 域名")
        return
    if args.forget_token:
        print("已删除 Token" if cf_forget_token() else "没有保存的 Token")
        return
    if args.forget_domain:
        print("已删除域名" if cf_forget_domain() else "没有保存的域名")
        return
    if args.package or args.package_lite or args.package_no_models:
        cmd = [sys.executable,
               os.path.join(SCRIPT_DIR, "tools", "package.py"),
               "--output", args.package_output]
        if args.package_no_models:
            cmd.append("--no-models")
        elif args.package_lite:
            cmd.append("--lite")
        print("=" * 60)
        print("  📦 ShaoyuLM 打包")
        print("=" * 60)
        rc = subprocess.call(cmd, cwd=SCRIPT_DIR)
        sys.exit(rc)

    if args.status:
        status()
        return
    if args.stop:
        kill_existing()
        log("stop", "已停止所有旧进程")
        return

    is_tty = sys.stdin.isatty()

    if args.backend == "auto":
        backend = interactive_choose_backend(args) if is_tty else "llama"
    else:
        backend = args.backend

    if backend == "llama":
        model = interactive_choose_model(args) if is_tty else (args.model or LLAMA_MODEL_CHOICES[0][0])
    else:
        model = None
    args.model = model

    if args.tunnel == "auto":
        tunnel_mode = interactive_choose_tunnel() if is_tty else None
    elif args.tunnel == "none":
        tunnel_mode = None
    else:
        tunnel_mode = args.tunnel

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if not args.no_kill:
        log("init", "清理旧进程...")
        kill_existing()
        time.sleep(1)

    backend_label = {"llama": "llama.cpp (GGUF)", "pytorch": "PyTorch (.pth)"}[backend]

    print()
    print("=" * 60)
    print("  ShaoyuLM 一键启动")
    print("=" * 60)
    print(f"  后端:        {backend_label}")
    print(f"  对外端口:    {args.port}")
    if backend == "llama":
        print(f"  模型:        models/{args.model}")
        print(f"  内部端口:    {args.backend_port}")
    else:
        print(f"  模型:        full_sft_512.pth")
    if tunnel_mode:
        print(f"  Tunnel:      {tunnel_mode}")
    print("=" * 60)

    if backend == "llama":
        start_llama(args)
    else:
        start_pytorch(args)

    public_url = None
    if tunnel_mode:
        public_url = start_cloudflared(tunnel_mode, args.port, args)

    print()
    print("=" * 60)
    print("  全部就绪")
    print("=" * 60)
    print(f"  前端页面:      http://127.0.0.1:{args.port}")
    print(f"  Base URL:      http://127.0.0.1:{args.port}/v1")
    print(f"  模型名:        shaoyu")
    print(f"  局域网 Base:   http://<本机IP>:{args.port}/v1")
    if public_url:
        print()
        print(f"  公网 URL:      {public_url}")
        print(f"  公网 Base:     {public_url.rstrip('/')}/v1")
    print()
    logs = "llama-server.log api_wrapper.log" if backend == "llama" else "flask.log"
    if tunnel_mode:
        logs += " cloudflared.log"
    print(f"  日志:  tail -f {logs}")
    print(f"  停止:  python run_all.py --stop")
    print(f"  状态:  python run_all.py --status")
    if cf_load_token() or cf_load_domain():
        print(f"  忘记凭据: python run_all.py --forget-all")
    print("=" * 60)
    print("  Ctrl+C 停止所有服务")
    print("=" * 60)

    try:
        while True:
            for p, _ in processes:
                rc = p.poll()
                if rc is not None:
                    log("main", f"子进程退出 (exit={rc})，关闭所有")
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
