# 当前资源和字节码结构

以下参数来自本地保卫萝卜4 v1.4.1 样本及原生 VM 验证。profile 固定了原 APK SHA 和三份原脚本 SHA。未来版本以重新采集到的文件为准。

## 资源容器

APK 脚本位于 `assets/src/<数字目录>/<数字文件>`。官方热更新脚本位于应用私有目录的 `files/hotupdate/1.4.1/<32位十六进制目录>/src/...`。源文件名保留在解出的 chunkname 中。

| 偏移 | 长度 | 当前含义 |
| --- | --- | --- |
| 0 | 4 | `ff db ff ee` |
| 4 | 4 | 小端整数 `0x66` |
| 8 | 4 | 解压后数据的 CRC32 |
| 12 | 4 | 原头部中的保留字段 |
| 16 | 4 | 解压后字节数 |
| 20 | 余下数据 | 经过稀疏按字 XOR 的 zlib 数据 |

asset_codec.py 保留原始 20 字节头部，更新 CRC32 与长度，再压缩并按相同规则 XOR。密钥流由 1024 个初始零字生成，四个 key word 为 `43f21b68 9a0f3610 3ac65312 b8926aa3`，运行八轮 XXTEA 风格混合。字长均为 32 位并按小端处理。

payload 以四字节字为单位处理。前 512 个字连续 XOR，中间每隔四个字处理一个，最后不足 512 个字的区间连续处理。使用同一过程即可逆转，尾部不足四字节的部分保持原字节。具体的区间边界与 key 下标循环以经过验证的 asset_codec.py 为准。

本地 ARM64 原库分析中，容器解码入口位于 `0xbedb78`，稀疏 XOR 位于 `0xbedc74`，四个 key word 位于 `0x396890`。这些是该原库的虚拟地址，定位新库时先重新确认 ELF 段和调用点。

## LuaJIT dump

当前解码得到的脚本头为 `1b 4c 4a 02 08`。头后是 ULEB128 chunkname 长度、chunkname 和连续的 length-prefixed prototypes，以长度零结束。子 prototype 在前，模块根 prototype 在最后。

每个 prototype 的前四字节是 flags、参数数、寄存器槽数、upvalue 数。其后是 ULEB128 GC 常量数、数字常量数、指令数、debug 字节数。存在 debug 时再读 firstline 和行跨度。后面依次是指令、每项两字节的 upvalue 描述、常量及 debug 数据。

修改过的 prototype 与模块根会去掉各自 debug 数据，其他 prototype 原样复制。这里的常量索引按原编号保留，追加 GC 字符串时将新条目按高索引到低索引写在旧常量数据之前。

## 当前游戏 dump opcode

此样本的 opcode 数值与宿主标准 LuaJIT 不同。inspect_bytecode.py 输出原始 opcode、寄存器和常量表，避免拿标准反汇编名称直接解释游戏指令。

| 游戏 opcode | 已确认含义 |
| --- | --- |
| `01` | ISGE |
| `04` | ISEQV |
| `05` | ISNEV |
| `0c` | KSTR |
| `0e` | KSHORT |
| `10` | KPRI |
| `18` | MOV |
| `1e` | RET0 |
| `1f` | RET1 |
| `2c` | MULVV |
| `36` | UCLO |
| `37` | FNEW |
| `3a` | GGET |
| `3c` | TGETV |
| `3d` | TGETS |
| `41` | TSETS |
| `46` | CALL |
| `58` | JMP |

指令存储为 `OP A C B`，AD 格式的 D 是后两个字节的小端值。跳转目标为当前下一条指令加 `D-32768`。函数调用有 FR2 空槽，函数在 rN，参数从 rN+2 开始。

## 最新金币实现

在 addGameLayerMoney 开头加正数、出售类型和模式检查，符合条件时将 r1 乘 10。进入原函数后，它继续更新自己的 money、顶部工具栏、统计和 MoneyDataValidator。addPartnerGameLayerMoney 仍由游戏原有数据路径调用。

七种单人模式加 GAMEMODE_COOPERATION 都通过金币条件。已观察到的实际模式编号分别为主题 1、周赛 2、日赛 3、糖果 4、本地周赛 5、星途 7、收集 8、合作 9。代码按枚举名称查值，以便保留可检查的模式含义。

## 最新射程实现

在 Tower.setShootRange 将原射程和 scale 计算完成后、传入 shootRange.setValue 前，根据七种单人模式把 r7 设为 4096。合作模式保留游戏计算出的值。这里修改的是通用炮塔射程，部分特殊弹道或技能还可能有自己的几何逻辑。

此前合作全图射程会在本机模拟中影响双方炮塔，用户确认这一现象后要求移除，因此合作条件只存在于金币模块。

## 金币 JIT 修复

原生 VM 沙箱连续调用旧金币方法时，曾从主题模式第 384 次附近开始出现 `40 → 40`，随后切换模式也出现错误。仅禁止该金币方法的 JIT 后，七种单人模式各 500 次检查均通过；加入合作模式后又完成八种模式各 500 次检查。

模块根返回类对象前调用 `jit.off(class.addGameLayerMoney, true)`。这会针对该方法及其子函数关闭编译并清除已有编译代码。函数级开关的语义见官方说明。[LuaJIT jit 库](https://luajit.org/ext_jit.html)

此项目已经确认该环境中问题与 JIT 路径有关，尚未把编译器内部触发原因细化到源码修复。不要以宿主解释器少量测试代替原生 VM 长时间检查。稳定补丁中包含上述函数级处理。

根函数常量编号可能超过 255。新增的 jit、off 和 addGameLayerMoney 使用完整 AD 字符串索引，再用 TGETV 取方法，避免将大索引截成单字节。
