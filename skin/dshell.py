# -*- coding: utf-8 -*-
"""豆包动态壁纸壳（常驻层）

行为：
- 跟随豆包主窗口，在窗口可见范围（外扩 PAD 像素）内绘制壁纸
- 用 DWM 缩略图把豆包真实界面以 0.70 不透明度贴回壁纸之上
- 窗口对鼠标完全透明（点击穿透），不影响任何交互
- 豆包失去焦点 / 最小化 / 关闭时自动隐藏或退出
"""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwm = ctypes.WinDLL("dwmapi", use_last_error=True)

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(os.path.dirname(HERE), "常驻深色2_clean.mp4")
FFMPEG = (r"C:\Users\86195\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe")

PAD = 10            # 窗口四周额外露出一圈壁纸
OPACITY = 179       # 0.70
FPS = 30
LW, LH = 2160, 1368 # 壁纸渲染尺寸（按 150% 缩放的物理屏幕）
RECT_TOL = 2        # 矩形跟随容差（像素）：小于该值的抖动不重排壳窗
HIDE_DELAY = 0.25   # 前台切走后延迟秒数再隐藏，避开 IME 候选窗的高速横跳
SW_RESTORE = 9
SW_MAXIMIZE = 3
GA_ROOTOWNER = 3
PROCESS_QUERY_LIMITED = 0x1000
# 中文/第三方输入法进程：打字时候选窗会短暂抢到前台，不能据此收起壁纸
IME_PROCS = {"textinputhost.exe", "chsime.exe", "ctfmon.exe", "sogoucloud.exe",
             "sogouinput.exe", "sogoupy.exe", "baidupinyin.exe", "baiduinput.exe",
             "qqinput.exe", "pinyinup.exe", "wechatinput.exe", "minisinp.exe"}
IME_CLASS_KEYS = ("windows.ui.core.corewindow", "ime", "cicero", "default ime")
STOP = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_stop.flag")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dshell.log")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


SHOW_FLAG = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_show.flag")
# 开屏会话标记（launcher/dsplash 维护）：它存在就说明开屏要来了或还在播，
# 哪怕开屏窗口还没建出来，壳也必须藏着，不能抢先露脸
BUSY_FLAG = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_splash_busy.flag")
BUSY_STALE = 6.0        # 标记超过这么久没刷新，按死掉的会话处理，防止壁纸永远不出来
FORCE_SHOW = os.environ.get("DB_SHELL_FORCE") == "1"   # 调试用：不管前台是谁都显示


def splash_busy():
    """开屏会话是否还在进行（防开屏进程崩溃后标记卡死）"""
    try:
        return (time.time() - os.path.getmtime(BUSY_FLAG)) < BUSY_STALE
    except Exception:
        return False


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("rcDestination", RECT), ("rcSource", RECT),
                ("opacity", ctypes.c_ubyte), ("fVisible", wintypes.BOOL),
                ("fSourceClientAreaOnly", wintypes.BOOL)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT),
                ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", ctypes.c_byte * 32)]


PAINT = {"bits": None, "bmi": None, "vw": 0, "vh": 0,
         "sx": 0, "sy": 0, "sw": 0, "sh": 0}
DEBUG_MOUSE = os.environ.get("DB_SHELL_MOUSE") == "1"   # 调试：记录壳窗收到的鼠标消息


@WNDPROC
def wndproc(hwnd, msg, wp, lp):
    if DEBUG_MOUSE and msg in (0x0200, 0x0201, 0x0202, 0x020A, 0x02A3):
        try:
            log("mouse msg=0x%04X lp=%s,%s" % (
                msg, ctypes.c_short(lp & 0xFFFF).value,
                ctypes.c_short((lp >> 16) & 0xFFFF).value))
        except Exception:
            pass
    if msg == 0x0002:          # WM_DESTROY
        u32.PostQuitMessage(0)
        return 0
    if msg == 0x000F:          # WM_PAINT
        ps = PAINTSTRUCT()
        hdc = u32.BeginPaint(hwnd, ctypes.byref(ps))
        if hdc and PAINT["bits"]:
            g32.StretchDIBits(hdc, 0, 0, PAINT["vw"], PAINT["vh"],
                              PAINT["sx"], PAINT["sy"], PAINT["sw"], PAINT["sh"],
                              PAINT["bits"], ctypes.byref(PAINT["bmi"]),
                              DIB_RGB_COLORS, SRCCOPY)
        if hdc:
            u32.EndPaint(hwnd, ctypes.byref(ps))
        return 0
    if msg == 0x0014:          # WM_ERASEBKGND
        return 1
    if msg == 0x0084:          # WM_NCHITTEST
        return -1              # HTTRANSPARENT：鼠标穿透
    return u32.DefWindowProcW(hwnd, msg, wp, lp)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


