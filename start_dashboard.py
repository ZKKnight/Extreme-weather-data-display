from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def find_pids_on_port(port: int) -> set[int]:
    if os.name == "nt":
        return find_pids_on_port_windows(port)
    return find_pids_on_port_unix(port)


def find_pids_on_port_windows(port: int) -> set[int]:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[int] = set()
    marker = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        state = parts[3]
        pid = parts[4]
        if local_address.endswith(marker) and state.upper() == "LISTENING":
            try:
                pids.add(int(pid))
            except ValueError:
                pass
    return pids


def find_pids_on_port_unix(port: int) -> set[int]:
    commands = [
        ["lsof", "-ti", f"tcp:{port}"],
        ["fuser", f"{port}/tcp"],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            pids = set()
            for token in result.stdout.split():
                try:
                    pids.add(int(token))
                except ValueError:
                    pass
            return pids
    return set()


def stop_pids(pids: set[int]) -> None:
    current_pid = os.getpid()
    for pid in sorted(pids):
        if pid == current_pid:
            continue
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            subprocess.run(["kill", "-TERM", str(pid)], check=False)


def wait_for_port_free(port: int, timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not find_pids_on_port(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Port {port} is still in use after cleanup.")


def wait_for_server(host: str, port: int, timeout_s: float = 15.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"Dashboard did not start at http://{host}:{port}.")


def start_dashboard(host: str, port: int) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_web.py"),
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restart and open the extreme weather dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Start the server without opening a browser.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pids = find_pids_on_port(args.port)
    if pids:
        print(f"Stopping existing process(es) on port {args.port}: {', '.join(map(str, sorted(pids)))}")
        stop_pids(pids)
        wait_for_port_free(args.port)

    process = start_dashboard(args.host, args.port)
    wait_for_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}"
    print(f"Dashboard running at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    print("Press Ctrl+C here to stop the dashboard.")
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()


if __name__ == "__main__":
    main()
