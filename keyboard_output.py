"""Saved keyboard mappings and held-key reconciliation for browser games."""
import json
import sys
import math
import time
from pathlib import Path

CONTROLS = ('up down left right cross circle square triangle l1 r1 l2 r2 '
            'share options l3 r3 ps touchpad left_up left_down left_left left_right '
            'right_up right_down right_left right_right').split()
KEYS = list('abcdefghijklmnopqrstuvwxyz0123456789') + [
    'space', 'enter', 'esc', 'tab', 'backspace', 'shift', 'ctrl', 'alt',
    'up', 'down', 'left', 'right', 'mouse_left', 'mouse_right', 'mouse_middle']
DEFAULT = dict(zip(('up','down','left','right','cross','circle','square','triangle',
                    'left_up','left_down','left_left','left_right','options'),
                   ('up','down','left','right','space','e','q','r','w','s','a','d','enter')))


def validate(value):
    if not isinstance(value, dict) or value.get('mode') not in ('keyboard', 'gamepad'):
        raise ValueError('Choose keyboard or gamepad mode.')
    mappings = value.get('mappings')
    if not isinstance(mappings, dict) or any(k not in CONTROLS or not isinstance(v, str)
            or v not in KEYS + [''] for k, v in mappings.items()):
        raise ValueError('Invalid button or key mapping.')
    stick_mode = value.get('rightStickMode', 'keys')
    speed = value.get('mouseSpeed', 900)
    invert = value.get('invertMouseY', False)
    if stick_mode not in ('keys', 'mouse') or type(speed) not in (int, float) or not math.isfinite(speed) or not 100 <= speed <= 3000 or type(invert) is not bool:
        raise ValueError('Invalid mouse settings: speed must be 100–3000 pixels/second.')
    return {'mode': value['mode'], 'mappings': {c: mappings.get(c, '') for c in CONTROLS},
            'rightStickMode': stick_mode, 'mouseSpeed': speed, 'invertMouseY': invert}



class Output:
    def __init__(self, path, dry_run=False, tolerate_error=False):
        self.path = Path(path)
        self.dry_run = dry_run
        self.settings = validate({'mode': 'keyboard', 'mappings': DEFAULT})
        try:
            self.settings = validate(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            pass
        self.held = set()
        self.mouse = None
        self.mouse_vector = (0.0, 0.0)
        self.mouse_fraction = [0.0, 0.0]
        self.keyboard = None
        self.gamepad = None
        self.last_input = None
        self.error = None
        try:
            self.prepare(self.settings['mode'])
        except Exception as exc:
            if not tolerate_error:
                raise
            self.error = str(exc)

    def prepare(self, mode):
        if self.dry_run:
            return
        if mode == 'keyboard' and self.keyboard is None:
            from pynput.keyboard import Controller, Key, KeyCode
            self.keyboard = Controller()
            self.key_class = Key
            self.key_code = KeyCode
        if mode == 'keyboard' and self.mouse is None:
            from pynput.mouse import Controller, Button
            self.mouse = Controller()
            self.mouse_buttons = Button
        if mode == 'gamepad' and self.gamepad is None:
            from pad import Pad
            self.gamepad = Pad()

    def configure(self, value):
        value = validate(value)
        self.prepare(value['mode'])  # Preserve the current configuration on failure.
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, indent=2))
        temp.replace(self.path)
        self.reset()
        self.settings = value
        self.error = None

    def key(self, name):
        # Character injection uses KEYEVENTF_UNICODE on Windows. Games generally
        # listen for physical keydown/code, so send a virtual-key event instead.
        if len(name) == 1 and sys.platform == 'win32' and not self.dry_run:
            return self.key_code.from_vk(ord(name.upper()))
        return name if len(name) == 1 else getattr(self.key_class, name)

    def apply(self, msg):
        if msg is not None:
            self.last_input = time.monotonic()
        if self.error:
            return
        if self.settings['mode'] == 'gamepad':
            if self.gamepad:
                self.gamepad.apply(msg)
            return
        msg = msg or {}
        controls = set(msg.get('b') or [])
        mouse_look = self.settings['rightStickMode'] == 'mouse'
        self.mouse_vector = (0.0, 0.0)
        if mouse_look:
            x = max(-1.0, min(1.0, (msg.get('rx', 128) - 128) / 127))
            y = max(-1.0, min(1.0, (msg.get('ry', 128) - 128) / 127))
            magnitude = math.hypot(x, y)
            if magnitude > .15:
                gain = (min(magnitude, 1.0) - .15) / (.85 * magnitude)
                self.mouse_vector = (x * gain, y * gain * (-1 if self.settings['invertMouseY'] else 1))
            else:
                self.mouse_fraction = [0.0, 0.0]
        for prefix, x, y in [('left', 'lx', 'ly'), ('right', 'rx', 'ry')]:
            if prefix == 'right' and mouse_look:
                continue
            for axis, negative, positive in [(x, 'left', 'right'), (y, 'up', 'down')]:
                value = msg.get(axis, 128)
                if value < 80:
                    controls.add(prefix + '_' + negative)
                elif value > 176:
                    controls.add(prefix + '_' + positive)
        wanted = {self.settings['mappings'].get(c) for c in controls} - {None, ''}
        for name in self.held - wanted:
            self.action(name, False)
        for name in wanted - self.held:
            self.action(name, True)
        self.held = wanted

    def action(self, name, pressed):
        if name.startswith('mouse_'):
            if self.mouse:
                button = getattr(self.mouse_buttons, name.removeprefix('mouse_'))
                (self.mouse.press if pressed else self.mouse.release)(button)
        elif self.keyboard:
            (self.keyboard.press if pressed else self.keyboard.release)(self.key(name))

    def tick(self, dt):
        """Called by the agent at ~60 Hz, independent of incoming input frames."""
        if (self.error or self.settings['mode'] != 'keyboard' or not self.last_input
                or time.monotonic() - self.last_input > 1.2):
            self.mouse_vector = (0.0, 0.0)
            self.mouse_fraction = [0.0, 0.0]
            return
        delta = []
        for axis in range(2):
            total = self.mouse_fraction[axis] + self.mouse_vector[axis] * self.settings['mouseSpeed'] * max(0, min(dt, .05))
            pixels = math.trunc(total)
            self.mouse_fraction[axis] = total - pixels
            delta.append(pixels)
        if self.mouse and any(delta):
            if sys.platform == 'win32' and not self.dry_run:
                from mouse_output import move_relative
                move_relative(*delta)
            else:
                self.mouse.move(*delta)

    def reset(self):
        self.mouse_vector = (0.0, 0.0)
        self.mouse_fraction = [0.0, 0.0]
        for name in list(self.held):
            self.action(name, False)
        self.held.clear()
        if self.gamepad:
            self.gamepad.reset()


def settings_reply(output, request):
    """Same settings protocol for authenticated LAN and paired relay phones."""
    request_id = request.get('id')
    if not isinstance(request_id, str) or len(request_id) > 80:
        return {'error': 'Invalid request id'}
    try:
        if request.get('action') == 'save':
            output.configure(request.get('settings'))
        elif request.get('action') != 'get':
            raise ValueError('Unknown settings action')
        return {'id': request_id, **output.settings, 'controls': CONTROLS, 'keys': KEYS,
                'outputError': output.error}
    except Exception as exc:
        return {'id': request_id, 'error': str(exc)}
