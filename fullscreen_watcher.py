"""
fullscreen_watcher.py
Polls the current foreground window on Windows and reports whether it's
covering an entire monitor (i.e. the user is watching something fullscreen,
like a YouTube video or a game). Used to auto-hide the pet and bring it
back automatically once the user exits fullscreen / minimizes.

Falls back to "never fullscreen" on non-Windows platforms so the app still
runs everywhere, just without this specific feature.
"""
import sys

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import win32gui
    import win32process
    import ctypes


def _get_taskbar_hwnd():
    if not IS_WINDOWS:
        return None
    return win32gui.FindWindow("Shell_TrayWnd", None)


def is_foreground_window_fullscreen(own_hwnds=None) -> bool:
    """
    Returns True if the currently focused window exactly covers a monitor
    (a strong signal for a fullscreen video player or game).
    `own_hwnds` is an optional set of window handles belonging to the pet
    itself, so we never mistake our own overlay for "fullscreen content".
    """
    if not IS_WINDOWS:
        return False

    own_hwnds = own_hwnds or set()

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or hwnd in own_hwnds:
        return False

    # Ignore the desktop itself and the taskbar
    class_name = win32gui.GetClassName(hwnd)
    if class_name in ("Shell_TrayWnd", "Progman", "WorkerW"):
        return False

    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return False

    win_w, win_h = right - left, bottom - top
    if win_w <= 0 or win_h <= 0:
        return False

    # Compare against the monitor that contains this window
    try:
        MONITOR_DEFAULTTONEAREST = 2
        monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        mon_w = info.rcMonitor.right - info.rcMonitor.left
        mon_h = info.rcMonitor.bottom - info.rcMonitor.top
    except Exception:
        return False

    # Allow a couple of pixels of slack for borderless-fullscreen quirks
    return abs(win_w - mon_w) <= 2 and abs(win_h - mon_h) <= 2
