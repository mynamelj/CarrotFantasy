# 新对话的固定上下文

先读 README.md、docs/UPDATING.md 和 profiles/1.4.1.json，再检查当前本地版本和仓库状态。

用户最新确定的需求如下。

- 单人主题关、周赛、本地周赛、日赛、星途、糖果和收集活动启用 10 倍关内正向金币收入与全图通用炮塔射程。
- 双人合作启用自己的 10 倍关内正向金币收入与全图炮塔射程。队友炮塔使用原始射程，换区后按当前归属重算。赠送队友金币无本机冷却，每笔仍按原规则检查余额和扣款。
- 金币支出和出售退款使用原逻辑。开局金币不属于当前倍率范围。
- 使用原签名 APK 和本地热更新资源。已知重新签名的对照包会在更新阶段闪退，详细观察记录在文档中。
- 金币函数须保留定向 `jit.off(GameLayer.addGameLayerMoney, true)`。仅做几次入账检查会漏掉已经复现的长时间失效。
- 单人模式在局内建造菜单追加太阳花和水晶。原有炮塔顺序不变，已有的塔不重复添加。合作与对战不追加。

工具入口如下。

1. tools/capture_cache.py 采集目标热更新脚本和候选配置，输出到 private。
2. tools/inspect_assets.py 和 tools/inspect_bytecode.py 定位 source、prototype、常量索引和指令。
3. tools/bytecode_patch.py 控制金币、射程及赠送冷却。tools/stabilize_money.py 注入定向 JIT 修复。
4. tools/build_patch.py 按 profiles 配置重建。最新版使用 `--coop-owned-range --no-donation-cooldown --append-solo-towers`。tools/verify_patch.py 检查模式、金币、炮塔归属、赠送确认、JIT 调用和建造菜单追加。
5. tools/prepare_native_test.py 与 tools/native_coin_selftest.lua 准备本机游戏 VM 的长时间模拟入账测试。
6. patches/latest 是当前可直接安装的完整补丁目录，releases 中是同一版本的 ZIP。

版本更新后，先确认干净资源。新版本出现头部、opcode、常量、行号或控制流差异时，更新配置和必要的二进制分析。完整的原脚本 SHA 校验与结构断言通过后才生成补丁。当前工具对未知结构会拒绝继续。

对局期间先准备补丁，待结算后安装和重启。测试账号由用户在模拟器中登录。金币自测通过沙箱余额与空服务函数运行，不修改玩家实际余额。真实双人联机测试与本地 VM 自测分别记录。

APK、原始解密脚本、原生库、用户数据、账号截图和签名私钥放在 private 或仓库外。上传前暂存明确的文件清单，执行 `python tools/audit_upload.py`。任何 APK、AAB、DEX、原生库或私钥出现在暂存区时，先修正清单。
