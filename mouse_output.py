"""Relative Windows mouse events for camera look (not absolute cursor warps)."""
import ctypes


class MouseInput(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_int32), ('dy', ctypes.c_int32),
                ('mouseData', ctypes.c_uint32), ('dwFlags', ctypes.c_uint32),
                ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_size_t)]


class InputUnion(ctypes.Union):
    _fields_ = [('mi', MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint32), ('data', InputUnion)]


def move_relative(dx, dy):
    # MOUSEEVENTF_MOVE without ABSOLUTE: pointer-lock games need movement deltas.
    event = Input(type=0, data=InputUnion(mi=MouseInput(dx=dx, dy=dy, dwFlags=1)))
    send = ctypes.windll.user32.SendInput
    send.argtypes = [ctypes.c_uint32, ctypes.POINTER(Input), ctypes.c_int]
    send.restype = ctypes.c_uint32
    if send(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise OSError('Windows blocked mouse input. Keep the game and PadLink at the same privilege level.')
