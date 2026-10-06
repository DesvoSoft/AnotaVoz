"""Prevents two AnotaVoz processes from running at once.

Without this, launching run.bat twice (easy to do — a tray app shows no
window to signal it already started) means two processes both register the
same global hotkey and both race to write the same partial model download
to the same .part file.
"""
import ctypes

_MUTEX_NAME = "Global\\AnotaVozSingleInstance"
_ERROR_ALREADY_EXISTS = 183

_handle = None  # kept alive for the process lifetime; GC'ing it would release the mutex


def acquire():
    """Returns True if this is the only running instance, False otherwise."""
    global _handle
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    already_running = ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    if already_running:
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True
