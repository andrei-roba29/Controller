# PadLink

Use your phone as a configurable keyboard or PS4 (DualShock 4) controller on your Windows PC — including
from outside your home network.

```
 phone (PWA on Netlify) ──► Supabase Realtime ──► agent.py on the PC ──► virtual DS4
```

The phone shows a controller. Every input is broadcast to a room; the agent on
your PC listens in that room and sends keyboard input (default), or drives a virtual DualShock 4 with
[vgamepad](https://github.com/yannbouteiller/vgamepad). The PC only makes
**outbound** connections: no port forwarding, no router config, no firewall
rules, no Netlify server.

## Why a plain Netlify deploy does not work

Netlify hosts static files and short-lived functions. PadLink needs a long-lived
process that sends OS keyboard input or owns a virtual gamepad, so the PC has to
be the thing driving the controller. Netlify's job here is only to serve the
phone app (the files in `web/`); Supabase is the wire between the two.

## One-time setup

### 1. PC — the agent

1. Windows 10/11, Python 3.10 or newer.
2. **Optional, gamepad mode only:** install the **ViGEmBus driver**: https://github.com/nefarius/ViGEmBus/releases
   (download the `ViGEmBus_*_x64.msi`, run it, reboot). Keyboard mode does not require this driver.
3. Run **`start-padlink.cmd`** (double-click it, or in a terminal:
   `.\start-padlink.cmd`). First run creates `.venv` and installs `aiohttp`,
   `websockets`, `qrcode`, `pynput` and `vgamepad`.

> **In PowerShell, keep the `.\` prefix.** Windows only runs programs from the
> current folder when you say so, otherwise it reports *"The term
> 'start-padlink.cmd' is not recognized"*. So `.\start-padlink.cmd --check`,
> not `start-padlink.cmd --check`. The prefix works in `cmd.exe` too.

The launcher automatically opens the **PC pairing dashboard** at
<http://127.0.0.1:8765/host>. It shows the saved joining code and a QR code.
This PC screen is not the controller; scan its QR code using your phone.
The console also prints the room code:

```
==============================
  PadLink is running
  Room code:  K7M2QX9P
==============================
```

Keep the agent running while you play. `Ctrl+C` in its console stops it.
You can close the dashboard tab and reopen it at <http://127.0.0.1:8765/host>.
If the virtual-controller driver fails, the dashboard stays open with the code
and error instead of disappearing.

### Optional: launch automatically when Windows starts

Double-click **`enable-startup.cmd`** once. It installs the dependencies, creates
a per-user Windows Startup shortcut, and opens the agent/dashboard now. After
that, signing into Windows starts the agent in a minimized console automatically
and opens the joining dashboard in your default browser. Visit the PadLink website on the PC and click
**Open PC dashboard & joining code**, or bookmark <http://127.0.0.1:8765/host>.
No administrator access is needed for this shortcut (the driver may need it).
**If you enabled startup with an older version, run `enable-startup.cmd` again**
to replace the old shortcut that included `--no-browser`. Check Windows
Settings → Apps → Startup if Windows has disabled PadLink. Opening the hosted
website alone cannot start the local agent.

- Double-click **`disable-startup.cmd`** to remove automatic startup. This does
  not stop an already running agent; restore its console and press `Ctrl+C`.
- Keep the PadLink folder in place. If you move it, run `enable-startup.cmd`
  again to update the shortcut. It starts this local copy, not future downloads.
- You can always double-click `start-padlink.cmd` manually; PowerShell is optional.
- A browser cannot silently run a `.cmd` file or read a local `room.txt` file.
  The hosted PC page links to the local dashboard, which supplies the real code.
  If that link is unavailable, the agent is not running, or you used a different
  `--port` (in that case, open the dashboard URL printed by the agent).
- Already running? A second agent will not create another controller when the
  dashboard port is occupied. Use the existing dashboard instead.

### 2. Netlify — the phone app

1. Netlify → **Add new site → Import an existing project → GitHub →
   `andrei-roba29/Controller`**.
2. Build command: leave empty. Publish directory: `web` (already set in
   `netlify.toml`, so the defaults are fine). Deploy.

That is all Netlify needs — it never runs Python.

### 3. Pair

The agent prints a link and a QR code for the current room. **Scan it with the
phone camera** (or open the Netlify URL and type the code), tap **Connect**, then
turn the phone sideways.

The code is saved in `room.txt` next to `agent.py`, so it stays the same on every
run and your phone only has to be paired once. Use `--new-room` to rotate it, or
`--room CODE` to pin a specific one.

If the phone is held upright, the pairing screen still works — the "rotate to
landscape" prompt only appears once you are actually in the controller.

> The controller page lives on the **phone**. Opening it in the PC's browser also
> requires choosing **Use this computer anyway**; otherwise it shows PC pairing
> instructions. Driving the pad from the PC is usually not what
> you want. The PC shows the pairing dashboard, not the gamepad.

The link points at the address in `web/config.json` → `siteUrl`. Set it once to
your deployed site (already set for this repo) and every run prints a scannable
code. You can also pass it per run with `--site`.

Shareable link form: `https://your-site.netlify.app/#K7M2QX9P`.

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
| `--room K7M2QX9P` | Use this exact room code (not saved to `room.txt`) |
| `--new-room` | Forget the saved code and generate a fresh one |
| `--site https://your-site.netlify.app` | Print a ready-to-open pairing link |
| `--lan` | Local Wi-Fi mode instead of the relay |
| `--pin 123456` | Fixed LAN PIN |
| `--check` | Report on Python, dependencies, the ViGEmBus driver and the relay |
| `--dry-run` | Don't touch vgamepad, just print input (works on any OS) |
| `--no-browser` | Run the agent without opening the PC dashboard tab (used at sign-in) |
| `--port 8765` | Local PC dashboard / LAN server port |
| `--verbose` | Log every websocket frame |

## Browser games and keyboard settings

Many browser games accept keyboard input but do not support a DualShock 4.
In the **local PC dashboard** (`http://127.0.0.1:8765/host`), use **Input settings**:

1. Choose **Keyboard** (the default for new settings).
2. Choose a replacement key for every button and stick direction; Unassigned
   disables that control. Click **Save settings & release held inputs**.
3. **Click inside the game on the PC** so it receives keyboard focus. Then use
   the phone. Inputs go to the focused Windows app, not to a particular tab.

Defaults: left stick = WASD, D-pad = arrows, cross = Space, circle = E,
square = Q, triangle = R, Options = Enter. Settings persist in `settings.json`
in the agent folder. Keyboard mode uses `pynput`; run the updated launcher once
to install it. It needs no ViGEmBus driver. You can also tap **⚙ Settings** on the phone controller to load and save
these mappings over the paired connection (relay and LAN). Both phone and PC
must be updated. **Options** remains a game input (Enter by default), not the
settings menu. If Settings reports no PC reply, update/restart the PC agent and
check its dashboard. Anyone with the pairing code can change these mappings.

The dashboard reports the age of the last phone snapshot and currently held
keyboard keys. If snapshots arrive but a game ignores them, check focus and its
key bindings. Elevated apps, anti-cheat, and games that reject simulated input
may not work. Switch to **Virtual DualShock 4** only for gamepad-aware games;
this requires ViGEmBus. Windows `joy.cpl` can test that controller separately.

Do not leave a text editor, password field, or another sensitive app focused
while using keyboard mode. Closing/hiding the phone or a lost connection
releases held keys; Save also releases current input before applying mappings.

## How much latency / traffic

Stick movement is coalesced at 20 Hz; button edges send immediately. The phone
also refreshes its full input snapshot every 400 ms, so held keys/sticks do not
time out. The PC sends a 0.5 msg/s keepalive. Input stops and keys release after
about 1.2 seconds without phone snapshots.
Expect roughly an extra 40–90 ms on top of whatever your phone and PC already
have to the internet. Fine for most games; not for rhythm games or fighting-game
tournaments. Use `--lan` when you want the lowest number.

Supabase's free tier includes 2M Realtime messages/month, which is roughly 25–30
hours of active play.

## Security

- Keyboard mode injects the configured keys into the active Windows app. Anyone
  with the room code can send these inputs while the agent runs.

- The anon key in `web/config.json` is public by design. RLS policies
  (`supabase.sql`) restrict it to topics named `padlink:<8 chars>`, so it cannot
  touch anything else in the Supabase project.
- The room code is 8 Crockford-base32 characters (~40 bits), saved locally in
  `room.txt`. Rotate it with `--new-room` if someone else learns it.
- Anyone who learns the room code can drive the pad. Treat it like a PIN — it is
  visible in the local PC dashboard, terminal, and phone pairing link.
- In relay mode the dashboard binds only to loopback, rejects non-loopback Host
  headers, and does not enable cross-origin reads. The hosted website cannot
  fetch your joining code. No inbound LAN/firewall access is needed in relay mode.
- The agent accepts gamepad input; LAN mode explicitly exposes the app and
  gamepad WebSocket on your local network.

## Updating

The agent prints its version (`PadLink 1.6.0`) in the startup box and in the
`--check` report, so you can always tell which build you are running.

- **Downloaded as a ZIP** (the folder is called `Controller-main`): GitHub will
  not update it for you. Download
  <https://github.com/andrei-roba29/Controller/archive/refs/heads/main.zip> and
  extract it over the same folder — `Expand-Archive Controller-main.zip -DestinationPath . -Force`
  from the parent folder. `.venv` is left alone, so the update is quick.
- **Cloned with git**: `git pull` in the folder, then re-run the launcher.

If a flag you read about is missing from `agent.py --help`, the copy is out of
date.

## Diagnostics

If the phone never connects, open **`<your-site>/diag.html`** on the phone, type
the room code and read the result. It checks, in order: which build is deployed,
`config.json`, `relay.js`, whether the device can open a websocket to Supabase,
whether the room join is authorized, and whether the PC's keepalive arrives.

Every line is marked ✓ / ✗, and the summary at the top says which of those it
actually failed on — far more useful than "nothing happens".

## Troubleshooting



**PowerShell: "The term 'start-padlink.cmd' is not recognized"** — PowerShell
does not run programs from the current folder. Prefix it:
`.\start-padlink.cmd --check`. Make sure the folder you are in actually contains
`agent.py` (`cd D:\Controller-main` after unzipping).

**No code on the PC website** — click **Open PC dashboard & joining code**. The
hosted site cannot read local files; the dashboard is served by the running
agent. If unavailable, double-click `start-padlink.cmd`. For automatic sign-in
startup, double-click `enable-startup.cmd` once.

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
| `room.txt` | Saved room code, created on first run (not in git). |
| `start-padlink.cmd` | Windows launcher that sets up `.venv` and runs the agent (`.\start-padlink.cmd` in PowerShell). |
| `enable-startup.cmd` / `disable-startup.cmd` | Enable or remove per-user Windows sign-in startup. |
| `windows-startup.ps1` | Creates the minimized Startup shortcut; called by the setup scripts. |
| `web/host.html` | PC pairing dashboard served locally by the relay agent. |
| `netlify.toml` | Tells Netlify to publish `web/`. |

## Development checks

On a non-Windows machine, install `aiohttp`, `websockets`, and `qrcode` in a
virtual environment (no vgamepad needed for these tests), then run:

```
python -m unittest discover -s tests -v
node tests/test_web.cjs
```

Tests cover dashboard status/QR, driver failure visibility, loopback Host
validation, duplicate-agent protection, browser launch target, and desktop vs
phone pairing. Windows Startup shortcuts and real ViGEmBus/controller behavior
must be verified on Windows.

### Keyboard events arrive but browser games ignore letters

Version 1.6.0 sends letters and digits as Windows virtual-key events instead of
Unicode text injection, so browser games can see normal keydown/code events.
Restart the updated PC agent; a website-only deployment cannot update Windows
input handling. Keep Keyboard mode selected and click the game on the PC.
Try Notepad first with the left stick (WASD). If Notepad receives nothing,
check the dashboard input age and agent errors; if Notepad works but the game
doesn't, verify its bindings/focus and whether it blocks simulated input.

### Phone tap accuracy (web 1.6.1)

The controller now scales as a single layout inside the phone's safe area,
including when browser bars or orientation change. Settings, touchpad, face
buttons, and sticks have separate hit regions; pressed buttons no longer
shrink their hit boxes. Sticks retain the finger that started the gesture,
so a second touch cannot take over or release that stick.

Deploy the updated `web/` files and reload the phone page to receive this fix;
the PC agent does not need updating for this layout-only change.

Optional Linux Chromium regression checks (dependencies stay in ignored
`node_modules/`):

```
npm install --no-save --package-lock=false playwright @sparticuz/chromium
node tests/test_touch_layout.cjs
```

These check hit testing and non-overlap at nine landscape viewport sizes,
including actual touch taps on Triangle and Settings.

### Phone Settings says “No reply from PC”

This means a settings request was not answered, not that a mapping was saved.
The phone joins the relay independently of the PC, so the controller screen
alone is not proof that the PC agent is present.

On the **PC**, open `http://127.0.0.1:8765/host` and check its status and room
code. You can configure mappings directly under **Input settings** there while
troubleshooting. In agent 1.7.0 the dashboard and phone report the running agent
version; older agents may not report a version or settings capabilities.

If the website updated but the running PC agent did not, stop the existing
PadLink console with Ctrl+C, update the local folder, and double-click
`start-padlink.cmd` from that folder. An agent already running (including the
sign-in copy) keeps executing the old code until stopped; a second launcher
cannot replace it when its port is occupied. Check the Windows startup shortcut
if it points to an older folder. Do not open the loopback dashboard address on
the phone—it refers to the phone itself there.

From 1.7.0, an output initialization failure no longer prevents the PC joining
the relay: phone Settings remains available and shows the output error. Switch
to Keyboard if the gamepad driver is unavailable, or install the missing input
dependency using the updated launcher. Settings loads retry twice; saves never
automatically retry. If a save is unconfirmed, Reload to see whether it applied
before saving again.

## Mouse clicks and right-stick camera look (1.8.0)

Update **both the PC agent and website**, restart the old PC agent, and reload
the phone. On either settings screen:

1. Select **Keyboard + mouse**.
2. Map **Touchpad (click)** (or any other button, including R3) to **Mouse left
   click**, **Mouse right click**, or **Mouse middle click**. Holding that button
   holds the mouse button; releasing it or disconnecting releases the click.
3. For **Right stick**, select **Mouse look / camera pan**. Adjust speed
   (100–3000 pixels/second at full tilt) and optionally invert vertical look.
4. Save, then click inside the game on the **PC**. Some games need to capture
   the pointer (pointer lock) before moving the mouse controls the camera.

Right-stick mouse look sends continuous relative movement at roughly 60 Hz,
with a centre deadzone and speed proportional to tilt, even while the phone
sends an unchanged stick position. In this mode the four right-stick keyboard
mappings are ignored; R3 remains a separately mapped click/button. Choose
**Mapped direction keys** to return to the old behaviour. Existing settings
keep that behaviour until you explicitly enable mouse look.

The touchpad control here is a **click**, not a swipe surface or a physical
laptop touchpad gesture. This feature sends mouse-button events and relative
mouse movement; it does not emulate multi-finger trackpad gestures. Games that
require dragging can use a mapped held mouse button together with the stick.
Virtual-gamepad mode is unchanged and does not inject mouse movement/clicks.

Mouse input affects the active desktop, not a particular game window. Keep the
game focused; some elevated apps, raw-input games, or anti-cheat systems may
reject simulated input. Windows uses relative SendInput mouse events rather
than absolute cursor positioning; actual game compatibility still needs testing
on Windows.
