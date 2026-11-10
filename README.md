# 豆包动态壁纸（真人化形象）

> **非官方项目。** 豆包客户端没有皮肤/插件接口，这套东西是在客户端**外面**加的一层视觉壳：不修改 `Doubao.exe`、不注入代码、不碰它的更新机制。素材是作者本人用 AI 生成的同人创作，与字节跳动无关；「豆包」名称与形象的相关权利归其所有者。本项目仅供个人学习与本地复现，请勿商用。

## 效果

- **点图标冷启动**：满屏播放约 4 秒的启动片，带原声；1.2 秒后真实界面从人物后面淡淡透出来
- **收尾**：启动片播完 → 最后一帧压住 0.3 秒 → 0.4 秒淡进常驻壁纸，全程不会闪出「两个人」
- **常驻**：壁纸贴着豆包窗口走，窗口拖到哪、缩到哪，壁纸跟着；真实 UI 以 70% 不透明度叠在壁纸上
- **切到别的程序**：壁纸层自动收起；右键托盘图标时立刻让开，豆包的「退出」菜单完整可见
- **鼠标**：完全穿透，豆包照常点击，没有任何交互损失
- **豆包已运行时再点图标**：只做普通激活，不重播开屏、不响音

## 仓库结构

```
.
├── 启动深色_clean.mp4      启动片（开屏，1920×1080 / 30fps / 4.07s）
├── 启动深色_audio.wav      启动片的音轨（PCM s16le 48k 双声道 / 4.04s）
├── 欢迎回来.m4a            启动片播完 0.5s 后响的问候语（AAC / 1.14s）
├── 常驻深色2_clean.mp4     常驻壁纸（1280×720 / 30fps / 12.13s，循环）
└── skin/
    ├── launcher.py         入口：判断冷启动还是普通激活
    ├── dsplash.py          开屏层：满屏放启动片 + 音轨，负责淡出与收尾
    ├── dshell.py           常驻层：贴窗口画壁纸，并把真实 UI 用 DWM 缩略图叠回来
    ├── install.ps1         安装：备份并重定向快捷方式
    ├── restore.py          卸载：撤层 + 还原快捷方式
    └── 一键还原.bat        双击即可复原
```

素材放在 `skin/` 的**上一级**，脚本按 `os.path.dirname(HERE)` 取，目录层级别打乱。

## 前置条件

- Windows 10 / 11（依赖 DWM，虚拟桌面/远程桌面下缩略图可能不工作）
- Python 3.8+，且 `pythonw.exe` 可用
- ffmpeg **含 ffplay**（用到 `ffmpeg`、`ffplay` 两个 exe）

## 复现前必须改的常量

仓库里的脚本是作者本机能直接跑的原样，**路径是硬编码的**。不改这几处一定跑不起来：

| # | 文件 | 常量 | 仓库里的值 | 改成 |
|---|---|---|---|---|
| 1 | `skin/launcher.py` | 第 17 行 `DOUBAO_EXE` | `C:\Users\86195\AppData\Local\Doubao\Application\Doubao.exe` | 你本机的 `Doubao.exe` |
| 2 | `skin/dshell.py` | 第 25-27 行 `FFMPEG` | WinGet 里的 `ffmpeg-9.0.2...\bin\ffmpeg.exe` | 你本机的 `ffmpeg.exe` |
| 3 | `skin/dsplash.py` | 第 27-32 行 `FFMPEG` / `FFPLAY` | 同上 | 你的 `ffmpeg.exe` / `ffplay.exe` |
| 4 | `skin/install.ps1` | 第 4 行 `$DOUBAO` | 同上 | 你的 `Doubao.exe` |
| 5 | `skin/install.ps1` | 第 6 行 `$PyDir` | `...\Programs\Python\Python38` | 你的 Python 目录（或删掉这行，让它走 `Get-Command python` 分支） |
| 6 | `skin/一键还原.bat` | 第 3 行 | `...\Python38\python.exe` | 你的 `python.exe` |
| 7 | `skin/install.ps1` + `skin/restore.py` | 快捷方式路径 | `Desktop\豆包.lnk`、`Start Menu\Programs\豆包.lnk` | 你机器上实际的 `.lnk` 路径（名字不叫「豆包」就要改） |
| 8 | `skin/dshell.py` | 第 32 行 `LW, LH` | `2160, 1368` | 按你的屏幕改（见「已知限制」） |

查找 Doubao.exe 最快的方法：在桌面快捷方式上右键 → 属性 → 看「目标」。

## 三步跑起来

```powershell
# 1. 进到 skin 目录
cd skin

# 2. 安装（备份原快捷方式，并把它们重定向到 launcher.py）
powershell -ExecutionPolicy Bypass -File .\install.ps1

# 3. 点桌面上的豆包图标（先确保豆包没在运行，否则只会走普通激活）
```

装完应该是：满屏开屏 → 界面透出 → 淡进壁纸。

