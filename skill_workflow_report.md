# Reverse-Orchestrator Skill 工作流报告

## 本次执行全流程

### 时间线与成果

| 阶段 | 状态 | 轮次 | 关键产出 |
|------|------|------|----------|
| Phase 0 | ✅ | ~5 | NIS加固识别、域名/SDK清单、字符串解密(custom base64+XOR "NetEase") |
| Phase 1 | ✅ | ~8 | Magisk DenyList绕过模拟器检测、SP/DB提取、hluda-server就绪 |
| Phase 2 | ✅ | ~6 | 28个API端点、请求头加密结构、CDN资源路径、RongCloud/MQTT发现 |
| Phase 3 | ✅ | ~30 | p1/p2 XOR破解、AES-256-CBC Key+IV捕获、Gson JSON序列化确认、加密/解密验证 |
| Phase 4 | ✅ | ~5 | 完整登录流程(明文密码)、三通道认证(HTTP+RongCloud+MQTT+TencentIM) |
| Phase 5 | ⬜ | - | 未执行 |

**总轮次**: ~60 轮交互
**总耗时**: 约 3-4 小时
**Phase 3 Frida 脚本迭代**: 18 个版本 (v1-v15 + cipher + gson + key + key2 + auth)

---

## 失败教训 (按严重度排序)

### 1. Frida 反检测迭代成本极高 (18版脚本)

Phase 3 是最昂贵的阶段。每次尝试一种 hook 方式, 都可能触发 NIS 崩溃:

```
v1: RequestBody.create(String)      → 无输出 (OkHttp5.x API 不同)
v2: 15 overloads + writeTo          → p1/p2 抓到, body 无输出  
v3: BufferedSink 底层 hook          → UI 崩溃 (hook 太底层)
v4: Interceptor + 类枚举            → Interceptor 是接口不可 hook
v5: HttpClientImp 方法枚举          → 发现 httpCall 签名和 HttpRequest 接口
v6: httpCall hook                   → [object Object] toString 不可读
v7: 反射 getDeclaredFields          → NIS 崩溃
v8: 修复 toString 调用              → 仍 [object Object]
v9: Object.keys + Java.cast         → NIS 崩溃
v10: HttpRequest getter             → 无输出 (接口方法不可 hook)
v11: setter + 流量计数              → 21个请求抓取, setter 不触发
v12: 枚举方法签名                   → 发现 HttpRequest 是 abstract 接口!
v13: Body.getData + 类枚举          → NIS 崩溃
v14: 最简 Body.getData              → ✅ 响应解密成功!
v15: createCall + 接口方法调用      → ✅ 请求明文成功!
  +  crypto_compare: 双通道对比     → 确认加密特征
  +  gson: 选择性 Gson hook          → ✅ JSON 序列化确认
  +  cipher: Cipher.doFinal hook     → ✅ AES/CBC/PKCS7 确认
  +  key2: Cipher.init hook          → ✅ AES-256 Key + IV 捕获!
```

**教训**:
- 从底层 hook (okio) 不如先从应用层 API 开始
- 加固 app 中禁止: 类枚举、反射、Java.cast、Object.keys
- 必须先枚举方法签名确定类结构, 再针对性 hook
- 接口 (interface) 不可 hook — 必须找到实现类

### 2. 加固 app 对 Frida 极度敏感

| 操作 | 是否触发 NIS | 说明 |
|------|-------------|------|
| frida spawn | ❌ 直接崩溃 | InvocationTargetException |
| frida attach (frida-server) | ❌ 崩溃 | 原生层检测 |
| frida attach (hluda-server) | ✅ 成功 | hluda 绕过检测 |
| 类枚举 (enumerateLoadedClasses) | ❌ 偶尔崩溃 | 大量类加载触发检测 |
| 反射 (getDeclaredFields) | ❌ 崩溃 | NIS 检测 JNI/反射 |
| Java.cast + Object.keys | ❌ 崩溃 | 同上 |
| Hook getter/setter | ✅ 安全 | 简单方法 hook 不触发 |
| Hook Cipher.doFinal/init | ✅ 安全 | 系统类 hook 安全 |
| Hook Gson.toJson | ⚠️ 不稳定 | 取决于调用频率 |

