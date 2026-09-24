#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
Dubber AI Pro Studio - Windows Launcher & Application Manager
====================================================================
Author: Dubber AI Team
Platform: Windows (Compatible with Linux/macOS)

Features:
- Starts Streamlit Web App (app.py) listening on 0.0.0.0 for phone access
- Automatically discovers local Wi-Fi / LAN IP for mobile browser testing
- Auto-starts Cloudflare Tunnel (cloudflared.exe) & detects public HTTPS URL
- Polls Streamlit health endpoint and auto-launches default web browser
- Clean process lifecycle management (graceful Ctrl+C shutdown)
====================================================================
"""

import argparse
import atexit
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# If executed directly by Streamlit (e.g., Streamlit Community Cloud with main file 'main.py')
try:
    import streamlit as st
    if hasattr(st, "runtime") and st.runtime.exists():
        import runpy
        _app_target = Path(__file__).resolve().parent / "app.py"
        runpy.run_path(str(_app_target), run_name="__main__")
        sys.exit(0)
except Exception:
    pass

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("Dubber AI Pro Studio - Windows Host")
        kernel32 = ctypes.windll.kernel32
        h_stdout = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h_stdout, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass

# Color codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_RED = "\033[91m"
C_DIM = "\033[2m"

BASE_DIR = Path(__file__).resolve().parent
APP_SCRIPT = BASE_DIR / "app.py"
CLOUDFLARED_BIN = BASE_DIR / "cloudflared.exe"
FFMPEG_BIN = BASE_DIR / "ffmpeg.exe"

streamlit_proc = None
tunnel_proc = None
public_tunnel_url = None
shutdown_requested = False


def print_banner():
    banner = f"""
{C_CYAN}{C_BOLD}╔══════════════════════════════════════════════════════════════════╗
║               🎬 DUBBER AI PRO STUDIO (WINDOWS)                  ║
║      Speech Transcription • Khmer Translation • Video Studio     ║
╚══════════════════════════════════════════════════════════════════╝{C_RESET}
"""
    print(banner)


def get_local_ip() -> str:
    """Detect LAN / Wi-Fi IP address for phone connection on local network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def verify_prerequisites():
    """Verify essential project files exist before running."""
    if not APP_SCRIPT.exists():
        print(f"{C_RED}[!] Error: Could not find '{APP_SCRIPT.name}' in {BASE_DIR}{C_RESET}")
        sys.exit(1)

    # Check ffmpeg
    if FFMPEG_BIN.exists():
        print(f"{C_GREEN}✓ Local FFmpeg engine detected:{C_RESET} {FFMPEG_BIN.name}")
    else:
        # Check system PATH
        try:
            res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"{C_GREEN}✓ System FFmpeg detected on PATH{C_RESET}")
            else:
                print(f"{C_YELLOW}⚠ Warning: ffmpeg not detected. Video dubbing may fail.{C_RESET}")
        except Exception:
            print(f"{C_YELLOW}⚠ Warning: ffmpeg not found in directory or PATH.{C_RESET}")


def monitor_tunnel_output(proc):
    """Background reader thread to extract public trycloudflare.com URL."""
    global public_tunnel_url
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    try:
        for line in iter(proc.stderr.readline, ""):
            if not line:
                break
            match = url_pattern.search(line)
            if match:
                public_tunnel_url = match.group(0)
                print(f"\n{C_GREEN}{C_BOLD}🌐 [Cloudflare Tunnel Connected!]{C_RESET}")
                print(f"   👉 Public Phone URL: {C_CYAN}{C_BOLD}{public_tunnel_url}{C_RESET}\n")
    except Exception:
        pass


