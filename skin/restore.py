# -*- coding: utf-8 -*-
"""一键还原：撤掉壁纸层/开屏层，并把快捷方式还原成原版"""
import ctypes, os, shutil, time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
Bak = os.path.join(HERE, "backup")
STOP = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_stop.flag")
TARGETS = [
    (os.path.join(os.environ["USERPROFILE"], "Desktop", "豆包.lnk"), "doubao-desktop.lnk"),
    (os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu",
                  "Programs", "豆包.lnk"), "doubao-startmenu.lnk"),
]

u32 = ctypes.WinDLL("user32")
u32.FindWindowW.restype = wintypes.HWND
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]


def main():
    open(STOP, "w").close()
    t0 = time.time()
    while time.time() - t0 < 5:
        if not u32.FindWindowW("DoubaoWallShell", None) and \
           not u32.FindWindowW("Static", "DoubaoSplashLayer"):
            break
        time.sleep(0.2)
    try:
        os.remove(STOP)
    except Exception:
        pass

    n = 0
    for path, bakname in TARGETS:
        bak = os.path.join(Bak, bakname)
        if os.path.exists(bak):
            shutil.copy2(bak, path)
            print("还原快捷方式：%s" % path)
            n += 1
    if not n:
        print("没有找到备份，快捷方式未改动")
    print("壁纸层已撤下")


if __name__ == "__main__":
    main()
