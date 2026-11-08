# 保卫萝卜 4 本地补丁

本仓库保存 v1.4.1 最新补丁，以及脱离原聊天也能使用的采集、分析、重建和验证方法。

| 模式 | 关内正向金币收入 | 炮塔通用射程 |
| --- | --- | --- |
| 经典主题、周赛、本地周赛、日赛、星途、糖果、收集活动 | 10 倍 | 覆盖全图 |
| 双人合作 | 自己的收入 10 倍 | 游戏原始射程 |

倍率作用于关内收入。开局金额、建造与升级支出、出售退款按原逻辑处理。双人合作只修改本机自己的金币入口。当前实现使用原签名 APK 加模拟器本地热更新脚本。

## 使用最新版

可下载仓库中的 [最新版补丁 ZIP](releases/CarrotFantasy4_1.4.1_MuMu-coop-gold-only-patch.zip)，解压后运行安装脚本。也可以直接使用 [patches/latest](patches/latest)。

以当前机器的 MuMu安卓设备-2 为例，ADB 地址是 `127.0.0.1:16448`。其他机器应先通过 MuMuManager 的 `info -v all` 查询实际地址。

```powershell
$adb = 'D:\Software\MuMuPlayer\nx_main\adb.exe'
$serial = '127.0.0.1:16448'
& $adb connect $serial
& $adb -s $serial root
& $adb -s $serial shell id -u
powershell -NoProfile -ExecutionPolicy Bypass -File .\patches\latest\Apply-CarrotPatch.ps1 -Serial $serial -Adb $adb
& $adb -s $serial unroot
```

`id -u` 应输出 `0`。若 Root 不可用，在目标 MuMu 实例设置中启用 Root 并重启后再执行。安装器会结束游戏进程，安装前先完成当前对局。安装完成后重新打开游戏。

目标实例需要已安装本地原版 `保卫萝卜4_1.4.1.apk` 并完成官方热更新。安装器会核对原版 APK 和每个目标脚本的 SHA-256，支持从此前几版补丁升级，首次修改前保存原脚本备份。可用同一命令加 `-Restore` 恢复原脚本。

## 游戏更新后

先读 [更新适配步骤](docs/UPDATING.md)，再按需查阅 [资源与字节码说明](docs/REVERSE_ENGINEERING.md) 和 [验证与故障排查](docs/VALIDATION.md)。根目录的 [AGENTS.md](AGENTS.md) 为新对话提供固定需求和工作入口。

可将下面这段文字直接发给没有历史上下文的新对话。

> 请阅读 https://github.com/mynamelj/CarrotFantasy 的 AGENTS.md 和 docs/UPDATING.md。目标是适配本地最新保卫萝卜4更新。单人模式为10倍关内金币收入加全图射程，双人合作仅保留自己10倍关内金币收入和原始射程。先核对当前版本、干净脚本和模式，再生成带校验和备份的补丁，保留金币函数的定向JIT修复，并完成宿主回归及游戏原生VM长时间入账测试。APK和原始资源保存在private目录，提交前运行tools/audit_upload.py。请在完成当前对局后再重启实例。

## 从干净脚本重建

Python 3.10 及以上版本可运行构建工具，语义检查另需 `requirements.txt` 中的 LuaJIT 运行时。

```powershell
python -m pip install -r requirements.txt
python tools/capture_cache.py --adb $adb --serial $serial --version 1.4.1 --output private/clean-cache --use-backups
python tools/build_patch.py --profile profiles/1.4.1.json --input private/clean-cache --output build/rebuilt
python tools/verify_patch.py build/rebuilt --baseline patches/latest
```

这里的 `--use-backups` 用于已经安装过本仓库补丁且存在原脚本备份的实例。在全新干净实例上采集时省略此参数。`private` 和 `build` 是本地工作目录。上传内容由 `.gitignore` 和发布前检查脚本共同限制。

最新补丁于 2026-11-08 在 MuMu安卓设备-2 安装。用户确认过双人合作的本机 10 倍金币生效，并要求移除会影响双方的全图射程。最终版本已完成模式检查和文件校验，验证边界见验证文档。
