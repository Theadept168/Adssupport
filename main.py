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
                try:
                    import json
                    url_cfg = BASE_DIR / "app_url.json"
                    token_url = f"{public_tunnel_url}/?device=VGhlYToxMjEyMTI.5580befe1b89338853e31248"
                    url_cfg.write_text(json.dumps({
                        "app_name": "Dubber AI Pro Studio",
                        "url": token_url,
                        "base_url": public_tunnel_url,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }, indent=2), encoding="utf-8")
                except Exception:
                    pass
    except Exception:
        pass


def free_port(port: int):
    """Terminate any lingering processes listening on the target port to prevent port conflicts."""
    if sys.platform != "win32":
        return
    my_pid = os.getpid()
    try:
        res = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        target_pids = set()
        for line in res.stdout.splitlines():
            if f":{port}" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid_str = parts[-1]
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        if pid != my_pid and pid > 0:
                            target_pids.add(pid)
        for pid in target_pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                pass
    except Exception:
        pass


def is_server_healthy(port: int) -> bool:
    """Check Streamlit's internal health endpoint with generous timeout under high load."""
    try:
        url = f"http://127.0.0.1:{port}/_stcore/health"
        req = urllib.request.Request(url, headers={"User-Agent": "DubberLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=10.0) as response:
            return response.status == 200
    except Exception:
        return False


def wait_for_server(port: int, max_seconds: int = 35) -> bool:
    """Poll Streamlit until it responds to health requests."""
    start_time = time.time()
    while time.time() - start_time < max_seconds:
        if is_server_healthy(port):
            return True
        time.sleep(0.5)
    return False


def stream_process_output(proc, stop_event: threading.Event):
    """Background reader thread to stream process stdout to console in real-time."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line or stop_event.is_set():
                break
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if "error" in lower or "exception" in lower or "traceback" in lower:
                print(f"{C_RED}[Streamlit Error]{C_RESET} {stripped}")
            elif "ready to watch" in lower or "dubbing" in lower or "http" in lower:
                print(f"{C_CYAN}[Streamlit]{C_RESET} {stripped}")
            elif "warning" in lower:
                print(f"{C_YELLOW}[Streamlit Warn]{C_RESET} {stripped}")
            else:
                print(f"{C_DIM}[Streamlit]{C_RESET} {stripped}")
    except Exception:
        pass


def launch_streamlit(args, st_env) -> subprocess.Popen:
    """Free port and launch Streamlit as a subprocess with high concurrency tuning."""
    free_port(args.port)
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
        "2048",
        "--server.maxMessageSize",
        "500",
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
        "--server.headless",
        "true",
    ]
    return subprocess.Popen(
        st_cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=st_env,
    )


def launch_tunnel(args) -> subprocess.Popen:
    """Launch Cloudflare tunnel subprocess."""
    if args.no_tunnel or not CLOUDFLARED_BIN.exists():
        return None
    tunnel_cmd = [
        str(CLOUDFLARED_BIN),
        "tunnel",
        "--url",
        f"http://localhost:{args.port}",
    ]
    try:
        proc = subprocess.Popen(
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
            args=(proc,),
            daemon=True,
        )
        tunnel_thread.start()
        return proc
    except Exception as e:
        print(f"{C_YELLOW}⚠ Could not start Cloudflare tunnel: {e}{C_RESET}")
        return None


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
    global streamlit_proc, tunnel_proc, shutdown_requested

    parser = argparse.ArgumentParser(
        description="Dubber AI Pro Studio - Windows Launcher with Auto-Reboot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8501, help="Port for Streamlit server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--no-tunnel", action="store_true", help="Disable Cloudflare Tunnel")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open default browser")
    parser.add_argument(
        "--no-auto-restart",
        action="store_false",
        dest="auto_restart",
        default=True,
        help="Disable automatic server reboot when an error or crash occurs",
    )
    parser.add_argument(
        "--restart-delay",
        type=int,
        default=3,
        help="Cooldown seconds before auto-rebooting after an error",
    )
    parser.add_argument(
        "--no-health-check",
        action="store_false",
        dest="health_check",
        default=True,
        help="Disable periodic health check watchdog",
    )
    parser.add_argument(
        "--health-interval",
        type=int,
        default=30,
        help="Seconds between health check pings (default: 30s to allow heavy jobs)",
    )
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

    st_env = os.environ.copy()
    st_env["PYTHONUTF8"] = "1"
    st_env["PYTHONIOENCODING"] = "utf-8"

    summary = f"""
{C_CYAN}┌──────────────────────────────────────────────────────────────────┐
│  {C_BOLD}🌟 Dubber AI Pro Studio is Live! [Auto-Reboot Active]{C_RESET}{C_CYAN}         │
│                                                                  │
│  💻 Local PC URL:      {C_GREEN}{C_BOLD}{local_pc_url:<41}{C_RESET}{C_CYAN} │
│  📱 Phone (Same Wi-Fi):{C_BLUE}{C_BOLD}{phone_wifi_url:<41}{C_RESET}{C_CYAN} │
│  🛡️ Auto-Reboot:       {C_GREEN}{C_BOLD}Enabled (restarts on error/crash){C_RESET}{C_CYAN}       │
│                                                                  │
│  ⌨️  Press {C_YELLOW}{C_BOLD}Ctrl+C{C_RESET}{C_CYAN} in this window to stop all services           │
└──────────────────────────────────────────────────────────────────┘{C_RESET}
"""

    reboot_count = 0
    browser_opened = False
    use_tunnel = not args.no_tunnel and CLOUDFLARED_BIN.exists()

    # Initial tunnel launch
    if use_tunnel:
        print(f"{C_BOLD}🌐 Launching Cloudflare Tunnel for Remote Mobile Access...{C_RESET}")
        tunnel_proc = launch_tunnel(args)
    elif not CLOUDFLARED_BIN.exists() and not args.no_tunnel:
        print(f"{C_DIM}ℹ cloudflared.exe not found in directory. Running local & LAN mode only.{C_RESET}")

    # Supervisor Loop: handles initial start and auto-reboots on crash/error
    while not shutdown_requested:
        if reboot_count == 0:
            print(f"\n{C_BOLD}🚀 Starting Streamlit Web Engine...{C_RESET}")
        else:
            print(f"\n{C_BOLD}🔄 [AUTO-REBOOT #{reboot_count}] Restarting Streamlit Web Engine...{C_RESET}")

        try:
            streamlit_proc = launch_streamlit(args, st_env)
        except Exception as e:
            print(f"{C_RED}[!] Failed to launch Streamlit: {e}{C_RESET}")
            if not args.auto_restart:
                sys.exit(1)
            time.sleep(args.restart_delay)
            reboot_count += 1
            continue

        stop_stream_event = threading.Event()
        stream_thread = threading.Thread(
            target=stream_process_output,
            args=(streamlit_proc, stop_stream_event),
            daemon=True,
        )
        stream_thread.start()

        # Wait for Streamlit server to boot
        print(f"{C_DIM}⏳ Waiting for Streamlit server to initialize...{C_RESET}")
        if wait_for_server(args.port):
            if reboot_count == 0:
                print(f"{C_GREEN}✓ Streamlit server is active and healthy!{C_RESET}")
            else:
                print(f"{C_GREEN}{C_BOLD}✓ [AUTO-REBOOT #{reboot_count}] Streamlit successfully recovered and back online!{C_RESET}")
        else:
            print(f"{C_YELLOW}⚠ Streamlit is taking longer than usual to start, continuing...{C_RESET}")

        # Show banner on first successful start
        if reboot_count == 0:
            print(summary)
            if not args.no_browser and not browser_opened:
                try:
                    print(f"{C_DIM}Opening default browser to {local_pc_url}...{C_RESET}")
                    webbrowser.open(local_pc_url)
                    browser_opened = True
                except Exception:
                    pass

        # Supervise the running instance & periodic health watchdog
        last_health_check = time.time()
        consecutive_health_failures = 0

        try:
            while not shutdown_requested:
                # 1. Check if process terminated (crashed or encountered unhandled error)
                exit_code = streamlit_proc.poll()
                if exit_code is not None:
                    stop_stream_event.set()
                    if shutdown_requested:
                        break

                    reboot_count += 1
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    print(f"\n{C_RED}{C_BOLD}╔══════════════════════════════════════════════════════════════════╗{C_RESET}")
                    print(f"{C_RED}{C_BOLD}║ ⚠️  SERVER ERROR: Streamlit process exited unexpectedly!        ║{C_RESET}")
                    print(f"{C_RED}{C_BOLD}║ Time: {timestamp} | Exit Code: {exit_code:<5}                        ║{C_RESET}")

                    if not args.auto_restart:
                        print(f"{C_YELLOW}║ Auto-reboot is disabled (--no-auto-restart). Exiting.          ║{C_RESET}")
                        print(f"{C_RED}{C_BOLD}╚══════════════════════════════════════════════════════════════════╝{C_RESET}\n")
                        return

                    print(f"{C_YELLOW}{C_BOLD}║ 🔄 AUTO-REBOOT: Restarting in {args.restart_delay}s... (Attempt #{reboot_count:<3})             ║{C_RESET}")
                    print(f"{C_RED}{C_BOLD}╚══════════════════════════════════════════════════════════════════╝{C_RESET}\n")

                    # Wait cooldown
                    for _ in range(args.restart_delay * 2):
                        if shutdown_requested:
                            break
                        time.sleep(0.5)

                    if shutdown_requested:
                        break

                    # Release port before restarting
                    free_port(args.port)

                    # Also check if tunnel needs restart
                    if use_tunnel and (tunnel_proc is None or tunnel_proc.poll() is not None):
                        print(f"{C_CYAN}[Auto-Reboot] Restarting Cloudflare Tunnel...{C_RESET}")
                        tunnel_proc = launch_tunnel(args)

                    break  # Break inner loop to restart streamlit in supervisor loop

                # 2. Watchdog: check health periodically
                now = time.time()
                if args.health_check and (now - last_health_check) >= args.health_interval:
                    last_health_check = now
                    if not is_server_healthy(args.port):
                        consecutive_health_failures += 1
                        if consecutive_health_failures >= 5:
                            reboot_count += 1
                            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                            print(f"\n{C_RED}[AUTO-REBOOT {timestamp}] ⚠️ Server unresponsive (5 consecutive health checks failed). Force-rebooting...{C_RESET}")
                            stop_stream_event.set()
                            try:
                                streamlit_proc.terminate()
                                streamlit_proc.wait(timeout=3)
                            except Exception:
                                try:
                                    streamlit_proc.kill()
                                except Exception:
                                    pass
                            free_port(args.port)
                            break
                    else:
                        consecutive_health_failures = 0

                # 3. Tunnel health check
                if use_tunnel and (tunnel_proc is None or tunnel_proc.poll() is not None) and not shutdown_requested:
                    print(f"{C_YELLOW}[!] Cloudflare tunnel dropped. Reconnecting tunnel...{C_RESET}")
                    tunnel_proc = launch_tunnel(args)

                time.sleep(0.5)

        except KeyboardInterrupt:
            shutdown_requested = True
            break

    cleanup()


if __name__ == "__main__":
    main()

