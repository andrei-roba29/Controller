import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from keyboard_output import Output, validate


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
