# -*- coding: utf-8 -*-
"""壁纸总开关：翻转 skin\state.txt，并让当前正在跑的壁纸层立刻跟着变

用法：
    双击 壁纸开关.bat        —— 在「开」和「关」之间切换
    或 python switch.py on   —— 强制开
    或 python switch.py off  —— 强制关

状态是持久化的：state.txt 里写 off，之后每次点图标启动都走原版豆包，
不会再冒出壁纸；写 on 或删掉这个文件就恢复壁纸。
"""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.txt")
STOP = os.path.join(os.environ.get("TEMP", "."), "doubao_wall_stop.flag")
SHELL_SCRIPT = os.path.join(HERE, "dshell.py")
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

DETACHED = 0x00000008
CREATE_NEW_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.FindWindowW.restype = wintypes.HWND
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]


def read_state():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            return f.read().strip().lower()
    except OSError:
        return ""


def write_state(v):
    with open(STATE, "w", encoding="utf-8") as f:
        f.write(v + "\n")


def shell_hwnd():
    return u32.FindWindowW("DoubaoWallShell", None)


def wait_shell_gone(seconds=6.0):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if not shell_hwnd():
            return True
        time.sleep(0.2)
    return False


def main():
    arg = sys.argv[1].strip().lower() if len(sys.argv) > 1 else ""
    cur = read_state()

    if arg in ("on", "off"):
        new = arg
    else:
        new = "on" if cur == "off" else "off"

    write_state(new)

    if new == "off":
        try:
            open(STOP, "w").close()      # 让正在跑的壳主动退出
        except Exception as e:
            print("写停止标记失败：%r" % (e,))
        if shell_hwnd():
            gone = wait_shell_gone()
            print("壁纸已关闭" + ("，当前壁纸层已撤下。" if gone else
                                   "；壁纸层 6 秒内没退出，稍后再看或手动结束 pythonw.exe。"))
        else:
            print("壁纸已关闭（当前本来就没在跑）。")
        print("之后每次点图标启动，都是原版豆包界面，不会再出壁纸。")
    else:
        print("壁纸已开启。")
        if shell_hwnd():
            print("壁纸层已经在跑，无需重启。")
        else:
            p = subprocess.Popen(
                [PYW if os.path.exists(PYW) else sys.executable, SHELL_SCRIPT],
                creationflags=DETACHED | CREATE_NEW_GROUP | CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True)
            time.sleep(1.5)
            if shell_hwnd():
                print("已立刻给当前豆包窗口挂上壁纸。")
            else:
                print("豆包现在没在运行（或还没窗口），下次点图标启动就会带上壁纸。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
