# TaskPool 任务积分池

一款完全离线、数据只保存在电脑本地的个人任务管理程序。把任务拆成明确产出，完成后获得积分，再用积分兑换自己定义的奖励。

## 功能

- 任务内容、产出要求、截止时间、任务积分
- 自定义奖励名称、说明和兑换积分
- 完成任务自动入账，兑换奖励自动扣分
- 任务列表、奖励池、余额和完成统计集中展示
- 完成/兑换动效与自定义强调色
- SQLite 本地持久化，数据文件夹可由用户自由选择
- 无账号、无服务器、无遥测

## Windows 直接使用

在仓库的 **Releases** 页面下载 `TaskPool-windows-x64.zip`，解压后双击 `TaskPool.exe`。

首次运行默认保存在：`%LOCALAPPDATA%\TaskPool\data\taskpool.db`。点击右上角“数据文件夹”可以选择任意本地文件夹；如果新文件夹为空，程序会自动复制现有数据，如果已有数据库则可以安全切换且绝不覆盖。升级或替换程序不会删除数据；需要备份时，退出程序后复制 `taskpool.db` 即可。

## 从源码运行

需要 Python 3.10 或更高版本，运行：

```powershell
python app.py
```

程序运行只使用 Python 标准库。执行测试：

```powershell
python -m unittest discover -s tests -v
```

## 本地打包

```powershell
./build.ps1
```

脚本会安装 PyInstaller，并在 `dist/TaskPool.exe` 生成单文件 Windows 程序。

## 发布新版本

推送形如 `v1.0.0` 的 tag，GitHub Actions 会自动构建 Windows x64 压缩包并创建 Release：

```powershell
git tag v1.0.0
git push origin v1.0.0
```

## 许可

MIT License
