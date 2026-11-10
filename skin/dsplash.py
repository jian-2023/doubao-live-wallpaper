# -*- coding: utf-8 -*-
"""冷启动开屏层

时间线：
  t=0        全屏铺满启动素材，alpha=255
  窗口出现后   立即开始 1.2 秒线性淡出到 alpha≈110（真实 UI 从人物后方透出）
  素材播完     保持最后一帧，等 0.3 秒收尾后自己退出，交给壁纸壳
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

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.dirname(HERE)
VIDEO = os.path.join(MEDIA, "启动深色_clean.mp4")
AUDIO = os.path.join(MEDIA, "启动深色_audio.wav")
# 启动片放完后的「欢迎回来」：只走冷启动这条路径，普通激活不会经过这里
WELCOME = os.path.join(MEDIA, "欢迎回来.m4a")
FFMPEG = (r"C:\Users\86195\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe")
FFPLAY = (r"C:\Users\86195\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-9.0.2-full_build\bin\ffplay.exe")
CREATE_NO_WINDOW = 0x08000000

FPS = 30
FADE_DUR = 1.2
MIN_ALPHA = 110
HOLD_TAIL = float(os.environ.get("DB_SPLASH_HOLD", "0.30"))  # 便于人工观察/截图时加长
TAIL_FADE = 0.40          # 收尾化成壁纸的时长：壁纸在这段里已经在下面等着
WELCOME_DELAY = 0.5       # 启动片最后一帧上屏后，隔多久响「欢迎回来」
GRACE_NO_WIN = 3.0        # 视频放完还没等到豆包窗口，再多举一会儿再淡出
SHOW_FLAG = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_show.flag")
# 开屏会话标记：launcher 起播前写下，开屏退出时清掉。
# 壳靠它判断「开屏要来了/还在播」，不必等开屏窗口建出来才知道。
BUSY_FLAG = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_splash_busy.flag")
LOG = os.path.join(HERE, "dsplash.log")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass



class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

u32.GetDC.restype = wintypes.HDC
u32.GetDC.argtypes = [wintypes.HWND]
u32.ReleaseDC.restype = ctypes.c_int
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u32.UpdateLayeredWindow.restype = wintypes.BOOL
u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT),
                                    ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                    ctypes.POINTER(POINT), wintypes.DWORD,
                                    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
u32.DestroyWindow.restype = wintypes.BOOL
u32.DestroyWindow.argtypes = [wintypes.HWND]
u32.IsWindow.restype = wintypes.BOOL
u32.IsWindow.argtypes = [wintypes.HWND]
u32.IsWindowVisible.restype = wintypes.BOOL
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.GetWindowTextW.restype = ctypes.c_int
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetClassNameW.restype = ctypes.c_int
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetSystemMetrics.restype = ctypes.c_int
u32.GetSystemMetrics.argtypes = [ctypes.c_int]
u32.ShowWindow.restype = wintypes.BOOL
u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
k32.GetModuleHandleW.restype = wintypes.HMODULE
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

WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020
WS_POPUP = 0x80000000
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
BI_RGB = 0
DIB_RGB_COLORS = 0


def find_main_window():
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


def play_audio(path):
    """启动音轨：与第一帧同时起播，异步、不阻塞渲染"""
    try:
        if not os.path.exists(path):
            log("audio missing %s" % path)
            return False
        mm = ctypes.WinDLL("winmm")
        mm.sndPlaySoundW.restype = wintypes.BOOL
        mm.sndPlaySoundW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        ok = bool(mm.sndPlaySoundW(path, 0x0001 | 0x0002))  # SND_ASYNC | SND_FILENAME
        log("audio start ok=%s" % ok)
        return ok
    except Exception as e:
        log("audio failed %s" % e)
        return False


def play_welcome():
    """欢迎回来：走独立播放进程，开屏层退场后它照样能把整段放完"""
    if not os.path.exists(WELCOME):
        log("welcome missing %s" % WELCOME)
        return False
    try:
        p = subprocess.Popen([FFPLAY, "-v", "error", "-nodisp", "-autoexit", WELCOME],
                             creationflags=CREATE_NO_WINDOW | 0x00000008,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        log("welcome play pid=%d" % p.pid)
        return True
    except Exception as e:
        log("welcome failed %r" % (e,))
        return False


def main():
    if not os.path.exists(VIDEO):
        log("video missing")
        return 2
    try:
        os.remove(SHOW_FLAG)      # 清掉上一轮遗留的“放行”标记
    except Exception:
        pass
    try:
        # 手动起播时 launcher 没写过会话标记，这里补上：壳必须知道开屏在
        open(BUSY_FLAG, "w").close()
    except Exception:
        pass

    SW = u32.GetSystemMetrics(0)
    SH = u32.GetSystemMetrics(1)

    ff = subprocess.Popen([FFMPEG, "-v", "error", "-i", VIDEO,
                           "-vf", ("scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
                                   "crop=%d:%d") % (SW, SH, SW, SH),
                           "-pix_fmt", "bgra", "-r", str(FPS), "-f", "rawvideo", "pipe:1"],
                          stdout=subprocess.PIPE, bufsize=0,
                          creationflags=CREATE_NO_WINDOW)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = SW
    bmi.bmiHeader.biHeight = -SH
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    pbits = ctypes.c_void_p()
    bm = g32.CreateDIBSection(None, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(pbits), None, 0)
    mdc = g32.CreateCompatibleDC(None)
    g32.SelectObject(mdc, bm)

    hinst = k32.GetModuleHandleW(None)
    win = u32.CreateWindowExW(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_NOACTIVATE
                              | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT,
                              "Static", "DoubaoSplashLayer", WS_POPUP,
                              0, 0, SW, SH, None, None, hinst, None)
    u32.ShowWindow(win, 4)  # SW_SHOWNOACTIVATE：分层窗口必须先显示再推帧

    size = wintypes.SIZE(SW, SH)
    src_pt = POINT(0, 0)
    dst_pt = POINT(0, 0)
    blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, 0)
    fb = SW * SH * 4
    t0 = time.perf_counter()
    have_frame = False
    audio_started = False
    t_win = None
    t_end = None
    video_end = None    # 最后一帧真正上屏的时刻；收尾以它为准，不按秒表掐
    eof = False
    cand = None
    cand_t = 0.0
    n = 0
    tail_sent = False
    welcome_sent = False
    busy_t = -1.0
    try:
        while True:
            el = time.perf_counter() - t0
            if t_win is None:
                h = find_main_window()
                if h:
                    # 要求同一个 hwnd 稳定 0.6s，避开启动期临时窗口误判
                    if h == cand and el - cand_t >= 0.6:
                        t_win = el
                        log("window appeared at %.2fs" % el)
                    elif h != cand:
                        cand, cand_t = h, el

            data = None if eof else read_exact(ff.stdout, fb)
            if data is not None:
                ctypes.memmove(pbits, data, fb)
                have_frame = True
                video_end = el
                if not audio_started:
                    audio_started = True
                    play_audio(AUDIO)      # 第一帧真正上屏时同步起播音轨
            elif not eof:
                # 读不满一整帧 = 视频流结束（或 ffmpeg 挂了）；最后一帧已经上屏
                eof = True
                log("video eof at %.2fs frames=%d" % (el, n))

            # 最后一帧上屏后隔 WELCOME_DELAY 秒响「欢迎回来」，只响一次
            if not welcome_sent and video_end is not None and el >= video_end + WELCOME_DELAY:
                welcome_sent = True
                log("welcome at %.2fs" % el)
                play_welcome()

            if t_end is None:
                if t_win is not None and eof:
                    # 整段播完 → 压住最后一帧 → 才开始化成壁纸；中间不会插队
                    tail_at = (video_end or el) + HOLD_TAIL
                    if t_win is not None:
                        tail_at = max(tail_at, max(1.0, t_win) + FADE_DUR)
                    t_end = tail_at + TAIL_FADE
                    log("planned end %.2fs (video_end=%.2f t_win=%.2f)"
                        % (t_end, video_end or el, t_win))
                elif t_win is None and eof and el > (video_end or el) + GRACE_NO_WIN:
                    # 片子都放完了还没见到豆包窗口：冻住最后一眼，淡出收场
                    t_end = el + TAIL_FADE + 0.05
                    log("no window, fade out at %.2fs" % t_end)

            # 心跳：壳靠标记的更新时间判断开屏会话还活着
            if el - busy_t >= 1.0:
                busy_t = el
                try:
                    os.utime(BUSY_FLAG, None)
                except Exception:
                    pass

            # 进入收尾淡出：放行壁纸层，让开屏淡到 0 时直接化进壁纸
            if t_end is not None and not tail_sent and el >= t_end - TAIL_FADE:
                tail_sent = True
                try:
                    with open(SHOW_FLAG, "w"):
                        pass
                    log("tail start, wall released")
                except Exception:
                    pass

            # alpha 曲线：满 → 1.2s 淡到 110 → 收尾 TAIL_FADE 内淡到 0（化进下方壁纸）
            if t_win is None:
                alpha = 255
            else:
                f0 = max(1.0, t_win)
                if el < f0:
                    alpha = 255
                else:
                    k = min(1.0, (el - f0) / FADE_DUR)
                    alpha = int(255 - (255 - MIN_ALPHA) * k)
            alpha = max(MIN_ALPHA, alpha)
            if t_end:
                k = max(0.0, min(1.0, (t_end - el) / TAIL_FADE))
                alpha = min(alpha, int(MIN_ALPHA * k))

            if have_frame:
                blend.SourceConstantAlpha = alpha
                u32.UpdateLayeredWindow(win, None, ctypes.byref(dst_pt), ctypes.byref(size),
                                        mdc, ctypes.byref(src_pt), 0,
                                        ctypes.byref(blend), ULW_ALPHA)

            n += 1
            if t_end is not None and el >= t_end:
                break
            if t_win is None and eof and el > (video_end or 0.0) + GRACE_NO_WIN + 5.0:
                log("no doubao window, give up")
                break

            d = (t0 + n / float(FPS)) - time.perf_counter()
            if d > 0:
                time.sleep(d)
    finally:
        # 极少数提前退场的分支（比如整段放完还没等到豆包窗口就收场）也要把「欢迎回来」补上
        if not welcome_sent and video_end is not None:
            welcome_sent = True
            log("welcome (fallback) at %.2fs" % (time.perf_counter() - t0))
            play_welcome()
        try:
            ff.kill()
        except Exception:
            pass
        try:
            u32.DestroyWindow(win)
        except Exception:
            pass
        # 开屏窗真没了才清放行标记；否则壳会以为开屏还在播，又把自己藏起来
        try:
            os.remove(SHOW_FLAG)
        except Exception:
            pass
        # 会话标记最后清：清早了壳会在收尾淡出中途插进来
        try:
            os.remove(BUSY_FLAG)
        except Exception:
            pass
        try:
            g32.DeleteDC(mdc)
            g32.DeleteObject(bm)
        except Exception:
            pass
        log("splash exit frames=%d t_win=%s" % (n, t_win))
    return 0


if __name__ == "__main__":
    sys.exit(main())