u32.DefWindowProcW.restype = ctypes.c_longlong
u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT),
                ("lPrivate", wintypes.DWORD)]


u32.PeekMessageW.restype = wintypes.BOOL
u32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND,
                             wintypes.UINT, wintypes.UINT, wintypes.UINT]
u32.TranslateMessage.restype = wintypes.BOOL
u32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
u32.DispatchMessageW.restype = ctypes.c_longlong
u32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
u32.BeginPaint.restype = wintypes.HDC
u32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
u32.EndPaint.restype = wintypes.BOOL
u32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
u32.InvalidateRect.restype = wintypes.BOOL
u32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
u32.SetLayeredWindowAttributes.restype = wintypes.BOOL
u32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD,
                                           ctypes.c_byte, wintypes.DWORD]
u32.EnableWindow.restype = wintypes.BOOL
u32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
msg_buf = MSG()


def pump():
    """每帧抽干消息队列——否则窗口不回 WM_NCHITTEST，鼠标移上去系统就转圈"""
    while u32.PeekMessageW(ctypes.byref(msg_buf), None, 0, 0, 1):
        u32.TranslateMessage(ctypes.byref(msg_buf))
        u32.DispatchMessageW(ctypes.byref(msg_buf))
u32.GetDC.restype = wintypes.HDC
u32.GetDC.argtypes = [wintypes.HWND]
u32.ReleaseDC.restype = ctypes.c_int
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u32.GetWindowRect.restype = wintypes.BOOL
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
u32.SetWindowPos.restype = wintypes.BOOL
u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
u32.ShowWindow.restype = wintypes.BOOL
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u32.IsWindowVisible.restype = wintypes.BOOL
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.IsWindow.restype = wintypes.BOOL
u32.IsWindow.argtypes = [wintypes.HWND]
u32.IsIconic.restype = wintypes.BOOL
u32.IsIconic.argtypes = [wintypes.HWND]
u32.IsZoomed.restype = wintypes.BOOL
u32.IsZoomed.argtypes = [wintypes.HWND]
u32.GetAncestor.restype = wintypes.HWND
u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CloseHandle.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowTextW.restype = ctypes.c_int
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetClassNameW.restype = ctypes.c_int
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetWindowThreadProcessId.restype = wintypes.DWORD
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowLongW.restype = ctypes.c_long
u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.GetForegroundWindow.restype = wintypes.HWND
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u32.RegisterClassExW.restype = wintypes.WORD
u32.UnregisterClassW.restype = wintypes.BOOL
u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
u32.LoadCursorW.restype = wintypes.HANDLE
u32.FindWindowW.restype = wintypes.HWND
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
k32.GetModuleHandleW.restype = wintypes.HMODULE
k32.CreateMutexW.restype = wintypes.HANDLE
k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
g32.CreateCompatibleDC.restype = wintypes.HDC
g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
g32.SelectObject.restype = wintypes.HGDIOBJ
g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
g32.DeleteDC.restype = wintypes.BOOL
g32.DeleteDC.argtypes = [wintypes.HDC]
g32.DeleteObject.restype = wintypes.BOOL
g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
g32.CreateDIBSection.restype = wintypes.HBITMAP
g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.DWORD,
                                 ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
g32.StretchDIBits.restype = ctypes.c_int
g32.StretchDIBits.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(BITMAPINFO),
                              wintypes.DWORD, wintypes.DWORD]
dwm.DwmGetWindowAttribute.restype = ctypes.c_long
dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwm.DwmRegisterThumbnail.restype = ctypes.c_long
dwm.DwmRegisterThumbnail.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.HANDLE)]
dwm.DwmUpdateThumbnailProperties.restype = ctypes.c_long
dwm.DwmUpdateThumbnailProperties.argtypes = [wintypes.HANDLE, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)]
dwm.DwmUnregisterThumbnail.restype = ctypes.c_long
dwm.DwmUnregisterThumbnail.argtypes = [wintypes.HANDLE]

WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002
WS_POPUP = 0x80000000
HWND_TOPMOST = wintypes.HWND(-1)
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010
BI_RGB = 0
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
CREATE_NO_WINDOW = 0x08000000


def splash_hwnd():
    """开屏层的窗口句柄；没在播就是 0"""
    return u32.FindWindowW("Static", "DoubaoSplashLayer")


def top_insert_after():
    """抬到置顶层时的参照：开屏层还在播就排在它下面，绝不盖住没播完的片子"""
    return splash_hwnd() or HWND_TOPMOST


def visible_frame(hwnd):
    """DWM 扩展边框 = 真正可见的窗口范围（不含 11px 阴影）"""
    r = RECT()
    hr = dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))
    if hr != 0:
        u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def find_main_window():
    best = [None, 0]

    @ENUMPROC
    def cb(hwnd, lp):
        if not u32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        if "豆包" not in buf.value:
            return True
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        if "Chrome_WidgetWin" not in cls.value:
            return True
        r = RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best[1]:
            best[0] = hwnd
            best[1] = area
        return True

    u32.EnumWindows(cb, 0)
    return best[0]


def pid_of(hwnd):
    p = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


_proc_name_cache = {}


def proc_name(pid):
    """进程可执行名（小写），带缓存；取不到返回空串"""
    if pid in _proc_name_cache:
        return _proc_name_cache[pid]
    name = ""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if h:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value).lower()
        k32.CloseHandle(h)
    _proc_name_cache[pid] = name
    return name


def _class_name(hwnd):
    c = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, c, 256)
    return c.value.lower()


def is_ime_window(hwnd):
    """输入法候选窗/输入体验窗：打字时短暂抢前台，属正常输入状态"""
    if not hwnd:
        return False
    if any(k in _class_name(hwnd) for k in IME_CLASS_KEYS):
        return True
    return proc_name(pid_of(hwnd)) in IME_PROCS


GWL_EXSTYLE = -20


def doubao_popup(doubao_pid, src):
    """豆包自己弹出的浮层（托盘右键菜单、下拉、提示条、对话框）。

    这类窗口是独立顶层窗口且带 WS_EX_TOPMOST，比壁纸壳后建又比壳矮一层，
    一旦壳层把它盖住，右键托盘就看不到「退出」菜单了。只要有它在，壁纸立刻让路。
    """
    hit = [None]

    @ENUMPROC
    def cb(hwnd, lp):
        if hwnd == src or not u32.IsWindowVisible(hwnd):
            return True
        if pid_of(hwnd) != doubao_pid:
            return True
        if not (u32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST):
            return True
        if u32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_NOACTIVATE:
            return True          # 不抢焦点的装饰浮条，不影响点菜
        r = RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        w = r.right - r.left
        h = r.bottom - r.top
        if w <= 0 or h <= 0 or w * h < 3000:
            return True
        s = RECT()
        u32.GetWindowRect(src, ctypes.byref(s))
        if w * h >= (s.right - s.left) * (s.bottom - s.top) * 0.6:
            return True          # 豆包自己的整屏透明层，不是菜单
        hit[0] = hwnd
        return False

    u32.EnumWindows(cb, 0)
    return hit[0]


def foreground_is_doubao(fg, src, doubao_pid):
    """前台归属：True=豆包主窗内 / "popup"=豆包自己的浮层（托盘菜单等）/ False=别的程序 / None=前台为空

    托盘右键菜单是豆包另开的一个置顶窗口，不是主窗，也不是主窗的 owned 窗口；
    旧版把它当成「还在豆包内」，壁纸照常显示，正好压住菜单让「退出」点不到。
    """
    if not fg:
        return None
    if fg == src:
        return True
    root = u32.GetAncestor(fg, GA_ROOTOWNER)
    if root and root == src:
        return True                      # 主窗自己的对话框，算在使用状态
    if is_ime_window(fg):
        return True
    if pid_of(fg) == doubao_pid or proc_name(pid_of(fg)) == "doubao.exe":
        return "popup"
    return False


