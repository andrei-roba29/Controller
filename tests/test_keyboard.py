import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from keyboard_output import Output, validate, settings_reply


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.json'
        self.output = Output(self.path, dry_run=True)
        self.output.keyboard = Mock()
        self.output.key_class = Mock(space='SPACE', up='UP')

    def test_press_hold_release(self):
        self.output.apply({'b': ['cross']})
        self.output.apply({'b': ['cross']})
        self.output.keyboard.press.assert_called_once_with('SPACE')
        self.output.reset()
        self.output.keyboard.release.assert_called_once_with('SPACE')
        self.assertEqual(self.output.held, set())

    def test_shared_key_not_released_early(self):
        self.output.settings['mappings']['circle'] = 'space'
        self.output.apply({'b': ['cross', 'circle']})
        self.output.apply({'b': ['circle']})
        self.output.keyboard.release.assert_not_called()
        self.output.apply(None)
        self.output.keyboard.release.assert_called_once_with('SPACE')

    def test_stick_and_persistence(self):
        self.output.apply({'lx': 0, 'ly': 255})
        self.assertEqual(self.output.held, {'a', 's'})
        self.output.configure({'mode': 'keyboard', 'mappings': {'cross': 'x'}})
        self.assertEqual(self.output.held, set())
        other = Output(self.path, dry_run=True)
        self.assertEqual(other.settings['mappings']['cross'], 'x')
        self.assertEqual(other.settings['mappings']['up'], '')

    def test_reject_bad_mapping(self):
        for value in [{'mode':'shell','mappings':{}}, {'mode':'keyboard','mappings':{'cross':'rm -rf'}},
                      {'mode':'keyboard','mappings':{'unknown':'a'}}]:
            with self.assertRaises(ValueError):
                validate(value)

    def test_failed_mode_switch_preserves_settings(self):
        old = self.output.settings.copy()
        self.output.prepare = Mock(side_effect=RuntimeError('driver missing'))
        with self.assertRaises(RuntimeError):
            self.output.configure({'mode':'gamepad','mappings':{}})
        self.assertEqual(old, self.output.settings)

    def test_windows_letters_use_virtual_keys_not_unicode(self):
        self.output.dry_run = False
        self.output.key_code = Mock()
        with patch('keyboard_output.sys.platform', 'win32'):
            self.output.key('w')
            self.output.key_code.from_vk.assert_called_once_with(0x57)
            self.output.key('1')
            self.output.key_code.from_vk.assert_called_with(0x31)
            self.assertEqual(self.output.key('space'), 'SPACE')

    def test_phone_settings_roundtrip(self):
        reply = settings_reply(self.output, {'id': 'get1', 'action': 'get'})
        self.assertEqual(reply['mappings']['options'], 'enter')
        self.assertEqual(reply['id'], 'get1')
        reply = settings_reply(self.output, {'id': 'save1', 'action': 'save',
            'settings': {'mode': 'keyboard', 'mappings': {'options': 'esc'}}})
        self.assertEqual(reply['mappings']['options'], 'esc')
        self.assertEqual(Output(self.path, dry_run=True).settings['mappings']['options'], 'esc')
        self.assertIn('error', settings_reply(self.output, {'id': 'bad', 'action': 'save', 'settings': {}}))

    def test_output_failure_keeps_settings_available_and_recoverable(self):
        with patch.object(Output, 'prepare', side_effect=RuntimeError('missing driver')):
            output = Output(self.path, dry_run=True, tolerate_error=True)
        self.assertEqual(output.error, 'missing driver')
        self.assertEqual(settings_reply(output, {'id':'1','action':'get'})['mode'], 'keyboard')
        output.apply({'b':['cross']})
        self.assertEqual(output.held, set())
        output.configure({'mode':'keyboard','mappings':{'cross':'x'}})
        self.assertIsNone(output.error)
        output.apply({'b':['cross']})
        self.assertEqual(output.held, {'x'})

    def test_mouse_click_hold_release_and_shared_mapping(self):
        self.output.mouse = Mock()
        self.output.mouse_buttons = Mock(left='LEFT', right='RIGHT', middle='MIDDLE')
        self.output.configure({'mode':'keyboard', 'mappings':{'touchpad':'mouse_left', 'r1':'mouse_left'}})
        self.output.apply({'b':['touchpad', 'r1']})
        self.output.apply({'b':['r1']})
        self.output.mouse.press.assert_called_once_with('LEFT')
        self.output.mouse.release.assert_not_called()
        self.output.reset()
        self.output.mouse.release.assert_called_once_with('LEFT')
        self.output.keyboard.press.assert_not_called()

    def test_mouse_look_continues_without_new_input_and_stops_on_reset(self):
        self.output.mouse = Mock()
        self.output.configure({'mode':'keyboard', 'mappings':{'right_right':'e'},
                               'rightStickMode':'mouse', 'mouseSpeed':1000})
        self.output.apply({'rx':255, 'ry':128})
        self.output.tick(.02)
        self.output.tick(.02)
        self.assertEqual(self.output.mouse.move.call_count, 2)
        self.output.mouse.move.assert_called_with(20, 0)
        self.output.keyboard.press.assert_not_called()
        self.output.reset()
        self.output.tick(.02)
        self.assertEqual(self.output.mouse.move.call_count, 2)

    def test_mouse_look_deadzone_invert_and_stale_timeout(self):
        self.output.mouse = Mock()
        self.output.configure({'mode':'keyboard', 'mappings':{}, 'rightStickMode':'mouse',
                               'mouseSpeed':1000, 'invertMouseY':True})
        self.output.apply({'rx':130,'ry':127})
        self.output.tick(.02)
        self.output.mouse.move.assert_not_called()
        self.output.apply({'rx':128,'ry':255})
        self.output.tick(.02)
        self.output.mouse.move.assert_called_once_with(0, -20)
        self.output.last_input -= 2
        self.output.tick(.02)
        self.assertEqual(self.output.mouse.move.call_count, 1)

    def test_mouse_options_validation_and_old_settings_migration(self):
        old = validate({'mode':'keyboard','mappings':{'cross':'space'}})
        self.assertEqual(old['rightStickMode'], 'keys')
        for field, value in [('mouseSpeed',float('nan')),('mouseSpeed',0),('mouseSpeed',True),
                             ('invertMouseY','yes'),('rightStickMode','unknown')]:
            with self.assertRaises(ValueError):
                validate({'mode':'keyboard','mappings':{},field:value})

    def test_gamepad_mode_never_moves_mouse(self):
        self.output.mouse = Mock()
        self.output.gamepad = Mock()
        self.output.configure({'mode':'gamepad','mappings':{},'rightStickMode':'mouse'})
        self.output.apply({'rx':255})
        self.output.tick(.02)
        self.output.mouse.move.assert_not_called()
        self.output.gamepad.apply.assert_called_once_with({'rx':255})

    def test_windows_mouse_look_uses_relative_events(self):
        self.output.mouse = Mock()
        self.output.configure({'mode':'keyboard','mappings':{},'rightStickMode':'mouse','mouseSpeed':1000})
        self.output.apply({'rx':255})
        self.output.dry_run = False
        with patch('keyboard_output.sys.platform', 'win32'), patch('mouse_output.move_relative') as move:
            self.output.tick(.02)
            move.assert_called_once_with(20, 0)
            self.output.mouse.move.assert_not_called()
