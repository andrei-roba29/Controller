#!/usr/bin/env python3
"""PadLink PC agent.

Turns your phone's touch input into a virtual DualShock 4 on this Windows PC.

Two transports:

  python agent.py           Relay mode. Joins a Supabase Realtime room, so the
                            phone can be anywhere (the PWA is hosted on Netlify
                            and the PC only makes *outbound* connections - no
                            port forwarding, no firewall rules).

  python agent.py --lan     Local mode. Runs a tiny web server on your Wi-Fi and
                            serves the same PWA itself. Lowest latency, works
                            with no internet at all, but phone and PC must be on
                            the same network.

Needs the ViGEmBus driver, which the vgamepad installer offers to set up.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets
import socket
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import quote

from pad import Pad, new_pin, new_room_code

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
VERSION = "1.1.0"
DEFAULT_REALTIME = "https://ljvafmdhcpxbtstaljqb.supabase.co"
HEARTBEAT_EVERY = 24.0
PC_ALIVE_EVERY = 2.0
INPUT_TIMEOUT = 1.2


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg = {"supabaseUrl": DEFAULT_REALTIME, "supabaseAnonKey": "", "siteUrl": ""}
    try:
        cfg.update(json.loads((WEB / "config.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


class Session:
    """Tracks what the phone is doing so we only print useful lines."""

    def __init__(self, pad: Pad):
        self.pad = pad
        self.idle_since = time.monotonic()
        self.phone_here = False

    def input(self, msg: dict | None) -> None:
        if msg is None:
            self.pad.apply(None)
            if self.phone_here:
                self.phone_here = False
                print("Phone idle - controller released.", flush=True)
            return
        if not self.phone_here:
            self.phone_here = True
            print("Phone connected.", flush=True)
        self.pad.apply(msg)


# --------------------------------------------------------------------------- #
# relay mode (Supabase Realtime, Phoenix protocol)
# --------------------------------------------------------------------------- #
class Relay:
    def __init__(self, base_url: str, api_key: str, room: str, session: Session,
                 verbose: bool = False):
        self.ws_base = (base_url.rstrip("/")
                        .replace("https://", "wss://", 1)
                        .replace("http://", "ws://", 1))
        self.api_key = api_key
        self.room = room
        self.topic = f"realtime:padlink:{room}"
        self.session = session
        self.verbose = verbose
        self._ref = 0
        self._join_ref = None

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                await self._session()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the agent alive
                self.session.pad.reset()
                print(f"  disconnected ({type(exc).__name__}: {exc}); reconnecting in {backoff}s",
                      flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)

    async def _session(self) -> None:
        import websockets

        url = f"{self.ws_base}/realtime/v1/websocket?apikey={quote(self.api_key)}&vsn=1.0.0"
        async with websockets.connect(url, max_size=4 << 20, ping_interval=20,
                                      ping_timeout=20) as ws:
            await self._join(ws)
            print(f"  joined room {self.room}", flush=True)
            tasks = [asyncio.create_task(self._reader(ws)),
                     asyncio.create_task(self._keepalive(ws))]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()

    async def _join(self, ws) -> None:
        ref = self._next_ref()
        self._join_ref = ref
        await ws.send(json.dumps({
            "topic": self.topic,
            "event": "phx_join",
            "payload": {
                "config": {
                    "broadcast": {"ack": False, "self": False},
                    "presence": {"key": ""},
                    "postgres_changes": [],
                    "private": True,
                },
                "access_token": self.api_key,
            },
            "ref": ref,
            "join_ref": ref,
        }))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            msg = json.loads(raw)
            if self.verbose:
                print(f"  <- {raw[:240]}", flush=True)
            if msg.get("event") == "phx_reply" and msg.get("ref") == ref:
                payload = msg.get("payload") or {}
                if payload.get("status") == "ok":
                    return
                raise RuntimeError(
                    "room rejected: " + json.dumps(payload)[:400] +
                    "\n  If this says 'Unauthorized', the Realtime policies in "
                    "supabase.sql are missing on your project."
                )

    def _frame(self, event: str, payload: dict) -> str:
        return json.dumps({
            "topic": self.topic,
            "event": "broadcast",
            "payload": {"type": "broadcast", "event": event, "payload": payload},
            "ref": self._next_ref(),
            "join_ref": self._join_ref,
        })

    async def _reader(self, ws) -> None:
        last_input = 0.0
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.4)
            except asyncio.TimeoutError:
                if last_input and time.monotonic() - last_input > INPUT_TIMEOUT:
                    last_input = 0.0
                    self.session.input(None)
                continue
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "broadcast":
                body = msg.get("payload") or {}
                if body.get("event") == "input":
                    last_input = time.monotonic()
                    self.session.input(body.get("payload") or {})
            elif event == "phx_reply":
                payload = msg.get("payload") or {}
                if payload.get("status") != "ok":
                    print(f"  broadcast rejected: {json.dumps(payload)[:300]}", flush=True)
            elif event in ("phx_error", "phx_close"):
                raise ConnectionError(event)
            if self.verbose:
                print(f"  <- {raw[:240]}", flush=True)

    async def _keepalive(self, ws) -> None:
        last_heartbeat = time.monotonic()
        while True:
            await asyncio.sleep(PC_ALIVE_EVERY)
            await ws.send(self._frame("pc-alive", {}))
            if time.monotonic() - last_heartbeat >= HEARTBEAT_EVERY:
                last_heartbeat = time.monotonic()
                await ws.send(json.dumps({"topic": "phoenix", "event": "heartbeat",
                                          "payload": {}, "ref": self._next_ref()}))


# --------------------------------------------------------------------------- #
# local (LAN) mode
# --------------------------------------------------------------------------- #
HOST_PAGE = """<!doctype html><meta charset=utf-8><title>PadLink</title>
<body style="font-family:system-ui;background:#16181f;color:#e8eaf0;text-align:center;padding:40px">
<h1>PadLink</h1><p>On your phone (same Wi-Fi), scan the code or open:</p>
<p style="font-size:22px">{url}</p><div id=qr style="background:#fff;display:inline-block;padding:12px;border-radius:8px"></div>
<p>Pairing PIN</p><p style="font:700 56px ui-monospace,monospace;letter-spacing:.2em;margin:0">{pin}</p>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script>try{{new QRCode(document.getElementById("qr"),{{text:"{url}#{pin}",width:200,height:200}})}}catch(e){{document.getElementById("qr").remove()}}</script>"""


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def run_lan(args, session: Session, pin: str) -> None:
    from aiohttp import WSMsgType, web

    scheme = "https" if (args.cert and args.key) else "http"
    url = f"{scheme}://{local_ip()}:{args.port}"
    print("\n==============================")
    print(f"  Open on your phone: {url}")
    print(f"  Pairing PIN:        {pin}")
    print(f"  Or open on this PC: {scheme}://localhost:{args.port}/host")
    print("==============================\n", flush=True)

    active = {"ws": None}

    async def ws_handler(request):
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)
        if pin and not secrets.compare_digest(request.query.get("pin", ""), pin):
            await ws.close(code=4001, message=b"bad pin")
            return ws
        if active["ws"] and not active["ws"].closed:
            await active["ws"].close(code=4002, message=b"replaced")
        active["ws"] = ws
        print("Phone connected:", request.remote, flush=True)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    session.input(json.loads(msg.data))
        finally:
            if active["ws"] is ws:
                session.input(None)
                print("Phone disconnected", flush=True)
        return ws

    async def host(request):
        if request.remote not in ("127.0.0.1", "::1"):
            raise web.HTTPForbidden()
        return web.Response(text=HOST_PAGE.format(url=url, pin=pin), content_type="text/html")

    async def health(request):
        return web.json_response({"app": "padlink", "mode": "lan"})

    app = web.Application()
    app.add_routes([
        web.get("/ws", ws_handler),
        web.get("/host", host),
        web.get("/health", health),
        web.get("/", lambda r: web.FileResponse(WEB / "index.html")),
    ])
    app.router.add_static("/", WEB)

    ctx = None
    if args.cert and args.key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(args.cert, args.key)
    try:
        web.run_app(app, host="0.0.0.0", port=args.port, ssl_context=ctx, print=None)
    except OSError as exc:
        print("Could not start the server:", exc, flush=True)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def banner(lines: list[str]) -> None:
    width = max(len(line) for line in lines) + 4
    print("\n" + "=" * width)
    for line in lines:
        print("  " + line)
    print("=" * width + "\n", flush=True)


def print_code_block(room: str, site: str) -> None:
    """Printed before anything can fail, so the code is always on screen."""
    lines = [f"PadLink {VERSION}", f"Room code:  {room}"]
    if site:
        lines.append(f"Open:       {site.rstrip('/')}/#{room}")
    else:
        lines.append("Open the PadLink site on your phone and type this code.")
    banner(lines)


def _probe_realtime(base: str, key: str) -> tuple[bool, str]:
    import websockets

    url = (base.rstrip("/").replace("https://", "wss://", 1)
           .replace("http://", "ws://", 1))
    url = f"{url}/realtime/v1/websocket?apikey={quote(key)}&vsn=1.0.0"

    async def probe() -> None:
        async with websockets.connect(url, open_timeout=8) as ws:
            await ws.close()

    try:
        asyncio.run(probe())
        return True, "reachable"
    except Exception as exc:  # noqa: BLE001
        return False, f"unreachable ({type(exc).__name__})"


def run_check(cfg: dict, args) -> int:
    """`--check`: a printable report of everything PadLink needs."""
    import importlib

    rows: list[tuple[str, str, bool]] = []

    v = sys.version_info
    rows.append(("Python", f"{v.major}.{v.minor}.{v.micro} (need 3.10+)", v >= (3, 10)))

    for module in ("aiohttp", "websockets", "vgamepad"):
        try:
            importlib.import_module(module)
            rows.append((module, "installed", True))
        except Exception as exc:  # noqa: BLE001
            rows.append((module, f"missing ({type(exc).__name__})", False))

    if sys.platform == "win32":
        import subprocess

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            out = subprocess.run(["sc", "query", "ViGEmBus"], capture_output=True,
                                 text=True, creationflags=flags).stdout.upper()
        except OSError:
            out = ""
        driver = "RUNNING" in out
        rows.append(("ViGEmBus driver", "running" if driver else "not installed", driver))
    else:
        rows.append(("ViGEmBus driver", "n/a (Windows only)", True))

    key = args.api_key or cfg.get("supabaseAnonKey") or ""
    base = args.realtime_url or cfg.get("supabaseUrl") or DEFAULT_REALTIME
    if key:
        ok, detail = _probe_realtime(base, key)
        rows.append(("Supabase relay", f"{detail} - {base}", ok))
    else:
        rows.append(("Supabase relay", "no anon key in web/config.json", False))

    width = max(len(row[0]) for row in rows) + 2
    print(f"\nPadLink check (agent {VERSION})\n")
    for label, value, ok in rows:
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {label:<{width}}{value}")

    failed = [row for row in rows if not row[2]]
    print()
    if not failed:
        print("  All good. Run .\\start-padlink.cmd to play.", flush=True)
        return 0
    print("  Fix the FAIL lines above, then run .\\start-padlink.cmd --check again.", flush=True)
    if any(row[0] == "ViGEmBus driver" and not row[2] for row in failed):
        print("  ViGEmBus: https://github.com/nefarius/ViGEmBus/releases "
              "(run the .msi, then reboot)", flush=True)
    return 1


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="PadLink PC agent")
    parser.add_argument("--lan", action="store_true",
                        help="serve the PWA over your Wi-Fi instead of using Supabase")
    parser.add_argument("--room", help="fixed 8-character room code (default: random each run)")
    parser.add_argument("--pin", help="fixed LAN pairing PIN (default: random each run)")
    parser.add_argument("--port", type=int, default=8765, help="LAN mode port (default 8765)")
    parser.add_argument("--cert", help="LAN mode: TLS certificate for HTTPS")
    parser.add_argument("--key", help="LAN mode: TLS private key for HTTPS")
    parser.add_argument("--site", help="public URL of the PWA, printed with the room code")
    parser.add_argument("--realtime-url", default=None, help="override the Supabase project URL")
    parser.add_argument("--api-key", default=None, help="override the Supabase anon key")
    parser.add_argument("--check", action="store_true",
                        help="check Python, dependencies, driver and relay, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="don't touch vgamepad, just print the input state")
    parser.add_argument("--verbose", action="store_true", help="log every websocket frame")
    args = parser.parse_args()

    if args.check:
        raise SystemExit(run_check(cfg, args))

    site = args.site or cfg.get("siteUrl") or ""

    if args.lan:
        session_pad = None
        try:
            session_pad = Pad(dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print("Could not create the virtual controller:", exc, flush=True)
            print("Install the ViGEmBus driver: "
                  "https://github.com/nefarius/ViGEmBus/releases", flush=True)
            raise SystemExit(1)
        run_lan(args, Session(session_pad), args.pin or new_pin())
        return

    room = (args.room or new_room_code()).upper()
    if not re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{8}", room):
        print(f"\"{room}\" is not a valid room code: it needs 8 characters from 0-9 and\n"
              "A-Z, excluding I, L, O and U (they are easy to mix up).", flush=True)
        raise SystemExit(1)

    # The code goes on screen before anything else can fail.
    print_code_block(room, site)

    try:
        pad = Pad(dry_run=args.dry_run)
        print(f"  Virtual controller: {'dry run (no driver needed)' if args.dry_run else 'ready'}",
              flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  Virtual controller: FAILED - {type(exc).__name__}: {exc}", flush=True)
        print("\nThe ViGEmBus driver is missing, so Windows has no virtual controller.\n"
              "  1. Download it:  https://github.com/nefarius/ViGEmBus/releases\n"
              "  2. Run ViGEmBus_*_x64.msi, then reboot Windows\n"
              "  3. Confirm with: .\\start-padlink.cmd --check\n"
              "\nTo test the phone side without the driver: "
              ".\\start-padlink.cmd --dry-run", flush=True)
        raise SystemExit(1)

    session = Session(pad)
    api_key = args.api_key or cfg.get("supabaseAnonKey") or ""
    if not api_key:
        print("  Relay:              FAILED - no anon key in web/config.json", flush=True)
        raise SystemExit(1)

    print("  Relay:              connecting...", flush=True)
    relay = Relay(args.realtime_url or cfg.get("supabaseUrl") or DEFAULT_REALTIME,
                  api_key, room, session, verbose=args.verbose)
    try:
        asyncio.run(relay.run())
    except KeyboardInterrupt:
        pass
    finally:
        pad.reset()
        print("Stopped.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
