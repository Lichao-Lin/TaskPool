# TaskPool / 全息任务控制台

完全离线的 Windows 个人任务管理程序。任务、积分、奖励、每日安排保存在本地 SQLite 数据库中。

## 下载与安装

前往 [最新 Release](https://github.com/Lichao-Lin/TaskPool/releases/latest)，只需下载 **TaskPool-Setup-2.0.0-windows-x64.exe**，运行安装包即可。无需 Python，无需解压。

安装后自动创建桌面与开始菜单的 TaskPool 快捷方式。程序安装在当前用户的 `%LOCALAPPDATA%\Programs\TaskPool`，无需管理员权限。可从 Windows「已安装的应用」卸载。卸载仅删除程序与快捷方式，保留个人数据。

## v2.0 功能

- 黑色全息控制台：左侧奖励圆环、中间任务树、右侧 Daily Routine，下方仅两个紧凑输入区。
- 奖励以无边框小字号文字沿圆环外侧依次排列，文字随角度旋转并向外延伸，不对称铺满；每页最多 12 份，未用圆弧留空，支持翻页与完整详情。
- 创建、编辑、删除、达成任务与兑换奖励均在主页面操作，无确认弹窗。错误显示在底部状态栏。
- 页面内撤销最近 30 次操作（Ctrl+Z），同时恢复数据、完成状态与积分；退出、跨日或切换数据库后清空撤销记录。
- 选中未完成任务，点「+ 子任务」创建嵌套子任务。子任务独立计分，全部完成后才能完成父任务。
- 未完成任务在截止前 48 小时标红，逾期继续标红；已完成任务变灰。
- 工作日、休息日分别保存每日安排，直接输入、修改、打勾与删除。修改即时保存。
- 每日勾选按本地日期记录，午夜自动刷新，累计完成次数保留。同一天重复勾选不重复计数，取消勾选撤销当天次数。
- 界面与存储设置在页面内展开：三套预设色、自定义背景/文字/强调色（#RRGGBB），粘贴本地图片路径使用背景图片（PNG/JPG/WebP）。

任务需要内容、产出、截止时间（YYYY-MM-DD HH:MM）与正整数积分。双击任务可直接编辑；已完成任务的积分不能修改。删除父任务会同时删除子任务，并撤销相关任务所得积分，误删可立即撤销。历史奖励兑换仍保留，余额可能因此成为负数。

## 数据与升级

默认数据：`%LOCALAPPDATA%\TaskPool\data\taskpool.db`。原版自定义的数据路径也会继续读取，升级自动扩展数据库结构并保留原任务、奖励、积分和主题色。

设置中的「数据文件夹」支持粘贴路径迁移：空目录复制当前数据库；已有 `taskpool.db` 则直接切换读取，不覆盖。仅建议同时运行一个程序窗口。备份时退出程序并复制数据库文件。

## 开发与打包

Python 3.10+，图片支持需要 Pillow。运行 `python app.py`。

```powershell
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
./build.ps1
```

打包依赖 Inno Setup 6（ISCC.exe），可通过 `./build.ps1 -Python <python路径> -ISCC <ISCC路径>` 指定工具。
推送 `v*` 标签后，GitHub Actions 测试并打包，Release 只附带 Windows 安装包（GitHub 自动提供的源码归档仍会显示）。

MIT License。