def ensure_maximized(hwnd):
    """启动/重挂后保证主窗最大化；不干涉之后用户手动还原"""
    if not hwnd:
        return
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
    if not u32.IsZoomed(hwnd):
        u32.ShowWindow(hwnd, SW_MAXIMIZE)


def rect_close(a, b):
    return all(abs(x - y) <= RECT_TOL for x, y in zip(a, b))


def make_dib(w, h):
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    p = ctypes.c_void_p()
    bm = g32.CreateDIBSection(None, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(p), None, 0)
    dc = g32.CreateCompatibleDC(None)
    g32.SelectObject(dc, bm)
    return bmi, bm, p, dc


def read_exact(f, n):
    buf = bytearray(n)
    got = 0
    mv = memoryview(buf)
    while got < n:
        r = f.readinto(mv[got:])
        if not r:
            return None
        got += r
    return bytes(buf)


def main():
    log("shell start")
    if os.path.exists(STOP):
        try:
            os.remove(STOP)
        except Exception:
            pass
    k32.CreateMutexW(None, False, "DoubaoWallShellMutex")
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
        log("another shell running, exit")
        return 0
    src = find_main_window()
    if not src:
        log("no doubao window")
        return 1
    dwm_pid = pid_of(src)
    ensure_maximized(src)
    log("doubao hwnd=%s pid=%s" % (src, dwm_pid))

    if not os.path.exists(VIDEO):
        log("video missing: %s" % VIDEO)
        return 2
    log("video: %s" % os.path.basename(VIDEO))

    ff = subprocess.Popen([FFMPEG, "-v", "error", "-stream_loop", "-1", "-i", VIDEO,
                           "-vf", ("scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
                                   "crop=%d:%d") % (LW, LH, LW, LH),
                           "-pix_fmt", "bgra", "-r", str(FPS), "-f", "rawvideo", "pipe:1"],
                          stdout=subprocess.PIPE, bufsize=0,
                          creationflags=CREATE_NO_WINDOW)

    bmi, bm, pbits, mdc = make_dib(LW, LH)
    hinst = k32.GetModuleHandleW(None)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinst
    wc.hCursor = u32.LoadCursorW(None, 32512)
    wc.lpszClassName = "DoubaoWallShell"
    u32.RegisterClassExW(ctypes.byref(wc))

    frame = visible_frame(src)
    win = u32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                              | WS_EX_TRANSPARENT | WS_EX_LAYERED,
                              "DoubaoWallShell", "", WS_POPUP,
                              frame.left - PAD, frame.top - PAD,
                              (frame.right - frame.left) + 2 * PAD,
                              (frame.bottom - frame.top) + 2 * PAD,
                              None, None, hinst, None)
    # 常量 alpha=255（不透明），只是为了拿到分层窗口的“点击穿透”行为
    u32.SetLayeredWindowAttributes(win, 0, 255, LWA_ALPHA)
    # 再补一刀：把窗口禁用，系统在命中测试时直接跳过它，鼠标/焦点完全不经过我们
    u32.EnableWindow(win, False)
    u32.ShowWindow(win, 0)
    u32.SetWindowPos(win, HWND_TOPMOST, frame.left - PAD, frame.top - PAD,
                     (frame.right - frame.left) + 2 * PAD,
                     (frame.bottom - frame.top) + 2 * PAD,
                     SWP_NOACTIVATE)

    # 开屏层若在，把自己垫到它下面，开屏尾部淡出可直接化进壁纸
    sp = u32.FindWindowW("Static", "DoubaoSplashLayer")
    if sp:
        u32.SetWindowPos(win, sp, 0, 0, 0, 0, 0x0001 | 0x0002 | SWP_NOACTIVATE)

    thumb = wintypes.HANDLE()
    hr = dwm.DwmRegisterThumbnail(win, src, ctypes.byref(thumb))
    props = DWM_THUMBNAIL_PROPERTIES()
    props.dwFlags = 0x1 | 0x4 | 0x8 | 0x10
    props.rcDestination = RECT(PAD, PAD, PAD + (frame.right - frame.left),
                               PAD + (frame.bottom - frame.top))
    props.rcSource = RECT(0, 0, 0, 0)
    props.opacity = OPACITY
    props.fVisible = True
    props.fSourceClientAreaOnly = True
    dwm.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))
    log("thumb hr=0x%08X" % (hr & 0xFFFFFFFF))

    fb = LW * LH * 4
    last = (frame.left, frame.top, frame.right, frame.bottom)
    visible = False
    last_want = None
    last_fg = None
    hide_since = None
    splash_block = True       # 开屏还在播（没到收尾）时壁纸不亮，否则两个人重影
    splash_t = 0.0
    splash_prev = True        # 上一拍开屏层是否存在，用来捕捉它退场的那一刻
    popup = None              # 豆包自己的置顶浮层（托盘菜单等）；有它就不许壁纸压在上面
    last_popup = None
    t0 = time.perf_counter()
    n = 0
    try:
        while True:
            pump()
            if os.path.exists(STOP):
                log("stop flag")
                break
            if not u32.IsWindow(src):
                # 豆包重启/换窗：先尝试重新挂上真实主窗口，挂不上才算关闭
                nxt = None
                for _ in range(20):
                    time.sleep(0.25)
                    c = find_main_window()
                    if c and u32.IsWindow(c):
                        nxt = c
                        break
                if not nxt:
                    log("doubao closed")
                    break
                if thumb:
                    try:
                        dwm.DwmUnregisterThumbnail(thumb)
                    except Exception:
                        pass
                src = nxt
                dwm_pid = pid_of(src)
                ensure_maximized(src)
                f = visible_frame(src)
                last = (f.left, f.top, f.right, f.bottom)
                # 换窗期间先藏起来：开屏层可能正盖在上面播，露不露脸交给主循环判定
                props.fVisible = False
                dwm.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))
                u32.ShowWindow(win, 0)
                visible = False
                u32.SetWindowPos(win, top_insert_after(), f.left - PAD, f.top - PAD,
                                 (f.right - f.left) + 2 * PAD,
                                 (f.bottom - f.top) + 2 * PAD,
                                 SWP_NOACTIVATE)
                hr = dwm.DwmRegisterThumbnail(win, src, ctypes.byref(thumb))
                props.rcDestination = RECT(PAD, PAD, PAD + (f.right - f.left),
                                           PAD + (f.bottom - f.top))
                props.fVisible = True
                dwm.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))
                hide_since = None
                last_want = None
                log("re-attached hwnd=%s hr=0x%08X" % (src, hr & 0xFFFFFFFF))
                continue

            data = read_exact(ff.stdout, fb)
            if data is None:
                log("video eof")
                break
            ctypes.memmove(pbits, data, fb)

            fg = u32.GetForegroundWindow()
            fg_pid = pid_of(fg) if fg else 0
            if fg != last_fg:
                last_fg = fg
                if fg:
                    log("fg change hwnd=%s pid=%s proc=%s" % (
                        fg, fg_pid, proc_name(fg_pid)))
                else:
                    log("fg change hwnd=None pid=0")
            iconic = u32.IsIconic(src)

            el = time.perf_counter() - t0
            if el - splash_t > 0.05:
                splash_t = el
                sp_now = splash_hwnd()
                if splash_prev and not sp_now:
                    # 开屏刚退场：壳归位到置顶层，免得被别的置顶窗压住
                    u32.SetWindowPos(win, HWND_TOPMOST, 0, 0, 0, 0,
                                     0x0002 | 0x0001 | SWP_NOACTIVATE)
                splash_prev = bool(sp_now)
                splash_block = (bool(sp_now) or splash_busy()) and not os.path.exists(SHOW_FLAG)
            popup = doubao_popup(dwm_pid, src)
            fg_state = foreground_is_doubao(fg, src, dwm_pid)
            if fg_state == "popup":
                popup = popup or fg          # 前台就停在豆包自己的菜单上，一样要让路
            if popup != last_popup:
                last_popup = popup
                log("doubao popup=%s" % popup)

            fg_ok = fg_state
            if fg_ok is None:
                fg_ok = visible   # 前台为空（锁屏/切桌面）时维持现状，不主动收起
            elif fg_ok == "popup":
                fg_ok = True      # 前台仍在豆包内，只是浮层，不是切到别的程序
            want = ((not iconic) and (FORCE_SHOW or fg_ok)
                    and not splash_block and not popup)

            # 切走延迟隐藏：避开 IME 候选窗在豆包窗/输入窗之间的高速横跳
            now_t = time.perf_counter()
            if want:
                hide_since = None
            elif hide_since is None:
                hide_since = now_t
            if popup:
                # 豆包菜单/浮层压在最上层：不能等 0.25 秒，立刻收起，否则就是盖住「退出」
                hide_since = now_t - HIDE_DELAY - 0.01
            hold = want or (visible and hide_since is not None and
                            now_t - hide_since < HIDE_DELAY)
            if splash_block:
                # 硬红线：开屏在播期间壁纸一律不许露脸，不吃 0.25 秒隐藏宽限
                hold = False

            if hold and not visible:
                u32.ShowWindow(win, 4)
                u32.SetWindowPos(win, top_insert_after(), 0, 0, 0, 0,
                                 0x0002 | 0x0001 | SWP_NOACTIVATE | SWP_SHOWWINDOW)
                props.fVisible = True
                dwm.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))
                visible = True
            elif not hold:
                # 以窗口真实状态为准（重挂、异常退出等路径可能让本地变量和实际不一致）
                if u32.IsWindowVisible(win):
                    props.fVisible = False
                    dwm.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))
                    u32.ShowWindow(win, 0)
                visible = False

            if want != last_want:
                log("want=%s fg_ok=%s fg_pid=%s doubao_pid=%s iconic=%s splash_block=%s" % (
                    want, fg_ok, fg_pid, dwm_pid, iconic, splash_block))
                last_want = want

            if visible:
                f = visible_frame(src)
                cur = (f.left, f.top, f.right, f.bottom)
                if f.right - f.left <= 0 or f.bottom - f.top <= 0:
                    # DWM 边框偶发返回空矩形：沿用上次，避免壳窗缩成一条
                    cur = last
                    f = RECT(last[0], last[1], last[2], last[3])
                if not rect_close(cur, last):
                    last = cur
                    u32.SetWindowPos(win, top_insert_after(), f.left - PAD, f.top - PAD,
                                     (f.right - f.left) + 2 * PAD,
                                     (f.bottom - f.top) + 2 * PAD,
                                     SWP_NOACTIVATE | SWP_SHOWWINDOW)
                    props.rcDestination = RECT(PAD, PAD, PAD + (f.right - f.left),
                                               PAD + (f.bottom - f.top))
                    dwm.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))

                vw = (f.right - f.left) + 2 * PAD
                vh = (f.bottom - f.top) + 2 * PAD
                # 等比裁切填充（cover），避免壁纸被窗口比例拉变形
                img_ar = float(LW) / LH
                view_ar = float(vw) / vh if vh else img_ar
                if view_ar >= img_ar:
                    sh = LH
                    sw = int(round(LH * view_ar))
                    sx = max(0, (LW - sw) // 2)
                    sy = 0
                else:
                    sw = LW
                    sh = int(round(LW / view_ar))
                    sx = 0
                    sy = max(0, (LH - sh) // 2)
                # 帧数据到位后交给 WM_PAINT 去画（分层窗口必须走绘制消息才会上屏）
                PAINT["vw"], PAINT["vh"] = vw, vh
                PAINT["sx"], PAINT["sy"] = sx, sy
                PAINT["sw"], PAINT["sh"] = min(sw, LW), min(sh, LH)
                PAINT["bmi"] = bmi
                PAINT["bits"] = pbits
                u32.InvalidateRect(win, None, False)
                pump()

            n += 1
            d = (t0 + n / float(FPS)) - time.perf_counter()
            if d > 0:
                time.sleep(d)
            elif d < -0.5:
                t0 = time.perf_counter() - n / float(FPS)
    finally:
        try:
            ff.kill()
        except Exception:
            pass
        if thumb:
            try:
                dwm.DwmUnregisterThumbnail(thumb)
            except Exception:
                pass
        try:
            u32.DestroyWindow(win)
        except Exception:
            pass
        try:
            g32.DeleteDC(mdc)
            g32.DeleteObject(bm)
        except Exception:
            pass
        try:
            u32.UnregisterClassW("DoubaoWallShell", hinst)
        except Exception:
            pass
        log("shell exit frames=%d" % n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        log("FATAL: %s" % traceback.format_exc().replace("\n", " | "))
        sys.exit(1)
