"""Shared DualShock 4 mapping for PadLink.

Only imported on the PC. ``--dry-run`` skips vgamepad entirely so the agent can
be tested on macOS/Linux (useful for debugging the relay without a controller).
"""
from __future__ import annotations

import json
import secrets

# Crockford base32, minus I/L/O/U: no ambiguous characters when read off a screen.
ROOM_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_room_code(length: int = 8) -> str:
    return "".join(secrets.choice(ROOM_ALPHABET) for _ in range(length))


def new_pin() -> str:
    return f"{secrets.randbelow(10 ** 6):06d}"


def clamp(value) -> int:
    return max(0, min(255, int(value)))


class Pad:
    """Virtual DualShock 4. ``apply`` mirrors the phone's full input state."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._active = False
        self._pad = None
        if dry_run:
            return
        import vgamepad as vg

        B, S, D = vg.DS4_BUTTONS, vg.DS4_SPECIAL_BUTTONS, vg.DS4_DPAD_DIRECTIONS
        self._buttons = {
            "cross": B.DS4_BUTTON_CROSS,
            "circle": B.DS4_BUTTON_CIRCLE,
            "square": B.DS4_BUTTON_SQUARE,
            "triangle": B.DS4_BUTTON_TRIANGLE,
            "l1": B.DS4_BUTTON_SHOULDER_LEFT,
            "r1": B.DS4_BUTTON_SHOULDER_RIGHT,
            "l2": B.DS4_BUTTON_TRIGGER_LEFT,
            "r2": B.DS4_BUTTON_TRIGGER_RIGHT,
            "share": B.DS4_BUTTON_SHARE,
            "options": B.DS4_BUTTON_OPTIONS,
            "l3": B.DS4_BUTTON_THUMB_LEFT,
            "r3": B.DS4_BUTTON_THUMB_RIGHT,
        }
        self._special = {
            "ps": S.DS4_SPECIAL_BUTTON_PS,
            "touchpad": S.DS4_SPECIAL_BUTTON_TOUCHPAD,
        }
        self._dpad = {
            frozenset(): D.DS4_BUTTON_DPAD_NONE,
            frozenset({"up"}): D.DS4_BUTTON_DPAD_NORTH,
            frozenset({"up", "right"}): D.DS4_BUTTON_DPAD_NORTHEAST,
            frozenset({"right"}): D.DS4_BUTTON_DPAD_EAST,
            frozenset({"down", "right"}): D.DS4_BUTTON_DPAD_SOUTHEAST,
            frozenset({"down"}): D.DS4_BUTTON_DPAD_SOUTH,
            frozenset({"down", "left"}): D.DS4_BUTTON_DPAD_SOUTHWEST,
            frozenset({"left"}): D.DS4_BUTTON_DPAD_WEST,
            frozenset({"up", "left"}): D.DS4_BUTTON_DPAD_NORTHWEST,
        }
        self._pad = vg.VDS4Gamepad()

    # -- applying input ----------------------------------------------------
    def apply(self, msg: dict | None) -> None:
        """Apply a full input snapshot, or neutral state when ``msg`` is None."""
        msg = msg or {}
        held = set(msg.get("b") or ())
        state = {
            "b": sorted(held),
            "lx": clamp(msg.get("lx", 128)),
            "ly": clamp(msg.get("ly", 128)),
            "rx": clamp(msg.get("rx", 128)),
            "ry": clamp(msg.get("ry", 128)),
        }
        if self.dry_run:
            if state != getattr(self, "_last_state", None):
                self._last_state = state
                print("PAD " + json.dumps(state), flush=True)
            return

        for name, btn in self._buttons.items():
            if name in held:
                self._pad.press_button(button=btn)
            else:
                self._pad.release_button(button=btn)
        for name, btn in self._special.items():
            if name in held:
                self._pad.press_special_button(special_button=btn)
            else:
                self._pad.release_special_button(special_button=btn)

        direction = frozenset(held & {"up", "down", "left", "right"})
        self._pad.directional_pad(direction=self._dpad.get(direction, self._dpad[frozenset()]))
        self._pad.left_trigger(value=255 if "l2" in held else 0)
        self._pad.right_trigger(value=255 if "r2" in held else 0)
        self._pad.left_joystick(x_value=state["lx"], y_value=state["ly"])
        self._pad.right_joystick(x_value=state["rx"], y_value=state["ry"])
        self._pad.update()

    def reset(self) -> None:
        """Drop every button and centre the sticks (called on disconnect)."""
        self.apply(None)
