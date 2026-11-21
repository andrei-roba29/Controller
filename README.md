# PadLink

Use your phone as a PS4 (DualShock 4) controller on your Windows PC — including
from outside your home network.

```
 phone (PWA on Netlify) ──► Supabase Realtime ──► agent.py on the PC ──► virtual DS4
```

The phone shows a controller. Every input is broadcast to a room; the agent on
your PC listens in that room and drives a virtual DualShock 4 with
[vgamepad](https://github.com/yannbouteiller/vgamepad). The PC only makes
**outbound** connections: no port forwarding, no router config, no firewall
rules, no Netlify server.

## Why a plain Netlify deploy does not work

Netlify hosts static files and short-lived functions. PadLink needs a long-lived
process that owns a Windows kernel driver and a virtual gamepad, so the PC has to
be the thing driving the controller. Netlify's job here is only to serve the
phone app (the files in `web/`); Supabase is the wire between the two.

## One-time setup

### 1. PC — the agent

1. Windows 10/11, Python 3.10 or newer.
2. Install the **ViGEmBus driver**: https://github.com/nefarius/ViGEmBus/releases
   (download the `ViGEmBus_*_x64.msi`, run it, reboot). Without it Windows has no
   virtual-controller support and the agent will tell you so on startup.
3. Run **`start-padlink.cmd`** (double-click it, or in a terminal:
   `.\start-padlink.cmd`). First run creates `.venv` and installs `aiohttp`,
   `websockets` and `vgamepad`.

> **In PowerShell, keep the `.\` prefix.** Windows only runs programs from the
> current folder when you say so, otherwise it reports *"The term
> 'start-padlink.cmd' is not recognized"*. So `.\start-padlink.cmd --check`,
> not `start-padlink.cmd --check`. The prefix works in `cmd.exe` too.

The window prints a room code:

```
==============================
  PadLink is running
  Room code:  K7M2QX9P
==============================
```

Keep it open while you play. `Ctrl+C` stops it.

### 2. Netlify — the phone app

1. Netlify → **Add new site → Import an existing project → GitHub →
   `andrei-roba29/Controller`**.
2. Build command: leave empty. Publish directory: `web` (already set in
   `netlify.toml`, so the defaults are fine). Deploy.

That is all Netlify needs — it never runs Python.

### 3. Pair

Open the Netlify URL on the phone, type the room code, tap **Connect**, rotate to
landscape. The code is remembered per device.

You can also share a direct link: `https://your-site.netlify.app/#K7M2QX9P`.

## Local Wi-Fi mode (optional, lower latency)

If phone and PC are on the same network you can skip Supabase entirely:

```
.\start-padlink.cmd --lan
```

The agent serves the same app from your PC on port 8765 and prints a LAN URL and
a 6-digit PIN. The page detects it is talking to the agent directly and switches
to the WebSocket transport automatically.

## Handy flags

| Flag | Effect |
| --- | --- |
| `--room K7M2QX9P` | Fixed room code instead of a fresh one per run |
| `--site https://your-site.netlify.app` | Print a ready-to-open pairing link |
| `--lan` | Local Wi-Fi mode instead of the relay |
| `--pin 123456` | Fixed LAN PIN |
| `--check` | Report on Python, dependencies, the ViGEmBus driver and the relay |
| `--dry-run` | Don't touch vgamepad, just print input (works on any OS) |
| `--verbose` | Log every websocket frame |

## How much latency / traffic

Input is capped at 20 messages per second per phone, and only when something
changes — an idle controller sends nothing but a 0.5 msg/s keepalive from the PC.
Expect roughly an extra 40–90 ms on top of whatever your phone and PC already
have to the internet. Fine for most games; not for rhythm games or fighting-game
tournaments. Use `--lan` when you want the lowest number.

Supabase's free tier includes 2M Realtime messages/month, which is roughly 25–30
hours of active play.

## Security

- The anon key in `web/config.js` is public by design. RLS policies
  (`supabase.sql`) restrict it to topics named `padlink:<8 chars>`, so it cannot
  touch anything else in the Supabase project.
- The room code is 8 Crockford-base32 characters (~40 bits) and is regenerated on
  every run unless you pass `--room`.
- Anyone who learns the room code can drive the pad. Treat it like a PIN — it is
  visible only in your terminal, and only while the agent runs.
- The agent only reads gamepad input; it never exposes your PC to the network.

## Updating

The agent prints its version (`PadLink 1.1.0`) in the startup box and in the
`--check` report, so you can always tell which build you are running.

- **Downloaded as a ZIP** (the folder is called `Controller-main`): GitHub will
  not update it for you. Download
  <https://github.com/andrei-roba29/Controller/archive/refs/heads/main.zip> and
  extract it over the same folder — `Expand-Archive Controller-main.zip -DestinationPath . -Force`
  from the parent folder. `.venv` is left alone, so the update is quick.
- **Cloned with git**: `git pull` in the folder, then re-run the launcher.

If a flag you read about is missing from `agent.py --help`, the copy is out of
date.

## Troubleshooting


**PowerShell: "The term 'start-padlink.cmd' is not recognized"** — PowerShell
does not run programs from the current folder. Prefix it:
`.\start-padlink.cmd --check`. Make sure the folder you are in actually contains
`agent.py` (`cd D:\Controller-main` after unzipping).

**No room code appears anywhere** — the agent prints the code as the very first
thing it does, so if you never saw it the window closed before starting. Run:

```
.\start-padlink.cmd --check
```

It reports Python, the three dependencies, the ViGEmBus driver and whether the
relay is reachable. Alternatively, open the PadLink site, tap
**"No code on your PC?" → "Create a code on this phone"**, then start the PC with
`.\start-padlink.cmd --room <CODE>`.

**The phone says "PC not responding"** — the agent is running but in a different
room: compare the codes, they are case-insensitive.

**`Could not create the virtual controller`** — the ViGEmBus driver is missing.
Install it from the link above and reboot.

**Page says "Relay error" / `room rejected ... Unauthorized`** — the Realtime
policies are missing on the Supabase project. Run `supabase.sql` in the SQL
editor (Dashboard → SQL Editor) for project `ljvafmdhcpxbtstaljqb`.

**Nothing happens when you press a button** — check the terminal: it prints
`Phone connected.` on the first input. If that never appears, the phone never
reached the room.

**"Install app" is not offered** — PWAs need HTTPS. The Netlify URL is HTTPS, so
install from there. LAN mode over plain `http://192.168.x.x` only gets a bookmark.

**Triggers are digital** — L2/R2 report full press only. Gyro, touchpad swipes and
rumble are not implemented.

## Files

| Path | What it is |
| --- | --- |
| `web/` | The phone app. This is what Netlify publishes. |
| `web/config.json` | Supabase project URL + public anon key. |
| `agent.py` | PC agent: relay mode (default) and LAN mode (`--lan`). |
| `pad.py` | DualShock 4 input mapping shared by both modes. |
| `supabase.sql` | Realtime RLS policies (already applied). |
| `start-padlink.cmd` | Windows launcher that sets up `.venv` and runs the agent (`.\start-padlink.cmd` in PowerShell). |
| `netlify.toml` | Tells Netlify to publish `web/`. |
