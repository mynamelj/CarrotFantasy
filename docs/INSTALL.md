# 补丁使用教程

当前方案是在已安装原版游戏的 MuMu 实例里，额外安装本地热更新补丁。单独安装 APK 不会自动带上补丁功能。仓库不提供 APK 安装包。

| 模式 | 当前效果 |
| --- | --- |
| 单人主题、周赛、本地周赛、日赛、星途、糖果、收集活动 | 10 倍关内正向金币收入，加全图通用炮塔射程 |
| 双人合作 | 自己的关内正向金币收入 10 倍，自己的炮塔全图射程，队友炮塔原始射程，赠送金币无本机冷却 |

建造、升级支出、出售退款和开局金币保持原逻辑。金币倍率以顶部余额的实际增加值为准，飘字可能显示原掉落数。

## 1. 准备游戏和补丁

1. 在目标 MuMu 实例中安装对应的原签名 `保卫萝卜4_1.4.1.apk`，打开游戏完成官方热更新，再退出游戏。当前补丁同时校验 APK 和热更新脚本，其他渠道包或后续更新不保证匹配。
2. 在该实例设置中启用 Root，按提示重启实例。请先完成当前对局，安装补丁会结束游戏进程。
3. 下载 [补丁 ZIP](https://github.com/mynamelj/CarrotFantasy/raw/refs/heads/main/releases/CarrotFantasy4_1.4.1_MuMu-coop-owned-range-no-cooldown-patch.zip)，完整解压，例如解压到 `D:\CarrotPatch`。

解压后的目录应同时包含以下内容，不能只复制安装脚本。

```text
D:\CarrotPatch\
  Apply-CarrotPatch.ps1
  manifest.json
  payload\
```

如果下载的是整个仓库，安装脚本位于仓库的 `patches\latest` 目录。使用现成补丁只需 Windows PowerShell 和 MuMu 自带的 ADB，无需 Python 或 Git。

## 2. 查询目标实例的 ADB 端口

先启动目标模拟器，再打开 Windows PowerShell 执行下面的命令。这里的 MuMu 安装路径是本机示例，其他电脑需改成自己的实际路径。

```powershell
$manager = 'D:\Software\MuMuPlayer\nx_main\MuMuManager.exe'
$adb = 'D:\Software\MuMuPlayer\nx_main\adb.exe'
& $manager info -v all
```

按输出里的 `name` 找到目标实例，读取同一实例的 `adb_host_ip` 和 `adb_port`。例如以下字段对应“MuMu安卓设备-2”。

```json
{
  "name": "MuMu安卓设备-2",
  "adb_host_ip": "127.0.0.1",
  "adb_port": 16448
}
```

实际输出还会包含其他字段。将 IP 和端口用冒号连接，得到 `127.0.0.1:16448`。端口不是所有实例统一使用的固定值，不要直接套用示例；更换、新建实例或迁移环境后重新查询。未启动的实例可能不显示端口。

## 3. 连接并确认 Root

继续在同一个 PowerShell 窗口执行，将 serial 换为上一步查到的地址。

```powershell
$serial = '127.0.0.1:16448'
& $adb connect $serial
& $adb devices
& $adb -s $serial root
& $adb -s $serial shell id -u
```

`devices` 中目标地址应显示为 `device`，最后的 `id -u` 应输出 `0`。如果不是 `0`，先检查目标实例的 Root 设置并重启，再重试。存在多个设备时，后续命令始终保留 `-s $serial`，避免选错实例。

## 4. 安装补丁

将 patchDir 换为含有 `Apply-CarrotPatch.ps1` 的实际目录。

```powershell
$patchDir = 'D:\CarrotPatch'
powershell -NoProfile -ExecutionPolicy Bypass -File "$patchDir\Apply-CarrotPatch.ps1" -Serial $serial -Adb $adb
```

安装器会检查 APK 与目标脚本的 SHA-256，备份原始脚本，写入补丁后再次校验。看到成功信息后执行以下命令，再手动打开游戏。

```powershell
& $adb -s $serial unroot
```

如果提示 `Files are already in the requested state.`，表示目标文件已经是该补丁版本，无需重复写入。`unroot` 让 ADB 恢复普通权限，不会删除已写入的补丁。

安装完成后无需持续连接电脑，也无需每次打开游戏都安装一次。补丁只作用于这一个模拟器实例；其他实例和手机需要各自处理。

## 5. 恢复原脚本

在同一个 PowerShell 窗口中执行下列命令，变量沿用上文。恢复也会结束游戏，请先完成对局。

```powershell
& $adb -s $serial root
& $adb -s $serial shell id -u
```

确认输出 `0` 后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$patchDir\Apply-CarrotPatch.ps1" -Serial $serial -Adb $adb -Restore
```

看到恢复成功信息后执行 `& $adb -s $serial unroot`，再打开游戏。恢复依赖首次安装时保存在游戏私有目录中的原脚本备份。

## 常见问题

### 安装到手机就能生效吗？

单独安装 APK 不会生效。普通未 Root 手机无法使用当前流程写入游戏私有脚本。已 Root 手机理论上可以适配，但现有安装器要求 ADB shell 直接拥有 Root 权限，没有处理手机常见的 `su` 提权方式，手机端尚未验证。当前已验证的平台是 MuMu。

### 找不到 adb.exe 或 MuMuManager.exe？

先确认 MuMu 的实际安装目录，再修改第 2 步的两个路径。本教程中的 `D:\Software\MuMuPlayer\nx_main` 仅为当前机器路径。

### 提示 APK 或更新文件不匹配？

先确认原签名 APK、渠道和官方热更新是否与补丁对应。版本号相同也可能存在不同的热更新内容。不要跳过校验或强行覆盖，按 [更新适配步骤](UPDATING.md) 采集并适配当前版本。

### 游戏更新、清数据或重装后怎么办？

这些操作可能替换或删除补丁及原脚本备份。完成官方更新后重新检查；仍匹配当前补丁时可以重新安装，内容或版本变化时先适配。详细验证方法见 [验证与故障排查](VALIDATION.md)。
