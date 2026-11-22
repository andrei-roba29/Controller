"""Saved keyboard mappings and held-key reconciliation for browser games."""
import json
from pathlib import Path

CONTROLS = ('up down left right cross circle square triangle l1 r1 l2 r2 '
            'share options l3 r3 ps touchpad left_up left_down left_left left_right '
            'right_up right_down right_left right_right').split()
KEYS = list('abcdefghijklmnopqrstuvwxyz0123456789') + [
    'space', 'enter', 'esc', 'tab', 'backspace', 'shift', 'ctrl', 'alt',
    'up', 'down', 'left', 'right']
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
    return {'mode': value['mode'], 'mappings': {c: mappings.get(c, '') for c in CONTROLS}}


class Output:
    def __init__(self, path, dry_run=False):
        self.path = Path(path)
        self.dry_run = dry_run
        self.settings = validate({'mode': 'keyboard', 'mappings': DEFAULT})
        try:
            self.settings = validate(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            pass
        self.held = set()
        self.keyboard = None
        self.gamepad = None
        self.last_input = None
        self.prepare(self.settings['mode'])

    def prepare(self, mode):
        if self.dry_run:
            return
        if mode == 'keyboard' and self.keyboard is None:
            from pynput.keyboard import Controller, Key
            self.keyboard = Controller()
            self.key_class = Key
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

    def key(self, name):
        return name if len(name) == 1 else getattr(self.key_class, name)

    def apply(self, msg):
        import time
        if msg is not None:
            self.last_input = time.monotonic()
        if self.settings['mode'] == 'gamepad':
            if self.gamepad:
                self.gamepad.apply(msg)
            return
        msg = msg or {}
        controls = set(msg.get('b') or [])
        for prefix, x, y in [('left', 'lx', 'ly'), ('right', 'rx', 'ry')]:
            for axis, negative, positive in [(x, 'left', 'right'), (y, 'up', 'down')]:
                value = msg.get(axis, 128)
                if value < 80:
                    controls.add(prefix + '_' + negative)
                elif value > 176:
                    controls.add(prefix + '_' + positive)
        wanted = {self.settings['mappings'].get(c) for c in controls} - {None, ''}
        for name in self.held - wanted:
            if self.keyboard:
                self.keyboard.release(self.key(name))
        for name in wanted - self.held:
            if self.keyboard:
                self.keyboard.press(self.key(name))
        self.held = wanted

    def reset(self):
        for name in list(self.held):
            if self.keyboard:
                self.keyboard.release(self.key(name))
        self.held.clear()
        if self.gamepad:
            self.gamepad.reset()
