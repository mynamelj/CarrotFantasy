# 验证范围和故障排查

## 已有结果

| 检查 | 记录 |
| --- | --- |
| 金币入口实际入账 | 经典已通关第 10 关中，三笔 40 金币均实际增加 400 |
| 旧版连续调用 | 从约第 384 次附近出现倍率失效，见 evidence/native-coin-before.log |
| 函数级 JIT 处理 | 七种单人模式各 500 次零偏差，见 evidence/native-coin-after.log |
| 加入合作 | 八种模式各 500 次零偏差，见 evidence/native-coop-selftest.log |
| 真实合作对局 | 用户确认本机金币倍率生效，同时报告全图射程影响双方 |
| 最新合作范围 | 按用户要求恢复合作原始射程，金币模块文件字节保持已生效版本；模式回归通过并已安装 |

最后一项的射程条件已经通过本地验证。修改后的新双人对局尚无进一步用户实测记录，后续应按实际对局补充。

## 宿主检查

```powershell
python tools/verify_patch.py patches/latest
```

检查会核对文件 SHA、可加载的 bytecode、全部模式、正收入、负支出、出售退款、未知模式，以及根函数中对指定金币方法的 jit.off 调用。射程检查明确要求合作模式返回原值。

如果本地已有干净脚本，可重建并追加 `--baseline patches/latest` 做 manifest 与 payload 逐字节比较。不同 zlib 运行时可能生成不同压缩字节，因此记录 Python 和 zlib 版本；更换工具链导致的压缩差异需要与内容差异分开核查。

## 原生 VM 长时间测试

tools/native_coin_selftest.lua 在游戏自己的 LuaJIT 中测试实际打补丁的方法。它给该方法设置临时沙箱环境，使用假的余额、工具栏和服务对象，结束后恢复环境，并写出各模式误差数。它不会创建真实关卡或发出合作网络请求。

在新测试目录准备临时文件。

```powershell
python tools/prepare_native_test.py --profile profiles/1.4.1.json --bundle patches/latest --apk private/original.apk --output private/native-probe
```

输出目录中的 probe 是临时测试资源，restore 是对应的正式补丁文件，probe-manifest.json 列出安装路径和需要额外清理的 MainScene 文件。工具先核对本地原 APK SHA 并检查注入 Lua 源码语法。

以下流程适用于当前 v1.4.1，示例变量承接 README 中的 adb 和 serial。先完成当前对局。所有临时路径都在该游戏的缓存根下。

```powershell
$root = '/data/user/0/com.feiyu.luobo4/files/hotupdate/1.4.1'
$probe = Get-Content private/native-probe/probe-manifest.json -Raw | ConvertFrom-Json
$uidGroup = (& $adb -s $serial shell "stat -c '%u:%g' /data/user/0/com.feiyu.luobo4/files").Trim()

# 新增的 MainScene 路径必须确认为不存在。已有文件应先保存并改为恢复它。
foreach ($relative in $probe.extra_paths) {
    & $adb -s $serial shell "test -e '$root/$relative'"
    if ($LASTEXITCODE -eq 0) { throw "Existing bootstrap path requires its own backup: $relative" }
}

& $adb -s $serial shell am force-stop com.feiyu.luobo4
$probeRoot = (Resolve-Path private/native-probe/probe).Path
foreach ($file in Get-ChildItem $probeRoot -Recurse -File) {
    $relative = $file.FullName.Substring($probeRoot.Length + 1).Replace('\', '/')
    $target = "$root/$relative"
    $parent = $target.Substring(0, $target.LastIndexOf('/'))
    & $adb -s $serial push $file.FullName /data/local/tmp/carrot-native-probe
    if ($LASTEXITCODE -ne 0) { throw 'Probe upload failed' }
    & $adb -s $serial shell "set -e; mkdir -p '$parent'; cat /data/local/tmp/carrot-native-probe > '$target'; chown '$uidGroup' '$target'; chmod 600 '$target'; restorecon '$target'"
    if ($LASTEXITCODE -ne 0) { throw 'Probe installation failed' }
}
& $adb -s $serial shell monkey -p com.feiyu.luobo4 -c android.intent.category.LAUNCHER 1
```

进入主界面后读取 `/data/user/0/com.feiyu.luobo4/files/.carrot_coin_selftest.log`。八种模式均应出现 `errors=0`，并出现 `native-test=true`。全局 `jit=true` 是正常输出，因为补丁使用函数级开关。联机网络行为由后续真实对局验证。

完成后退出游戏，把 restore 中的文件按相同相对路径写回并恢复属主、模式和 SELinux 标签。按 probe-manifest.json 的 extra_paths 清理本次新增的 MainScene 文件，移走自测日志并删除 `/data/local/tmp/carrot-native-probe`。重新运行正式补丁安装器核对所有 SHA，再重启游戏，最后执行 adb unroot。

## 真实游戏检查

记录进入关卡时的金币余额，分别触发普通击杀、障碍物掉落、正向奖励、建造、升级和出售，比较顶部余额差值。飘字可能仍显示原掉落数，因此用余额确认倍率。继续运行到多波之后，再重新进入其他模式检查。

双人合作确认本机实际余额按 10 倍增加，自己的和对方炮塔都使用正常射程。区分本机显示、对方显示以及服务器同步结果。当前项目没有验证所有服务器版本的判定规则。

## 已知陷阱

- 同一个版本号下出现多个热更新目录。金币模块和炮塔模块可能来自不同目录，应核对全部实际候选。
- 原始文件和补丁文件混用。firstline 被剥离的函数可能已经修改，应读取备份或重新采集干净实例。
- 仅改 APK 内资源。官方热更新会通过私有缓存覆盖加载路径。
- 只做短时间倍率测试。金币方法的 JIT 问题在连续运行后才复现。
- 以全局模式代替双方身份分析。合作模式中每个客户端同时模拟双方炮塔，通用射程变更曾影响双方。
- 在注入 Lua 源码时丢失反斜杠。prepare_native_test.py 会先编译检查源码，避免字符串换行造成启动错误。

## 重签闪退的观察边界

本地原版可完成更新进入登录页。只重新签名而未改玩法的对照包，与修改 APK 一样在更新阶段崩溃，日志落在 libgame.so 释放场景节点的路径。替换为原签名 APK 加本地热更新补丁后可启动。

这些对照支持使用当前本地资源方案。签名变化触发该路径的底层机制没有进一步定性，不能仅据此断言某个具体服务器或反篡改模块的实现。
