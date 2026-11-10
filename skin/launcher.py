# -*- coding: utf-8 -*-
"""豆包启动器（由 .lnk 指向本脚本）

- 豆包已在运行（哪怕窗口还没出来）→ 只做普通激活，不重播开屏
- 真冷启动 → 先上开屏层，再拉起豆包；等到「稳定」的主窗口出现才垫壁纸壳
- 全程不弹控制台：子进程一律 CREATE_NO_WINDOW
"""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DOUBAO_EXE = r"C:\Users\86195\AppData\Local\Doubao\Application\Doubao.exe"
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
STOP = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_stop.flag")
SHOW_FLAG = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_show.flag")
# 开屏会话标记：起播前写、开屏退出时清，壳靠它在开屏窗口还没建出来的空档里也保持隐藏
BUSY_FLAG = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_splash_busy.flag")
LOG = os.path.join(HERE, "launcher.log")

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi")
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

u32.GetWindowTextW.restype = ctypes.c_int
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetClassNameW.restype = ctypes.c_int
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetWindowRect.restype = wintypes.BOOL
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.IsWindowVisible.restype = wintypes.BOOL
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.SetForegroundWindow.restype = wintypes.BOOL
u32.SetForegroundWindow.argtypes = [wintypes.HWND]
u32.ShowWindow.restype = wintypes.BOOL
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.IsIconic.restype = wintypes.BOOL
u32.IsIconic.argtypes = [wintypes.HWND]
u32.IsZoomed.restype = wintypes.BOOL
u32.IsZoomed.argtypes = [wintypes.HWND]
u32.FindWindowW.restype = wintypes.HWND
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u32.IsWindow.restype = wintypes.BOOL
u32.IsWindow.argtypes = [wintypes.HWND]

k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CloseHandle.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
psapi.EnumProcesses.restype = wintypes.BOOL
psapi.EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD)]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD)]

DETACHED = 0x00000008
CREATE_NEW_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
PROCESS_QUERY_LIMITED = 0x1000
SW_RESTORE = 9
SW_MAXIMIZE = 3


def ensure_maximized(hwnd):
    """启动时把主窗顶到最大化；已最大化/最小化恢复后最大化，不干涉之后的手动还原"""
    if not hwnd:
        return
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
    if not u32.IsZoomed(hwnd):
        u32.ShowWindow(hwnd, SW_MAXIMIZE)


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def find_main_window():
    """标题含「豆包」且类名 Chrome_WidgetWin 的最大可见窗口"""
    best = [None, 0]

    @ENUMPROC
    def cb(hwnd, lp):
        if not u32.IsWindowVisible(hwnd):
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, b, 256)
        if "豆包" not in b.value:
            return True
        c = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, c, 256)
        if "Chrome_WidgetWin" not in c.value:
            return True
        r = wintypes.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        a = (r.right - r.left) * (r.bottom - r.top)
        if a > best[1]:
            best[0] = hwnd
            best[1] = a
        return True

    u32.EnumWindows(cb, 0)
    return best[0]


def wait_stable_window(timeout=30.0, stable=0.9):
    """等同一个 hwnd 连续稳定 stable 秒——启动期的临时窗口换手后不会误判"""
    t0 = time.time()
    last, last_t = None, 0.0
    while time.time() - t0 < timeout:
        w = find_main_window()
        if w:
            if w == last:
                if time.time() - last_t >= stable:
                    return w, time.time() - t0
            else:
                last, last_t = w, time.time()
        else:
            last = None
        time.sleep(0.15)
    return last, time.time() - t0


def doubao_running():
    """进程里有没有 Doubao.exe（窗口可能还没建出来）"""
    arr = (wintypes.DWORD * 2048)()
    n = wintypes.DWORD()
    if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(n)):
        return False
    cnt = n.value // ctypes.sizeof(wintypes.DWORD)
    for i in range(cnt):
        pid = arr[i]
        if not pid:
            continue
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            continue
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        got = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        k32.CloseHandle(h)
        if got and os.path.basename(buf.value).lower() == "doubao.exe":
            return True
    return False


def spawn(script):
    p = subprocess.Popen([PYW if os.path.exists(PYW) else sys.executable, script],
                         creationflags=DETACHED | CREATE_NEW_GROUP | CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    log("spawn %s pid=%d" % (os.path.basename(script), p.pid))
    return p


def shell_alive():
    return bool(u32.FindWindowW("DoubaoWallShell", None))


def main():
    log("launcher start argv=%s" % sys.argv)
    win = find_main_window()
    proc = doubao_running()

    if win or proc:
        # 已在运行（或正在启动）：绝不重开实例
        if not win:
            log("doubao process alive, window pending -> wait")
            win, dt = wait_stable_window(timeout=20.0)
            log("window=%s after %.1fs (pending path)" % (win, dt))
        else:
            log("doubao already running hwnd=%s -> activate only" % win)
        if win:
            ensure_maximized(win)
            u32.SetForegroundWindow(win)
        if win and not shell_alive():
            spawn(os.path.join(HERE, "dshell.py"))
        log("launcher done")
        return 0

    log("cold start path")
    for f in (STOP, SHOW_FLAG):
        try:
            os.remove(f)
        except Exception:
            pass
    try:
        # 先立会话标记再起开屏：壳无论起来得多早都不会抢在开屏前面露脸
        open(BUSY_FLAG, "w").close()
    except Exception:
        pass
    try:
        spawn(os.path.join(HERE, "dsplash.py"))
    except Exception as e:
        log("spawn splash failed: %r" % (e,))
        try:
            os.remove(BUSY_FLAG)
        except Exception:
            pass
        return 4
    time.sleep(0.15)
    try:
        subprocess.Popen([DOUBAO_EXE],
                         creationflags=DETACHED | CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
        log("doubao exe launched")
    except Exception as e:
        log("launch exe failed: %r" % (e,))
        return 3

    win, dt = wait_stable_window(timeout=30.0)
    log("stable window=%s after %.1fs" % (win, dt))
    if win:
        # 刚启动时前台可能还停在资源管理器，壳会因此隐身，这里主动拉到前台
        ensure_maximized(win)
        u32.SetForegroundWindow(win)
        log("foreground set")
    if win and not shell_alive():
        spawn(os.path.join(HERE, "dshell.py"))
    log("launcher done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
