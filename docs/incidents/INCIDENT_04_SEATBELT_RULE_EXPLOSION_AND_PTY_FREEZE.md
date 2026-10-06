# 事故四深度取证报告：Seatbelt 1.7 万行规则雪崩致 SBPL 编译 O(N²) 死锁 64 分钟与 PTY 5 秒假死

> **事故归档编号**：`WKB-INCIDENT-004`  
> **故障定级**：`P0`（严重核心功能完全瘫痪 / 进程长时间 100% CPU 死锁 / 系统级假死）  
> **受影响系统**：macOS (Apple Silicon / Intel, Darwin 20+)  
> **核心涉案组件**：`sandbox-center`, `sandbox-cli`, `tsbx_rules.json`, macOS Seatbelt (SBPL), Unix Domain Socket IPC  
> **治理工具与命令**：`wb-sandbox heal`, `wb-sandbox clean`, `wb-doctor` (Check 5)  
> **开源治理仓库**：[FlapPearLabs/workbuddy-toolkit](https://github.com/FlapPearLabs/workbuddy-toolkit)

---

## 一、问题背景：我们是怎么碰到的

作为重度依赖 AI 协同构建系统的独立开发者（二本文科生身份，GitHub: [FlapPearLabs](https://github.com/FlapPearLabs)），在长期使用腾讯所谓“拳头级”AI 编程工具 WorkBuddy 的过程中，突发了一场令资深系统工程师极度窒息的特大生产级故障：

1. **终端命令全面假死，120 秒后惨遭 SIGKILL 强杀**：
   - 在 WorkBuddy 内置终端或由 Agent 调用的终端中，执行**任何**终端命令（即使只是最简单的 `date`、`echo 1` 或 `ls`），终端立即陷入无休止的悬挂卡死；
   - 界面毫无输出，持续转圈整整 120 秒后，前端无情抛出错误弹窗：
     ```text
     Process terminated with exit_code: 137 (SIGKILL)
     ```
   - 终端可用度彻底归零（命令执行成功率 0%）；
2. **命令退出硬卡死 5 秒**：
   - 即使在偶发恢复时，任何 1 毫秒即可完成的轻量命令，在执行完毕后界面必定硬生生假死 5 秒才恢复光标；
3. **关闭主程序后，后台守护进程 100% CPU 狂转 64 分钟**：
   - 用户尝试关闭 WorkBuddy Electron 桌面主窗口退出应用；
   - 但电脑风扇持续剧烈呼啸，机身发烫严重，电池电量飞速耗尽；
   - 调出系统活动监视器与 `top` 检查，赫然发现后台残留的守护进程 **`sandbox-center`（PID 1442）单核 CPU 占用持续顶死在 100.0%，整整持续死锁狂转了 64 分钟**！

---

## 二、排查取证过程：怎么找的证据、使用了什么工具与探针

面对这一致命死锁，我们绝不满足于“杀进程重启”的鸵鸟态度，而是坚持**白盒物理取证**，挂载 macOS 内核级探针直击事故核心：

### 探针 1：macOS 原生 `sample` 堆栈物理采样，抓获深水死锁现场

针对正在打满单核 CPU 狂转的 `sandbox-center` 进程（PID 1442），使用 macOS 原生采样器对其进行连续采样：

```bash
sample 1442 10 -file /tmp/sandbox_center_sample.txt
```

**物理采样结果震撼曝光**：
全部 2,351 个采样点 100% 集中在同一个调用深渊：

```text
+ 2351 Thread_12534 DispatchQueue_1: com.apple.main-thread (serial)
+   2351 sandbox_center::rules::profile::sbpl::compile_sbpl_clauses (in sandbox-center) + 312
+     2351 sandbox_center::rules::profile::sbpl::shadowed_verdicts::dim_covered (in sandbox-center) + 184
+       2351 <sandbox_center::rules::behavior::FileActionMap as core::cmp::PartialEq>::eq (in sandbox-center) + 48
```

证据确凿：`sandbox-center` 并非在进行合法的系统 I/O，而是深陷在 **`compile_sbpl_clauses -> shadowed_verdicts::dim_covered`** 的规则编译死循环中！

### 探针 2：符号表提取与反编译算法复杂度审查 (`nm -C`)

我们对 `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.6.10/sandbox-center` 执行符号表审计：

```bash
nm -C sandbox-center | grep -E "compile_sbpl|shadowed_verdicts"
```

**符号证据确认**：
```text
0000000100110b78 t sandbox_center::rules::profile::sbpl::compile_sbpl_clauses
00000001001187fc t sandbox_center::rules::profile::sbpl::shadowed_verdicts::dim_covered
```

**反汇编逻辑逆向**：
在生成苹果 macOS Seatbelt 沙盒底层 SBPL 规则前，`compile_sbpl_clauses` 试图对规则集进行去重与阴影覆盖（shadowing）判定。其算法实现竟然是一个**未经过任何空间索引、前缀树或哈希分组的双重嵌套循环**：

```rust
// 逆向还原伪代码:
for i in 0..rules.len() {
    for j in 0..rules.len() {
        if i != j && is_shadowed(&rules[i], &rules[j]) {
            dim_covered(&rules[i], &rules[j]);
        }
    }
}
```

其算法时间复杂度是极其原始且致命的 **$O(N^2)$**！

### 探针 3：解包 `tsbx_rules.json`，发现草台班子配置漏洞

为什么会有海量规则被送入 $O(N^2)$ 编译器？我们打开了 WorkBuddy 自带的初始沙盒规则文件：
`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.6.10/tsbx_rules.json`

**令人目瞪口呆的代码真相曝光**：
```json
{
    "version": 1,
    "file_rules": [
        { "path": "%LOCALAPPDATA%\\Temp\\**", "action": "read=allow|write=allow|delete=allow", "_comment": "temp" },
        { "path": "C:\\openclaw\\openclaw\\**", "action": "read=allow|write=allow|delete=allow", "_comment": "openclaw app" },
        { "path": "D:\\openclaw\\proxy-agent\\**", "action": "read=allow|write=allow|delete=allow", "_comment": "..." }
    ]
}
```

**荒谬事实**：
- 腾讯工程师在发布 macOS 版本的沙盒时，直接照搬了 Windows 的配置模板；
- 规则中**只声明了 Windows 的 Temp 环境变量 (`%LOCALAPPDATA%\Temp\**`)**，甚至留着工程师在自己 Windows 电脑上的测试路径 `C:\openclaw` 和 `D:\openclaw`！
- **对于 macOS 的系统全局临时目录 `$TMPDIR`（如 `/var/folders/.../T/`、`/private/var/folders/...`、`/tmp/**`），竟然完全漏配，一条都没有！**

### 探针 4：多米诺骨牌雪崩反应还原

由于 macOS 临时目录漏配，整个沙盒系统爆发了多米诺骨牌式的恶性雪崩：

1. **单条绝对路径爆炸**：在 macOS 上，任何终端命令（创建临时文件、管道重定向、编译脚本）只要触碰一下 `$TMPDIR`，沙盒底层 Hook 拦截到访问，发现未命中任何通配规则；
2. **回退 IPC 动态注册**：沙盒机制自动回退，通过 Unix Socket 向 `sandbox-center` 发起 IPC 注册，将每个被碰到的临时文件以**单条完整绝对路径**形式注册为 `auto_grant` 规则；
3. **线性膨胀至 17,500+ 条**：经过几天自动化开发积累，动态单条规则生生被追加到了 **17,542 条**（规则体积超过 1.06MB）；
4. **1.53 亿次死循环比对**：当规则数量达到 $N = 17,542$ 时，$O(N^2)$ 算法需执行的运算次数为：
   $$\frac{N \times (N - 1)}{2} = \frac{17,542 \times 17,541}{2} \approx 153,846,000 \text{ 次比对}$$
   **整整一亿五千三百万次比对！**
5. **事件循环彻底打死**：这 1.53 亿次比对直接将单线程的 `center-io` 事件循环死锁了整整 **64 分钟**！

### 探针 5：超时链路还原（3000ms 与 120,000ms）

- 当用户在终端发起新命令时，`sandbox-cli` 尝试通过 Unix Socket 握手获取执行 Token；
- 由于 `sandbox-center` 正忙于跑 1.53 亿次死循环，IPC 无响应，`sandbox-cli` 触发硬编码的 **3000ms IPC 超时**退出；
- 前端 Electron 界面层迟迟得不到响应，陷入 **120,000ms（2 分钟）全局死等**，最终无情抛出 SIGKILL (137) 报错退出。

### 探针 6：深入逆向 `sandbox-cli`，揭露 5 秒假死硬编码

为什么偶发执行成功的命令也必定卡死 5 秒？
我们对 `sandbox-cli` 执行符号反编译，定位到：
`<sandbox_core::executor::interactive::InteractiveProcess as core::ops::drop::Drop>::drop`

**逆向真相**：
- 在命令结束时，主线程进入 `InteractiveProcess::drop` 析构函数；
- 但由于代码编写错误，主线程在持有 `master_fd`（伪终端主设备描述符）的情况下，就急于调用 `reader_thread.join()`；
- 由于 `master_fd` 未被关闭，负责从 PTY 读取输出的子线程 `reader_thread` 永远收不到 `EOF`，一直阻塞在内核 `read(master_fd)` 系统调用中；
- 官方工程师在这里写死了超时等待：`reader_thread.join_timeout(Duration::from_millis(5000))`；
- **因为子线程永远不退出，主线程每一次都必须干等满整整 5000ms 超时才强行放弃！凭空制造了 5 秒假死！**

### 探针 7：孤儿守护进程脱离常驻

WorkBuddy Electron 桌面窗口在关闭时，从未向后台通过进程组发送 `SIGTERM` 或执行优雅停机广播，导致 `sandbox-center` 和 `sandbox-cli-gc` 沦为孤儿守护进程在后台永久驻留，肆无忌惮地 100% 消耗用户 CPU 算力。

---

## 三、最终白盒物理凭证

以下为生产环境现场捕获的物理凭据：

### 1. 物理计量指标对比

| 物理计量项 | 官方故障状态实测值 | Toolkit 治理后实测值 | 改善幅度 / 证据意义 |
| :--- | :--- | :--- | :--- |
| **规则总条数** | **17,542 条** (单路径膨胀) | **48 条** (通配规则覆盖) | **规则数削减 99.7%** |
| **SBPL 编译比较次数** | **1.53 亿次** | **1,128 次** | **计算量削减 99.999%** |
| **规则编译耗时** | **64 分 12 秒 (3852 秒)** | **0.2 毫秒 (0.0002 秒)** | **提速 19,260,000 倍** |
| **终端命令假死率** | **100% 失败 (超时 SIGKILL)** | **0% (毫秒级响应)** | 核心功能彻底复活 |
| **PTY 退出等待耗时** | **5,002 毫秒** (硬卡死) | **< 2 毫秒** | 消除 5 秒非预期卡顿 |
| **关闭窗口后孤儿进程 CPU**| **100.0% 狂转** | **0.0% (安全回收)** | 杜绝发烫与电量浪费 |

### 2. 真实物理堆栈采样证据 (macOS Native `sample`)

```text
Sampling process 1442 for 10 seconds with 1 millisecond of run time between samples
Sampling completed, processing symbols...
Analysis of sampling sandbox-center (pid 1442) every 1 millisecond
Process:         sandbox-center [1442]
Path:            /Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.6.10/sandbox-center
Load Address:    0x1000f0000
Architecture:    arm64

  2351 Thread_12534: com.apple.main-thread
  + 2351 start (in dyld) + 2544
  +   2351 main (in sandbox-center) + 892
  +     2351 sandbox_center::service::rules::RulesManager::recompile (in sandbox-center) + 416
  +       2351 sandbox_center::rules::profile::sbpl::compile_sbpl_clauses (in sandbox-center) + 312
  +         2351 sandbox_center::rules::profile::sbpl::shadowed_verdicts::dim_covered (in sandbox-center) + 184
  +           2351 <sandbox_center::rules::behavior::FileActionMap as core::cmp::PartialEq>::eq (in sandbox-center) + 48
```

### 3. `tsbx_rules.json` 漏配实锤证据

文件物理路径：
`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.6.10/tsbx_rules.json`
第 7 行代码：
```json
{ "path": "%LOCALAPPDATA%\\Temp\\**", "action": "read=allow|write=allow|delete=allow", "_comment": "temp" }
```
全文件检索无任何 `/var/folders`、`/private/var/folders` 或 `/tmp` 声明。

---

## 四、Toolkit 根治方案：我们的工具怎么修的

为了彻底根治这一大厂草台班子级严重事故，我们在 `workbuddy-toolkit` 中打造了**动态 IPC 自愈与系统 C-FFI 进程安全收割**的双核解决方案：

### 1. `wb-sandbox heal`：底层 IPC 动态注入通配规则与膨胀清理

我们不修改官方不可变的二进制文件，而是利用其暴露的 Unix Domain Socket，在运行态直连守护进程 IPC 进行外科手术式热修复：

```python
# bin/workbuddy-log-guard: heal_sandbox_center_rules 核心逻辑切片

def heal_sandbox_center_rules(socket_path=None, uid=None):
    # 1. 定位活体 Unix Domain Socket: /tmp/workbuddy-sandbox-center-*.sock
    sock = socket_path or find_sandbox_center_socket()
    target_uid = uid or find_active_uid()

    # 2. 探针查询当前在线规则
    rules_resp = send_sandbox_ipc(sock, "sandbox.rules.get_rules", {}, uid=target_uid)
    existing_rules = rules_resp.get("data", {}).get("fileRules", [])
    existing_paths = {r.get("path") for r in existing_rules if isinstance(r, dict)}

    # 3. 动态注入 macOS 遗漏的全局临时目录通配符
    temp_paths = [
        "/var/folders/**",
        "/private/var/folders/**",
        "/tmp/**",
        "/private/tmp/**",
        "/var/tmp/**",
        "/private/var/tmp/**"
    ]
    missing = [p for p in temp_paths if p not in existing_paths]
    if missing:
        to_add = [{"path": p, "action": "read=allow|write=allow|delete=allow", "isDirectory": True} for p in missing]
        send_sandbox_ipc(sock, "sandbox.rules.add_file_rule", {"category": "global", "rules": to_add}, uid=target_uid)

    # 4. 膨胀熔断：若累积 auto_grant 规则超过 500 条，原子清空重置
    if len(existing_rules) > 500:
        send_sandbox_ipc(sock, "sandbox.rules.set_file_rules", {"category": "auto_grant", "rules": []}, uid=target_uid)
        send_sandbox_ipc(sock, "sandbox.rules.set_file_rules", {"category": "temp", "rules": []}, uid=target_uid)
```

**自愈效果**：
通过直接向 `sandbox-center` 注入 6 条通配规则并清空历史膨胀规则，规则总数从 **17,542 条瞬间回归到 48 条**，SBPL 编译耗时从 64 分钟直降至 **0.2 毫秒**，彻底杜绝 $O(N^2)$ 死锁！

### 2. `wb-sandbox clean`：原生 `libproc.dylib` C-FFI 零 Fork 安全收割孤儿进程

针对主程序退出后守护进程常驻的问题，我们坚决贯彻**严禁滥用外部子进程 Fork**的系统工程标准，使用 macOS 原生动态链接库进行精准收割：

```python
# bin/workbuddy-log-guard: zero-fork libproc GUI 检测与守护进程回收

def is_workbuddy_gui_running():
    # 通过 macOS 原生动态库 libproc.dylib 进行零 Fork 纯内存遍历 (CPU 0.0%)
    libproc = ctypes.CDLL("libproc.dylib")
    pids = (ctypes.c_int * 2048)()
    bytes_ret = libproc.proc_listpids(1, 0, pids, ctypes.sizeof(pids))
    num_pids = bytes_ret // ctypes.sizeof(ctypes.c_int)
    buf = ctypes.create_string_buffer(1024)
    for i in range(num_pids):
        if libproc.proc_pidpath(pids[i], buf, 1024) > 0:
            p = buf.value.decode("utf-8", errors="ignore")
            if "WorkBuddy.app/Contents/MacOS" in p and "Helper" not in p:
                return True
    return False

def reap_orphaned_daemons(protected_keywords=["zhihu", "cargo"]):
    # 严格防护：GUI 运行中跳过；检测到用户正在运行活跃编译/爬虫任务跳过；检测到活跃 sandbox-cli 跳过
    if is_workbuddy_gui_running():
        return {"reaped": False, "reason": "gui_running"}
    # 确认全空闲孤儿态后，安全发送 SIGTERM 回收 sandbox-center 与 sandbox-cli-gc
    ...
```

### 3. `wb-doctor` 实时规则体检与状态诊断 (Check 5)

在 `bin/workbuddy doctor` 中集成 Check 5，实时审计沙盒健康度：

```bash
wb-doctor
```

- 若规则数超过 2,000 且缺少通配规则，当场标红警报：
  `Sandbox & Seatbelt : RISK (17542 rules, high SBPL lockup risk)`
- 修复后输出健康标识：
  `Sandbox & Seatbelt : HEALTHY (48 rules, temp wildcards active)`

### 4. 治理命令行交互

开发者可随时在终端执行自愈与状态查询：

```bash
# 1. 检查沙盒核心运行状态与规则数
wb-sandbox status

# 2. 一键执行规则热修复自愈
wb-sandbox heal

# 输出示例：
# ✔ 自愈完成: 总规则数 48 条，注入通配规则 6 条。
# ✔ 成功清理膨胀的 auto_grant 规则，消除 O(N^2) SBPL 编译锁死风险。

# 3. 安全清理孤儿守护进程
wb-sandbox clean
```

彻底解决 120 秒超时 SIGKILL、PTY 5 秒退出延迟与 64 分钟 100% CPU 电池风暴，还开发者一个安静、敏捷、可信赖的终端环境！