**还原**：双击 `skin\一键还原.bat`。它会以 `%TEMP%\doubao_wall_stop.flag` 通知壳退出，再用 `backup\` 里的备份覆盖回原快捷方式。

## 实现原理

三层各管一段，互不耦合，靠 `%TEMP%` 下三个标记文件通信：

| 标记 | 写入方 | 用途 |
|---|---|---|
| `doubao_wall_splash_busy.flag` | launcher 起播前立，dsplash 每秒 `utime` 心跳、退出时清 | 告诉壳「开屏要来了/还在播」，覆盖开屏窗口尚未建出的空档 |
| `doubao_wall_show.flag` | dsplash 在收尾阶段写 | 放行壁纸层，让开屏淡到 0 时直接化进壁纸 |
| `doubao_wall_stop.flag` | restore.py 写 | 通知两个层主动退出 |

### 1. launcher.py — 分流

- 枚举 2048 个进程找 `doubao.exe`（用 `EnumProcesses` + `QueryFullProcessImageNameW`，不靠进程名匹配，避免误判）
- 已经在跑（哪怕窗口还没出来）→ 只 `SetForegroundWindow` 激活，起壁纸壳，**绝不重开实例**
- 真冷启动 → 写 BUSY 标记 → 起 `dsplash.py` → 等 0.15s → 起 `Doubao.exe`
- 等主窗「稳定」：同一个 hwnd 连续 0.9 秒不变才算数（启动期会有一个临时窗口，句柄随后换手）

### 2. dsplash.py — 开屏层

一个铺满全屏的分层窗口（类名 `Static`、窗口名 `DoubaoSplashLayer`），用 `UpdateLayeredWindow` 每帧推 alpha。

```
ffmpeg -i 启动深色_clean.mp4 -vf scale=SW:SH:force_original_aspect_ratio=increase:flags=lanczos,crop=SW:SH \
       -pix_fmt bgra -r 30 -f rawvideo pipe:1
```

`SW/SH` 取 `GetSystemMetrics(0/1)`，所以开屏永远铺满，不依赖写死的分辨率。视频第一帧真正上屏的那一刻才 `ffplay` 起播音轨——这样音画天然对齐，不靠延时猜。

实测时间线（4 秒启动片，122 帧）：

| 时刻 | 事件 |
|---|---|
| 0.00s | launcher 写 BUSY、起开屏、0.15s 后起豆包 |
| 0.10s | 开屏窗口出现，首帧上屏，音轨同时起播 |
| 1.00s 起 | 主窗稳定 0.6s 后，开始 1.2s 线性淡出，alpha 255 → 110，界面从人物后透出 |
| 4.07s | 视频流 EOF，最后一帧留在屏上 |
| 4.37s | 写 SHOW_FLAG 放行壁纸（=`t_end - 0.40`） |
| 4.57s | 响「欢迎回来」（=EOF + 0.5s） |
| 4.77s | 淡到 alpha 0 退出，壳接棒 |

收尾时刻不是按秒表掐的，而是由最后一帧的实际上屏时间推出来：

```python
video_end = 最后一帧上屏的时刻
t_end = max(video_end + HOLD_TAIL(0.30), max(1.0, t_win) + FADE_DUR(1.2)) + TAIL_FADE(0.40)
```

按秒表算的话，最后一帧还没吐完就开始淡出，会看到画面「跳一下」。

### 3. dshell.py — 常驻层

**（a）把视频流变成壁纸**

```
ffmpeg -stream_loop -1 -i 常驻深色2_clean.mp4 \
       -vf scale=LW:LH:force_original_aspect_ratio=increase:flags=lanczos,crop=LW:LH \
       -pix_fmt bgra -r 30 -f rawvideo pipe:1
