# 游戏更新后的适配步骤

## 准备当前环境

使用一个独立 MuMu 实例安装本地原签名 APK，完成官方更新并进入登录页。版本号相同也可能有新热更新目录，因此同时核对 APK SHA、缓存目录和脚本 SHA。

```powershell
$manager = 'D:\Software\MuMuPlayer\nx_main\MuMuManager.exe'
$adb = 'D:\Software\MuMuPlayer\nx_main\adb.exe'
& $manager info -v all
$serial = '127.0.0.1:16448'
& $adb connect $serial
& $adb -s $serial shell dumpsys package com.feiyu.luobo4
& $adb -s $serial root
& $adb -s $serial shell id -u
```

当前包名为 `com.feiyu.luobo4`。缓存根目录是 `/data/user/0/com.feiyu.luobo4/files/hotupdate/<版本号>`。MuMu 的 Root 设置可能需要重启后才生效。

## 采集并定位目标

下面的 `1.4.1` 是示例。适配新版时改为从安装信息确认的版本，并选一个新的本地输出目录。

```powershell
python tools/capture_cache.py --adb $adb --serial $serial --version 1.4.1 --output private/capture-new
python tools/inspect_assets.py private/capture-new --contains gamescene/GameLayer.lua > private/game-layer-index.json
python tools/inspect_assets.py private/capture-new --contains tower/Tower.lua > private/tower-index.json
```

采集器只保存目标脚本和候选配置。`candidate-profile.json` 包含实际 APK SHA、脚本 SHA、缓存相对路径和候选 prototype 行号。已安装补丁的旧实例可用 `--use-backups` 读取 `.carrot-original-<版本号>` 中保存的原脚本。原备份属于对应热更新路径，新更新应优先在干净实例采集。

APK 内原始脚本可辅助定位来源。

```powershell
python tools/inspect_assets.py private/original.apk --contains gamescene/GameLayer.lua > private/apk-game-layer.json
```

脚本文件名是数字散列，源文件名保留在解出的 LuaJIT chunkname 中。缓存可能有多个相同源文件，当前 profile 同时覆盖两个 GameLayer 副本。保留全部会参与搜索的目标副本，并核对缓存搜索优先级。

## 校对 prototype 和常量

`inspect_bytecode.py` 依赖 `lupa.luajit21`，只加载 bytecode 以读取结构，不调用游戏函数。

```powershell
python -m pip install -r requirements.txt
python tools/inspect_bytecode.py private/capture-new/42d940292c5e7c5e44e182eaaf84b7fa/src/2859421969/4221989431 --line 3563 > private/money-detail.json
```

这条命令的散列路径和 `3563` 仅适用于已知 v1.4.1 样本。新版应先从索引找行号，再检查常量表和原始指令。

| 目标方法 | 当前原型形状 | 定位线索 |
| --- | --- | --- |
| GameLayer.addGameLayerMoney | 5 参数、164 条指令、12 个寄存器槽 | money、addValue、updateMoney、MONEY_CHANGE_TOWER_SELL |
| Tower.setShootRange | 1 参数、68 条指令、10 个寄存器槽 | Tower:setShootRange、range、scale、shootRange、setValue |

金币函数中 `_gl`、`playerGameMode`、`gameMode` 和出售类型的索引直接参与补丁。当前索引依次是 1、13、14、33、34，其中最后两个是 moneyChangeType 与 MONEY_CHANGE_TOWER_SELL。必须逐项核实。

射程补丁插入到原第 40 条指令之后。原第 40 条是 `MULVV r7,r3,r7`，第 41 条是 `CALL r4,1,3`。符合单人模式或合作炮塔归属条件时，补丁把传给 setValue 的 r7 改为 4096。当前目标函数中没有跳转。若新版在插入点前后新增跳转，须重新计算跨越插入点的分支目标。

校对 `Tower.setOwnerID` 的第 608 行原型与换区调用，确认归属改变后可以安全重算射程。核对两份 `GameLayer` 的赠送确认函数，当前行号为 5259 和 5269。赠送确认补丁删除 `coin_cd` 的读取和 `startCoolingDown` 调用，保留原赠送入口和关闭弹窗逻辑。版本变化时更新 `DONATION_CONFIRM_LINES` 和对应指令断言。

检查金币模块根函数仍通过 `RET1` 返回类对象，确认可用的临时寄存器和常量索引。根函数末尾会调用 `jit.off` 禁止金币方法热编译。

## 生成新版 profile

将人工核实后的候选配置复制成 `profiles/<版本号>.json`。保留 `version`、`package`、`apk`，每个文件填写 `path`、`kind`、`firstline`、`original` 和 `previous`。

`previous` 仅列入本项目确实发布过、允许原地升级的脚本 SHA。缓存散列目录有变化时，新路径与旧路径分别处理。`bootstrap_assets` 只服务于可选的原生 VM 诊断，须按新 APK 中 MainScene 的实际数字文件路径更新。

当前补丁结构由 tools/bytecode_patch.py 实现，严格断言原型形状。新版本结构变化时，先更新指令位置、常量和对应回归检查，再构建。原始输入 SHA 不符时先确认采集来源。

## 构建与验证

```powershell
python tools/build_patch.py --profile profiles/1.4.1.json --input private/capture-new --output build/new-patch --coop-owned-range --no-donation-cooldown
python tools/verify_patch.py build/new-patch
```

输出包含 payload、manifest 和安装器，并同时生成 `build/new-patch.zip`。构建工具会先检查全部原脚本 SHA，再进行转换。输出目录须为空。运行 Python 时保留默认断言设置。

重建已知 v1.4.1 时可追加逐字节比较。

```powershell
python tools/verify_patch.py build/new-patch --baseline patches/latest
```

新版本还须按 [验证文档](VALIDATION.md) 执行游戏原生 VM 长时间入账检查，随后检查真实单人关卡和用户同意测试的双人对局。每次记录金币余额的实际差值，区分飘字与余额。

## 安装和发布

先完成当前对局，再执行新构建目录中的 Apply-CarrotPatch.ps1。安装器核对整个原 APK SHA 与各文件 SHA，写入时保留文件元数据并执行 restorecon，原脚本位于 `.carrot-original-<版本号>`。如果中途失败，游戏保持退出状态；可以修正问题后重试，或用同一安装器加 `-Restore` 恢复。

完成验证后更新 patches/latest、releases、profile、README 和验证记录。发布前暂存明确的目录并执行审计。

```powershell
git add .gitignore .gitattributes AGENTS.md README.md requirements.txt docs profiles tools patches releases evidence
python tools/audit_upload.py
git diff --cached --stat
```

记录这次实测范围和仍待确认的联机行为，再提交到仓库。private 和 build 留在本地。
