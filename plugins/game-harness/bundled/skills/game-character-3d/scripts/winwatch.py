"""Log every top-level window that gets shown or brought to the foreground (WinEvent hook - catches windows that flash for a few ms too), with its
process and parent chain, to find what pops up on the user's desktop.   pythonw winwatch.py <log> <seconds>"""
import ctypes
import ctypes.wintypes as W
import sys
import time

u, k = ctypes.windll.user32, ctypes.windll.kernel32
log = open(sys.argv[1], 'a', encoding='utf-8', buffering=1)
end = time.time() + float(sys.argv[2])


class PE(ctypes.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', W.DWORD), ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', W.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


def procs():
    snap = k.CreateToolhelp32Snapshot(2, 0)
    e = PE()
    e.dwSize = ctypes.sizeof(PE)
    out = {}
    ok = k.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        out[e.th32ProcessID] = (e.szExeFile, e.th32ParentProcessID)
        ok = k.Process32NextW(snap, ctypes.byref(e))
    k.CloseHandle(snap)
    return out


def chain(pid):
    p, names = procs(), []
    for _ in range(8):
        if pid not in p:
            break
        names.append(f'{p[pid][0]}({pid})')
        pid = p[pid][1]
    return ' <- '.join(names)


@ctypes.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)
def on_show(hook, event, hwnd, obj, child, thread, ms):
    if obj != 0 or not hwnd or u.GetAncestor(hwnd, 2) != hwnd:       # OBJID_WINDOW, top-level only
        return
    kind = 'FOREGROUND' if event == 3 else 'SHOW'
    if kind == 'SHOW' and not u.IsWindowVisible(hwnd):
        return
    title, cls, pid = ctypes.create_unicode_buffer(200), ctypes.create_unicode_buffer(100), W.DWORD()
    u.GetWindowTextW(hwnd, title, 200)
    u.GetClassNameW(hwnd, cls, 100)
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if cls.value in ('tooltips_class32', 'IME', 'MSCTFIME UI') or cls.value.startswith('Chrome_WidgetWin'):
        return
    log.write(f'{time.strftime("%H:%M:%S")} {kind} class={cls.value} title={title.value!r} proc={chain(pid.value)}\n')


h = u.SetWinEventHook(0x8002, 0x8002, 0, on_show, 0, 0, 0)          # EVENT_OBJECT_SHOW, out of context
h2 = u.SetWinEventHook(0x0003, 0x0003, 0, on_show, 0, 0, 0)         # EVENT_SYSTEM_FOREGROUND: a window brought to front
log.write(f'{time.strftime("%H:%M:%S")} WATCH START hook={h}\n')
msg = W.MSG()
while time.time() < end:
    while u.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))
    time.sleep(0.01)
u.UnhookWinEvent(h)
u.UnhookWinEvent(h2)
log.write(f'{time.strftime("%H:%M:%S")} WATCH END\n')
