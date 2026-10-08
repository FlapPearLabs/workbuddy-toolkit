# WorkBuddy 生产级底层事故深度排查与白盒物理凭证库

> **维护主体**：FlapPearLabs ([GitHub](https://github.com/FlapPearLabs))  
> **定位**：拒绝表面应付、拒绝伪装完成，拿不可伪造的真实物理计量、内核堆栈与反汇编证据说话。  
> **开源治理项目**：`workbuddy-toolkit` ([https://github.com/FlapPearLabs/workbuddy-toolkit](https://github.com/FlapPearLabs/workbuddy-toolkit))  
> **取证代码库**：`workbuddy-safedelete-rootcause` ([https://github.com/FlapPearLabs/workbuddy-safedelete-rootcause](https://github.com/FlapPearLabs/workbuddy-safedelete-rootcause))

---

> 🧭 **导航**：[📖 返回 Toolkit 主 README](../../README.md#16--生产事故深水排查与白盒物理凭证库seatbelt-17-万行规则雪崩pty-5s-延迟与四大草台班子工程缺陷)

---

## 概述：大厂光环下的“草台班子”底层工程缺陷

在长期使用腾讯所谓“拳头级”AI 编程助手 WorkBuddy 构建复杂系统（如知乎数据管道 `zhihugrabber` 与微服务项目）的过程中，我们遭遇了一系列匪夷所思、导致系统瘫痪或数据损坏的深水生产事故。

面对这些缺陷，我们坚决贯彻**“理论真源优先、白盒化物理凭证交付、强制诚实”**的工程准则，使用 macOS 原生 `sample` 采样器、系统级 `lsof` 句柄审计、二进制符号反编译（`nm -C` / `otool`）与真实物理计量，对底层缺陷完成了闭环溯源，并在 `workbuddy-toolkit` 中给出了工业级的全自动自愈与治理方案。

本目录完整归档了各大事故的**问题背景**、**排查取证过程**、**最终白盒物理凭证**与**Toolkit 治愈方案**。

---

## 生产事故索引矩阵

| 事故编号 | 事故定级 | 事故名称与核心现象 | 涉案代码组件与符号定位 | 核心根因与物理证据 | 官方 PR 补丁与 Toolkit 治理方案 | 深度报告链接 |
| :---: | :---: | :--- | :--- | :--- | :--- | :---: |
| **01** | `P0` | **沙盒 PTY 日志无底洞与 32 万快照文件瘫痪系统 I/O**<br>运行数天系统盘减少 15GB+，整机卡死 | `sandbox-cli-gc` (`gc_runner.rs`, `SessionIndex`)<br>`sandbox_core::pipe_utils`<br>`no-orphans.cjs` (L24) | PTY 日志零 TTL 累积 14.8GB；321,489 个快照小文件；`sandbox-cli-gc` RSS 达 471.2MB 遍历打满 IOPS | **官方 Patch**：流式滑动窗口 GC + PTY 滚动容量硬顶 + POSIX 孤儿进程回收<br>**Toolkit**：`workbuddy-log-guard` 四重物理看门狗 + `wb-sandbox clean` | [查看完整报告 ➔](./INCIDENT_01_SANDBOX_LOG_SNAPSHOT_EXHAUSTION.md) |
| **02** | `P1` | **多 Agent 并发构建缺乏全局编译缓存诱发计算风暴**<br>风扇狂转、CPU 100%、磁盘被多份 `target` 吞噬 | `TerminalEnvironmentFactory.ts`<br>`WorkspaceIsolationManager.ts`<br>Colima / Docker APFS 存储层 | 多 Agent 独立沙盒重复拉取 crates 并冷编译，构建耗时 128s，无共享 `sccache`，缓存命中率 0% | **官方 Patch**：多 Agent 环境变量自动嗅探注入 `RUSTC_WRAPPER` + 共享 `.cargo/config.toml`<br>**Toolkit**：`wb-doctor` Check 6 + 全局 10GB 缓存硬顶 + `fstrim` 穿透 | [查看完整报告 ➔](./INCIDENT_02_CARGO_MULTI_AGENT_SCCACHE.md) |
| **03** | `P0` | **Git 工作树文件莫名蒸发与 npm ci 崩溃**<br>包管理器被拦截留脏状态，工作树 59 个文件丢失 | `genie-safe-delete.cjs`<br>文件系统过滤驱动竞争态 | `genie-safe-delete.cjs` 硬编码删除超 20 个文件抛错；底层沙盒过滤层在竞争态下直接诱发文件系统物理丢失 | **官方 Patch**：移除无界安全删除抛错，修复驱动竞争态<br>**Toolkit**：未提交代码资产绝对保护准则 | [独立证据仓库 ➔](https://github.com/FlapPearLabs/workbuddy-safedelete-rootcause) |
| **04** | `P0` | **Seatbelt 规则雪崩致 SBPL O(N²) 死锁、前端 120s 强杀 (exit 137) 与 PTY 5s 假死**<br>终端命令假死报 137，后台 CPU 100% | `sandbox-center` (`compile_sbpl_clauses`, `dim_covered`)<br>`tsbx_rules.json` (L7)<br>`sandbox-cli` (`InteractiveProcess::drop`) | `tsbx_rules.json` 遗漏 macOS 临时目录；动态生成万条单路径；$O(N^2)$ 比对 1.5 亿次死锁；前端 120s 超时下发 ProcessKill (SIGKILL 137)；PTY drop join 硬卡 5 秒 | **官方 Patch**：`tsbx_rules.json` 补全临时目录 + 前缀树 Trie 降至 $O(N \log N)$ + 先关闭 `master_fd` 后 join<br>**Toolkit**：UDS 顶层 `sessionId` 修复 + `wb-sandbox heal` + `wb-sandbox clean` + `wb-doctor --inspect-137` | [查看完整报告 ➔](./INCIDENT_04_SEATBELT_RULE_EXPLOSION_AND_PTY_FREEZE.md) |

---

## 取证方法论与工程准则

所有事故调查均严格遵循以下准则：

1. **白盒化物理凭证（White-box Proof of Execution）**：
   - 拒绝“大概是某个配置问题”的主观猜测；
   - 必须提供内核级调用堆栈（`sample`）、真实反汇编符号（`nm -C`）、物理文件条目计量（`find | wc -l`）、真实常驻内存（RSS）与吞吐测试对比；
2. **零隐式截断与强迫诚实（Forced Honesty）**：
   - 每一个数字均取自现场环境测量，不掩盖、不粉饰；
3. **零破坏与外科手术式修改（Surgical Cleanup）**：
   - 修复工具必须具备活跃句柄感知（`lsof` / 共享锁感知）；
   - 严禁为了治理而粗暴 `rm -rf`，绝对保护用户未提交的代码资产与活跃工作现场。

---

> 🧭 **导航**：[📖 返回 Toolkit 主 README](../../README.md#16--生产事故深水排查与白盒物理凭证库seatbelt-17-万行规则雪崩pty-5s-延迟与四大草台班子工程缺陷)

