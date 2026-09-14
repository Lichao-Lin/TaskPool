# Termxk

本地个人任务、积分、奖励与每日安排控制台。原 TaskPool 的升级版本，继续读取同一份 SQLite 数据。

## 下载与安装

在 [GitHub Releases](https://github.com/Lichao-Lin/TaskPool/releases/latest) 下载 **Termxk-Setup-3.0.0-windows-x64.exe**，运行安装包。安装自动创建桌面与开始菜单的 **Termxk** 快捷方式，使用机器人头部图标，并替换旧的 TaskPool 快捷方式。

支持 Windows 10/11 x64，无需 Python。安装器检测 Microsoft WebView2 Runtime，仅在缺少时自动安装，此时需要联网。安装完成后日常任务管理可完全离线。旧版本安装路径会被沿用；新安装默认在 `%LOCALAPPDATA%\Programs\Termxk`。

## v3.0 交互

- 高 DPI 清晰渲染，普通界面不模糊；全局字号略增大，奖励名称后紧接积分，悬停不会变白。
- 左侧奖励圆环更宽，右侧 Daily Routine 更窄；提示移至左上角，输入区固定在最下方。
- 外围奖励支持拖动、滚轮和左右方向键旋转，中心积分保持固定；Home 键复位。不再悬停放大或模糊其他区域。
- 奖励无边框、沿圆周连续向外排列，每页 14 份，未使用角度留空。长名称可点击查看完整详情。
- 点击任务前方勾号完成任务，获得积分并从主列表消失；兑换奖励后同样移入右上角「活动日志」。日志支持类型筛选与搜索。
- 新建、编辑、删除、兑换和撤销都在页面内操作，无反复确认弹窗。最多撤销最近 30 次操作；跨日、退出或切换数据库后清空撤销历史。
- 子任务独立计分；需先完成子任务才能完成父任务。截止前 48 小时及逾期未完成任务标红。
- 工作日和休息日分别维护 Daily Routine，当日勾选独立记录、累计次数保留。取消当天勾选会减去当天一次。
- 设置页列出背景、文字和光效色板，并可调面板透明度；透明度不影响文字。支持拖入背景图片或输入本地图片路径。

## 数据

数据默认仍保存在 `%LOCALAPPDATA%\TaskPool\data\taskpool.db`，原版自定义路径也继续生效。改名不会另建空数据库。升级保留旧任务、奖励、积分和每日记录；已有已完成任务和已兑换奖励自动归入日志。

数据文件夹切换时，空目录复制当前数据库，已有数据库直接读取不覆盖。卸载保留个人数据。删除任务及子任务会撤回关联积分，历史兑换扣分保留；误删可立即撤销。

## 开发

Python 3.10+，依赖见 `requirements-build.txt`。前端为本地 HTML/SVG，桌面宿主使用 pywebview / WebView2；SQLite 与 UI 分离。

```powershell
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python app.py
./build.ps1
```

`build.ps1` 使用 PyInstaller 和 Inno Setup 6 生成安装包，支持 `-Python` 与 `-ISCC` 参数指定工具路径。推送 `v*` 标签自动测试和发布安装包。

机器人图标基于用户提供的图片提取头部。代码沿用 MIT License；第三方图像权利归原权利人。