### 3. ADB/MSYS2 路径问题贯穿全程

```
问题: MSYS2 将 /sdcard/ 转换为 E:/Git/sdcard/
解决: 每个 adb 命令前加 MSYS_NO_PATHCONV=1
影响: adb pull/push/shell 全部受影响
遗漏: 每个新命令都要记得加, 否则静默失败
```

### 4. OkHttp 版本差异

抓包发现 `user-agent: okhttp/5.3.2`, 但 OkHttp 4.x/5.x 与 3.x API 完全不同:
- `RealCall` 类名变化
- `RequestBody.create()` 有 15 个 overloads
- Interceptor 接口方法不可直接 hook
- 很多内部类从 Java 迁移到 Kotlin

### 5. 接口 vs 实现类

`HttpRequest` 是 Retrofit 动态生成的接口实现, Frida 无法 hook:
- `HttpRequest.setParam/setPath` — 接口, hook 不触发
- `HttpRequest.getParam/getPath` — 接口, hook 不触发
- 解决方法: hook `HttpClientImp.createCall(req)` 并在方法体内调用 `req.getPath()` 等

### 6. 模拟器环境不稳定性

- MuMu 模拟器偶尔断连 (一天 3+ 次)
- 重启后 `adb root` 权限丢失, 需重连
- Magisk DenyList 不持久化, 每次重启需重设
- 长时间运行后模拟器性能下降

---

## 成功经验

### 1. hluda-server 是关键突破点

普通 frida-server: spawn + attach 均被 NIS 检测
hluda-server: attach 成功, 后续 hook 全部基于此

**结论**: 加固 app 逆向必须优先准备 hluda/gadget

### 2. 从应用层 API 入手, 逐层下探

路径: 
```
Headers (RequestBuilder.header) → 工作 ✅
  ↓
OkHttpClient.newCall → 工作 ✅ (流量指示)
  ↓  
HttpClientImp.httpCall → 工作但不可读
  ↓
Body.getData() → ✅ 响应解密
  ↓
HttpClientImp.createCall() → ✅ 请求明文
  ↓
Gson.toJson() → ✅ 序列化格式
  ↓
Cipher.doFinal() + Cipher.init() → ✅ 算法+密钥
```

不是从底层 (okio/BufferedSink) 向上, 而是从应用层向底层。

### 3. 抓包 + Hook 交叉验证

- mitmproxy 看到加密 body → Frida 定位加密点
- Frida 抓到明文 → mitmproxy 抓到对应密文 → 对比反推算法
- 双通道对比在 Phase 3.5 中起了决定性作用

### 4. 类枚举先于 Hook

v5 先枚举 `HttpClientImp` 和 `HttpRequest` 的所有方法签名, 发现了:
- `HttpRequest` 是 abstract 接口 (v12 才确认)
- `HttpClientImp.httpCall` 有两个 overload (3参/4参)
- `Body` 是 Kotlin data class, 有 `getData()` getter

这些信息指导了后续所有 hook 策略。

### 5. 最小化原则

v14 (只有 Body.getData) 和 v15 (只有 createCall) 是最成功的两个版本 — 单 hook, 无反射, 无枚举, 稳定运行。

---

## Skill 设计问题与改进建议

### P0: Skill 引用的工具全部不存在

Skill 文档中所有函数名均为虚构:

```
apk_unpack()              → 不存在
apk_detect_packer()       → 不存在  
apk_extract_manifest()    → 不存在
apk_string_search()       → 不存在
apk_decompile()           → 不存在
adb_device_info()         → 不存在
adb_install_cert()        → 不存在
adb_app_mgmt()            → 不存在
adb_push_pull()           → 不存在
proxy_start()             → 不存在
proxy_list_flows()        → 不存在
proxy_stop()              → 不存在
toolkit_analyze()         → 不存在
crypto_sign_verify()      → 不存在
crypto_aes()              → 不存在
crypto_rc4()              → 不存在
crypto_rsa()              → 不存在
db_explore()              → 不存在
file_parse_java_serial()  → 不存在
hook_gen_frida()          → 不存在
hook_run()                → 不存在
toolkit_scaffold()        → 不存在
```

