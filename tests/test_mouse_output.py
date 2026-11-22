import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mouse_output import Input, move_relative


class WindowsMouseTests(unittest.TestCase):
    def test_relative_sendinput_structure(self):
        def send(count, pointer, size):
            event = ctypes.cast(pointer, ctypes.POINTER(Input)).contents
            self.assertEqual(count, 1)
            self.assertEqual(size, 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
            self.assertEqual(event.type, 0)
            self.assertEqual(event.data.mi.dwFlags, 1)
            self.assertEqual((event.data.mi.dx, event.data.mi.dy), (-12, 7))
            return 1
        fake = SimpleNamespace(user32=SimpleNamespace(SendInput=Mock(side_effect=send)))
        with patch.object(ctypes, 'windll', fake, create=True):
            move_relative(-12, 7)

    def test_windows_blocked_input_is_reported(self):
        fake = SimpleNamespace(user32=SimpleNamespace(SendInput=Mock(return_value=0)))
        with patch.object(ctypes, 'windll', fake, create=True), self.assertRaises(OSError):
            move_relative(1, 1)