```

主循环按 `LW * LH * 4` 字节读满一帧，`memmove` 进 `CreateDIBSection` 的位图（32bpp、`biHeight = -h` 表示 top-down），然后 `InvalidateRect` 触发 `WM_PAINT`，在 `WM_PAINT` 里 `BeginPaint` + `StretchDIBits` + `EndPaint`。

**这一步不能用 `GetDC` + `StretchDIBits` 直接画**，分层窗口下那样画完全不显示（窗口是空的），必须走 `WM_PAINT`。

**（b）让鼠标穿过**

窗口样式：

```
WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED
```

光有 `WS_EX_TRANSPARENT` 不够——跨进程实测光标仍会变成箭头/加载圈。要三件套一起上：

1. `SetLayeredWindowAttributes(win, 0, 255, LWA_ALPHA)`（常量 alpha=255，只为拿到分层窗口的穿透行为）
2. `EnableWindow(win, False)`，系统在命中测试时直接跳过
3. `WM_NCHITTEST` 返回 `-1`（`HTTRANSPARENT`）

**（c）把真实 UI 叠回来**

不截图、不复制窗口内容，直接用 DWM 缩略图合成：

```python
DwmRegisterThumbnail(壳窗, 豆包主窗, &thumb)
props.dwFlags = DWM_TNP_RECTDESTINATION | DWM_TNP_OPACITY | DWM_TNP_VISIBLE | DWM_TNP_SOURCECLIENTAREAONLY
props.opacity = 179              # 0.70
props.rcDestination = RECT(PAD, PAD, PAD + w, PAD + h)   # PAD = 10，四周留一圈壁纸
```

主窗移动/改尺寸时重设 `rcDestination`，只有位移超过 `RECT_TOL(2px)` 才重排，避免每帧抖。

**（d）什么时候藏**

每帧判断前台归属，分三档：主窗内 → 显示；豆包自己的浮层 → 立刻收起；其他程序 → 0.25s 后收起（避开输入法候选窗高速横跳）。输入法进程（`textinputhost.exe` 等）和 `WS_EX_NOACTIVATE` 装饰条要白名单排除。

## 踩过的坑（复现时大概率也会撞上）

| 现象 | 原因 | 解法 |
|---|---|---|
| 启动时没有壁纸，壳自己退了 | 启动期临时窗口句柄随后失效，被误判「豆包已关闭」 | 句柄失效先重找主窗再决定退出；认窗要求「同一 hwnd 稳定 0.9s」 |
| 开屏还没播完就冒出壁纸，屏幕里两个人 | 壳无条件 `SWP_SHOWWINDOW` 抢到置顶层 | BUSY 标记 + 把壳 `SetWindowPos` 垫到开屏窗口下面，开屏退场后再归位 TOPMOST |
| 鼠标移到豆包上变成加载圈，点不动 | 自绘窗口没泵消息，`WM_NCHITTEST` 没人应答 | 每帧 `PeekMessageW` + `TranslateMessage` + `DispatchMessage` |
| 右键托盘图标，「退出」菜单被盖住 | 托盘菜单是 `Doubao.exe` 另开的顶层窗，类名同为 `Chrome_WidgetWin_1`，被当成「仍在豆包内」 | 按 owner/面积/进程识别出「豆包浮层」，出现时立即收起 |
| 双击图标弹一个黑控制台 | `pythonw` 之外的子进程没加 `CREATE_NO_WINDOW` | 所有 `subprocess.Popen` 加 `creationflags=CREATE_NO_WINDOW` |
| 多个壁纸壳叠在一起重画 | 重复入口多次拉起 | `CreateMutexW("DoubaoWallShellMutex")`，`ERROR_ALREADY_EXISTS(183)` 直接退出 |

## 素材规格与替换

| 素材 | 分辨率 | 帧率 | 时长 | 编码 |
|---|---|---|---|---|
| 启动片 | 1920×1080 | 30 | 4.07s（122 帧） | H.264 |
| 开屏音轨 | — | — | 4.04s | PCM s16le / 48k / 双声道 |
| 常驻片 | 1280×720 | 30 | 12.13s（364 帧） | HEVC |
| 问候语 | — | — | 1.14s | AAC / 48k / 双声道 |

换素材时文件名保持一致即可，脚本按文件名取。必须注意：

- **常驻片首尾要接得上**：镜头运动方向一致或构图静止，否则循环点会「跳」。建议 8–15 秒、静止或缓慢单向运动
- **启动片不要太长**：超过 5 秒用户会等得不耐烦，而且这段时间豆包界面是「被压着」的
- 从视频里重新导出音轨：

```powershell
ffmpeg -i 新启动.mp4 -vn -ac 2 -ar 48000 -c:a pcm_s16le 启动深色_audio.wav
```

- 若原始素材带平台水印，先抹掉再进 ffmpeg：

```powershell
ffmpeg -i 原始.mp4 -vf "delogo=x=30:y=24:w=212:h=70" -c:v libx264 -crf 20 -an 启动深色_clean.mp4
```

## 已知限制

- 只接管**桌面**和**开始菜单**里的快捷方式。任务栏固定图标不经过启动器，需要手动再拖一次
- 豆包升级后如果重建了桌面图标，劫持会失效，重跑一次 `install.ps1`
- `dshell.py` 的渲染尺寸 `LW, LH = 2160, 1368` 是按作者 2160×1440@150% 的屏幕写死的。换分辨率后壁纸会被拉伸或裁边（不会崩，但比例会歪）。改这两行即可
- 豆包主窗右上角的 X 需要点两次才能关（未解决）
- 依赖 DWM 缩略图，远程桌面/部分虚拟机环境下缩略图可能返回失败（`DwmRegisterThumbnail` 的 HRESULT 会打日志）
- 不处理多显示器：主窗拖到副屏时，壳跟随用的是物理坐标，副屏 DPI 不同会错位

## 卸载

```powershell
# 双击 skin\一键还原.bat，或手动：
python skin\restore.py
```

`backup\` 里的两个 `.lnk` 是原快捷方式的备份，**还原成功之前别删**。

## License

- 代码（`skin/` 下所有脚本）：MIT
- 素材（4 个视频/音频）：作者二创作品，随仓库分发仅供个人非商业复现，转载或再分发请注明来源

---

*本项目是作者在自己机器上一边踩坑一边调出来的，代码保留了当时的原样（包括硬编码路径和调试用的环境变量开关），目的是让整个排查过程可追溯。`DB_SHELL_MOUSE=1`、`DB_SPLASH_HOLD` 是留给调试的。*