**影响**: Skill 设计流程完全无法直接执行。每个步骤都需要人工翻译为实际 CLI/Python 命令。

**建议**: 两个方案:
- A: 编写 Python/Shell 封装脚本放到 `tools/` 目录
- B: 将 Skill 文档中的函数名直接替换为实际命令示例
- 推荐 B (更快), 同时逐步建设 A

### P0: 知识库全部缺失

已知的 KB 路径全部不存在:
```
kb/patterns/packer_patterns.md       ❌ → 本次手动补充 (5种加固)
kb/patterns/anti_patterns.md         ❌ → 本次手动补充 (~10条)
kb/patterns/ssl_bypass_strategies.md ❌ → 本次手动补充 (5级策略)
kb/patterns/auth_flow_patterns.md    ❌ → 本次手动补充 (4种模式)
kb/case_library/index.json           ❌ → 本次手动补充 (sybl首个案例)
kb/confidence_rules.json             ❌ → 本次手动补充
```

**建议**: 首次运行时自动初始化 KB 骨架 (空模板)。每次逆向完成后增量更新。

### P1: Phase 流程与实际脱节

Skill 设计的 Phase 顺序与实际执行存在差距:

| Skill 设计 | 实际问题 |
|------------|----------|
| Phase 0 静态分析 → 查 case_library | case_library 不存在 |
| Phase 1 安装证书 + 装app | 证书安装需要 MoveCertificate 模块, Skill 未提及 |
| Phase 2 抓包 → 如果有 SSL pinning | NIS 加固的模拟器检测比 SSL pinning 更优先 |
| Phase 3 调 /reverse-js-analyzer | 子 Skill 不存在 |
| Phase 3 调 /reverse-crypto-detector | 子 Skill 不存在 |
| Phase 4 调 /reverse-auth-flow-composer | 子 Skill 不存在 |

**建议**: 
- Phase 0 增加"加固检测与绕过"步骤 (优先于一切)
- Phase 1 增加"环境检测绕过" (Magisk/hluda)
- 子 Skill 不存在时自动降级为手动分析指导

### P1: 缺少 Frida 最佳实践

Skill 提到 `hook_gen_frida` 和 `hook_run` 但没有任何关于:
- 加固 app 中哪些操作会触发检测
- hluda vs frida-server 的选择
- 从应用层到系统层的 hook 策略
- 最小化 hook 原则

**本次建立的 Frida 安全规则**:
```
✅ 安全: Hook 简单 getter/setter, Cipher.doFinal/init, Gson.toJson (选择性)
❌ 危险: 类枚举, getDeclaredFields, setAccessible, Java.cast, Object.keys
⚠️  不稳定: 底层 okio/BufferedSink hook, 高频率 hook
```

### P2: 加固自动检测能力不足

Skill 仅提到 "360加固 → 放弃 Runtime Hook → H5", 但:

```yaml
缺失的加固特征库:
  libnesec.so + MyApplication(NIS wrapper) → 网易易盾
  libjiagu.so                              → 360
  libsecmain.so                            → 腾讯乐固
  libDexHelper.so                          → 梆梆
  libijmdata.so                            → 爱加密
  libemulatordetector.so                   → 模拟器检测 (非加固但关键)
```

**建议**: 
- Phase 0 结束后自动匹配加固特征库
- 匹配到 NIS → 推荐策略: Magisk DenyList + hluda + 动态分析
- 匹配到 360 → 推荐策略: 放弃 native hook, 直奔 H5/WebView

### P2: 缺少平台兼容层