def is_server_healthy(port: int) -> bool:
    """Check Streamlit's internal health endpoint."""
    try:
        url = f"http://127.0.0.1:{port}/_stcore/health"
        req = urllib.request.Request(url, headers={"User-Agent": "DubberLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def wait_for_server(port: int, max_seconds: int = 25) -> bool:
    """Poll Streamlit until it responds to health requests."""
    start_time = time.time()
    while time.time() - start_time < max_seconds:
        if is_server_healthy(port):
            return True
        time.sleep(0.5)
    return False


def cleanup():
    """Cleanly terminate all spawned subprocesses on shutdown."""
    global shutdown_requested, streamlit_proc, tunnel_proc
    if shutdown_requested:
        return
    shutdown_requested = True

    print(f"\n{C_YELLOW}[*] Shutting down Dubber AI Studio processes...{C_RESET}")

    # Terminate Cloudflare Tunnel
    if tunnel_proc and tunnel_proc.poll() is None:
        try:
            tunnel_proc.terminate()
            tunnel_proc.wait(timeout=2)
        except Exception:
            try:
                tunnel_proc.kill()
            except Exception:
                pass

    # Terminate Streamlit App
    if streamlit_proc and streamlit_proc.poll() is None:
        try:
            streamlit_proc.terminate()
            streamlit_proc.wait(timeout=3)
        except Exception:
            try:
                streamlit_proc.kill()
            except Exception:
                pass

    print(f"{C_GREEN}✓ All processes stopped cleanly. Goodbye!{C_RESET}")


def signal_handler(signum, frame):
    cleanup()
    sys.exit(0)


def main():
    global streamlit_proc, tunnel_proc

    parser = argparse.ArgumentParser(
        description="Dubber AI Pro Studio - Windows Launcher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8501, help="Port for Streamlit server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--no-tunnel", action="store_true", help="Disable Cloudflare Tunnel")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open default browser")
    args = parser.parse_args()

    # Register exit handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)

    print_banner()
    verify_prerequisites()

    local_ip = get_local_ip()
    local_pc_url = f"http://localhost:{args.port}"
    phone_wifi_url = f"http://{local_ip}:{args.port}"

    print(f"\n{C_BOLD}🚀 Starting Streamlit Web Engine...{C_RESET}")
    st_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_SCRIPT),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
        "--server.maxUploadSize",
        "1024",
        "--browser.gatherUsageStats",
        "false",
        "--server.headless",
        "true",
    ]

    st_env = os.environ.copy()
    st_env["PYTHONUTF8"] = "1"
    st_env["PYTHONIOENCODING"] = "utf-8"

    try:
        streamlit_proc = subprocess.Popen(
            st_cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=st_env,
        )
    except Exception as e:
        print(f"{C_RED}[!] Failed to launch Streamlit: {e}{C_RESET}")
        sys.exit(1)

    # Optional: Start Cloudflare Tunnel
    use_tunnel = not args.no_tunnel and CLOUDFLARED_BIN.exists()
    if use_tunnel:
        print(f"{C_BOLD}🌐 Launching Cloudflare Tunnel for Remote Mobile Access...{C_RESET}")
        tunnel_cmd = [
            str(CLOUDFLARED_BIN),
            "tunnel",
            "--url",
            f"http://localhost:{args.port}",
        ]
        try:
            tunnel_proc = subprocess.Popen(
                tunnel_cmd,
                cwd=str(BASE_DIR),
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            tunnel_thread = threading.Thread(
                target=monitor_tunnel_output,
                args=(tunnel_proc,),
                daemon=True,
            )
            tunnel_thread.start()
        except Exception as e:
            print(f"{C_YELLOW}⚠ Could not start Cloudflare tunnel: {e}{C_RESET}")
    elif not CLOUDFLARED_BIN.exists() and not args.no_tunnel:
        print(f"{C_DIM}ℹ cloudflared.exe not found in directory. Running local & LAN mode only.{C_RESET}")

    # Wait for Streamlit server to boot
    print(f"{C_DIM}⏳ Waiting for Streamlit server to initialize...{C_RESET}")
    if wait_for_server(args.port):
        print(f"{C_GREEN}✓ Streamlit server is active and healthy!{C_RESET}")
    else:
        print(f"{C_YELLOW}⚠ Streamlit is taking longer than usual to start, continuing...{C_RESET}")

    # Display clean summary box
    summary = f"""
{C_CYAN}┌──────────────────────────────────────────────────────────────────┐
│  {C_BOLD}🌟 Dubber AI Pro Studio is Live!{C_RESET}{C_CYAN}                                │
│                                                                  │
│  💻 Local PC URL:      {C_GREEN}{C_BOLD}{local_pc_url:<41}{C_RESET}{C_CYAN} │
│  📱 Phone (Same Wi-Fi):{C_BLUE}{C_BOLD}{phone_wifi_url:<41}{C_RESET}{C_CYAN} │
│                                                                  │
│  ⌨️  Press {C_YELLOW}{C_BOLD}Ctrl+C{C_RESET}{C_CYAN} in this window to stop all services           │
└──────────────────────────────────────────────────────────────────┘{C_RESET}
"""
    print(summary)

    # Open browser automatically if desired
    if not args.no_browser:
        try:
            print(f"{C_DIM}Opening default browser to {local_pc_url}...{C_RESET}")
            webbrowser.open(local_pc_url)
        except Exception:
            pass

    # Stream Streamlit output in main thread or wait
    try:
        while streamlit_proc.poll() is None:
            line = streamlit_proc.stdout.readline()
            if line:
                # Optionally filter noisy logs or print cleanly
                if "error" in line.lower() or "exception" in line.lower():
                    print(f"{C_RED}[Streamlit Error]{C_RESET} {line.strip()}")
                elif "ready to watch" in line.lower() or "dubbing" in line.lower():
                    print(f"{C_CYAN}[Streamlit]{C_RESET} {line.strip()}")
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