Windows + MSYS2 环境下的特殊问题:
- 路径转换: 所有 adb 命令需要 `MSYS_NO_PATHCONV=1`
- 文件落地位置: `adb pull /sdcard/x /tmp/x` → `/e/tmp/x`
- mitmdump 端口占用: 读取流不能与捕获流同端口
- Python vs Linux 工具链: 文件操作优先 Python

### P3: 案例保存格式良好但未自动化

Skill 要求写 `workflow.json` 到 `case_library/`, 格式设计合理 (phases/decisions/strategy_stack)。但本次全手动编写。

**建议**: Phase 5 完成后自动从状态文件生成 workflow.json 和案例摘要。

### P3: 缺少交互式引导

Skill 假设全自动执行, 但实际上需要用户交互 (点击app, 输入登录):
- 未明确哪些步骤需要用户操作
- 未提供"等待用户操作"的检查点
- 未说明如何检测用户是否完成操作

---

## 工作流逻辑评估

### Skill 原始流程 vs 实际执行

```
Skill 设计:  Phase0 → Phase1 → Phase2 → Phase3(JS分析+Crypto检测) → Phase4(Auth) → Phase5
实际执行:  Phase0 → [绕过检测] → Phase1 → Phase2 → [18轮Frida] → Phase3 → Phase4 → (未到Phase5)
                                            ↑                    ↑
                                       最大偏差              子Skill缺失
```

### 流程问题:

1. **Phase 0→1 缺少"环境准备"阶段**: 加固检测、模拟器绕过、hluda 配置应该在 Phase 1 之前
2. **Phase 2→3 过渡不自然**: 抓包发现加密后, 应该先尝试静态分析 (对比明密文), 再动态 Hook
3. **Phase 3 内部顺序错误**: Skill 让先调 JS/Crypto 子 Skill, 再手动分析。但加固 app 应该先动态 Hook
4. **Phase 之间的检查点缺失**: 每个 Phase 完成后没有自动验证

### 推荐工作流:

```
Phase 0: 静态分析
  ├── 加固检测 → 匹配特征库 → 获取对抗策略
  ├── 提取 manifest/域名/SDK
  └── 查 case_library 获取相似案例

Phase 0.5: 环境准备 [NEW]
  ├── 检测 ADB 设备
  ├── 根据加固类型准备绕过工具
  │   ├── NIS → Magisk DenyList + hluda
  │   └── 无加固 → frida-server 即可
  └── 安装 CA 证书

Phase 1: 数据提取
  ├── 安装/启动 app
  ├── 绕过检测 (如需)
  └── 提取 SP/DB/MMKV

Phase 2: 流量抓包
  ├── 启动 mitmproxy
  ├── 抓取各页面流量
  └── 发现 API 端点

Phase 3: 加密逆向
  ├── 3a: 尝试类枚举 (加固app跳过)
  ├── 3b: Hook 应用层 API (Body.getData/createCall)
  ├── 3c: Hook 加密层 (Cipher/Gson)
  └── 3d: Python 验证解密

Phase 4: 认证流程
  ├── 捕获登录请求/响应
  ├── 提取 token/IM 凭据
  └── 验证 token 使用方式

Phase 5: 产物生成
  ├── api_spec.json
  ├── plugin.py (如有完整加密)
  └── 写入 case_library
```

### 逻辑合理性评分

| 维度 | 评分 | 说明 |
|------|------|------|
| Phase 划分 | ⭐⭐⭐ | 6 阶段划分合理, 但缺少"环境准备"阶段 |
| 工具调用 | ⭐ | 全部虚构函数, 不可执行 |
| 案例复用 | ⭐⭐ | 设计合理但 KB 为空 |
| 错误处理 | ⭐⭐ | 有重试/降级概念, 但未具体化 |
| 加固对抗 | ⭐⭐ | 仅提及 360, 缺少 5+ 种常见加固 |
| 交互设计 | ⭐ | 假设全自动, 实际需要用户参与 |
| 产物质量 | ⭐⭐⭐ | 设计合理 (plugin.py + api_spec.json) |
| 总体 | ⭐⭐ | 框架合理, 细节缺失严重 |
