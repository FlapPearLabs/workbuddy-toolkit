# 事故一深度取证报告：沙盒 PTY 日志无底洞与 32 万会话快照吞噬磁盘致系统 I/O 瘫痪

> **事故归档编号**：`WKB-INCIDENT-001`  
> **故障定级**：`P0`（严重系统资源耗尽 / 整机 I/O 饥饿死锁）  
> **受影响系统**：macOS (APFS), Linux (ext4/btrfs), Windows (NTFS)  
> **核心涉案组件**：`sandbox-core`, `sandbox-cli-gc`, `~/.workbuddy/logs/sandbox/`, `~/.workbuddy/workspace/sessions/`  
> **治理工具与命令**：`workbuddy-log-guard`, `wb-sandbox clean`  
> **开源治理仓库**：[FlapPearLabs/workbuddy-toolkit](https://github.com/FlapPearLabs/workbuddy-toolkit)

---

> 🧭 **导航入口**：[🔙 返回事故总览矩阵](README.md) │ [📖 返回 Toolkit 主 README](../../README.md#16--生产事故深水排查与白盒物理凭证库seatbelt-17-万行规则雪崩pty-5s-延迟与四大草台班子工程缺陷) │ [下一篇：事故二 ➔](INCIDENT_02_CARGO_MULTI_AGENT_SCCACHE.md)

---

## 一、问题背景：我们是怎么碰到的

在使用腾讯 WorkBuddy 开展长周期 AI-Native 自动化编程与智能体协同任务（例如运行连续数天的微服务与系统抓取工具开发）期间，macOS 工作机突发以下严重异常：

1. **系统盘可用空间断崖式蒸发**：原本剩余充足的系统盘（APFS）在 3~4 天内无故减少 **15GB 以上**，macOS 频繁弹出“磁盘空间几乎已满”系统警报；
2. **整机文件系统严重卡顿与 I/O 饥饿**：
   - 终端中执行 `ls`、`find` 或 Git 状态检查出现明显停顿；
   - 编译任务读写文件耗时成倍放大，Finder 窗口浏览工作区时甚至出现数秒“彩虹风车”；
3. **后台幽灵进程内存爆炸**：
   - 打开系统监视器（Activity Monitor）与 `top` 检查，赫然发现后台驻留着一个由 WorkBuddy 派生的独立守护进程 **`sandbox-cli-gc`**；
   - 该进程常驻物理内存（RSS）竟然狂飙至 **471.2 MB**，并且其单核 CPU 占用周期性脉冲式拉满到 80%~100%，持续高频对磁盘进行不可知读写。

---

## 二、排查取证过程：怎么找的证据、使用了什么工具与探针

为了探究系统磁盘与 I/O 崩溃的底层物理根因，我们严禁凭空猜想，立即挂载 macOS 系统级物理探针进行白盒穿透审计：

### 探针 1：磁盘空间分布与目录深度计量 (`du`, `find`)

首先使用系统基础计量工具锁定磁盘暴涨的热点目录：

```bash
# 1. 定位 WorkBuddy 用户目录物理占用
du -sh ~/.workbuddy/* | sort -hr
```

**计量发现**：
- `~/.workbuddy/logs/sandbox/` 物理占用高达 **14.8 GB**；
- `~/.workbuddy/workspace/sessions/` 物理占用 **1.2 GB**。

进一步对 `sessions` 目录进行物理文件条目枚举：

```bash
# 2. 统计 sessions 目录下的物理文件总数
find ~/.workbuddy/workspace/sessions -type f | wc -l
```

**惊人证据**：
终端输出了一个完全突破系统常规开发认知的天文数字——**321,489 个小文件**！

### 探针 2：文件系统元数据压力与 APFS 遍历延迟测量

在 APFS 文件系统中，单目录或多层嵌套树下堆积超过 30 万个小文件时，VFS 的目录遍历与 Inode lookup 操作将产生巨大的缓存失效。我们通过 Python 探针测试 `os.stat` 与 `os.walk` 的耗时：

- 正常目录遍历（< 1,000 文件）：平均耗时 **1.8 ms**；
- 遍历 `~/.workbuddy/workspace/sessions`：耗时飙升至 **48.7 秒**，期间产生极密集的内核 APFS VNode 锁竞争。

### 探针 3：句柄审计与文件持有状态排查 (`lsof`)

32 万个文件是否正在被活跃的 WorkBuddy 进程使用？我们使用 `lsof` 深入审计：

```bash
# 检查当前是否有进程持有 sessions 下的文件
lsof +D ~/.workbuddy/workspace/sessions
lsof +D ~/.workbuddy/logs/sandbox
```

**审计结果**：
- 在 14.8 GB 的 PTY 日志中，仅有**当前活跃终端正在写入的 2~3 个 `.log` 文件**被 `sandbox-core` 持有（fd 处于写入态）；其余数千个历史日志文件的持有句柄数为 **0**（完全孤立）；
- 在 32 万个 session 快照小文件中，仅有当前正在活动的会话目录下存在 `center.backup.lock`，其余几十个历史会话目录全部处于无进程持有的陈旧废弃状态。

### 探针 4：逆向代码逻辑与 `sandbox-cli-gc` 内存雪崩机制

我们逆向反编译了位于 `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.6.10/sandbox-cli-gc` 的二进制程序与 WorkBuddy 会话生命周期代码，发现了两大致命工程设计缺陷：

1. **PTY 日志只写不删，零生命周期管理**：
   - 官方虽然为每个终端输出设计了 13MB 的单文件滚动逻辑，但**完全没有设置目录总容量硬顶（Hard Limit）**，**也完全没有设计任何基于时间戳的 TTL 淘汰机制**；
   - 只要用户持续使用终端，每一行输出都忠实地在磁盘上永久累积，直至把用户整块硬盘吃满写爆。
2. **会话快照级联清理缺失与 GC 自身沦为 I/O 炸弹**：
   - 每次 Agent 修改代码或执行文件交互，WorkBuddy 都会在 `workspace/sessions/<session_id>/modify_backup` 与 `.modify_backup_meta` 中备份整份文件副本与元数据 JSON；
   - 用户关闭会话或开启新会话后，WorkBuddy 官方代码**从未在前端或后端调用任何级联删除清理钩子**；
   - 官方试图亡羊补牢，写了一个后台进程 `sandbox-cli-gc`，监听 `FSEventStream` 并定期对 sessions 目录执行 GC 扫描；
   - 但因为快照小文件累积到了 32 万个，`sandbox-cli-gc` 为了在内存中构建所有文件的遍历图，在堆上无节制分配对象，导致其自身 RSS 物理内存直接吃爆 **471.2 MB**；
   - 每次该 GC 进程启动深度遍历，都会疯狂打满磁盘读 IOPS（实测持续 1,800+ IOPS），造成整机文件系统严重饥饿假死！

### 探针 5：日志分卷增长速率与滚动切片计量 (`~/.workbuddy/logs/sandbox/`)

我们进一步对 PTY 终端日志的生成速率与分卷机制进行了高频时序采样：

1. **单分卷硬编码滚动阈值**：
   - WorkBuddy 底层 `sandbox-core` 将单个日志分卷硬编码为 **13.0 MB** 切片；
   - 分卷以命名序列 `<session_id>_output.log`、`<session_id>_output.log.1`、`<session_id>_output.log.2` 依次向后追加；
2. **高强度 Agent 任务下的物理产出速率**：
   - 在多 Agent 并发自动化构建、长文本交互与爬虫/测试运行期间，终端输出频率可达 **150 ~ 300 lines/s**；
   - 实测平均 **4 ~ 6 分钟** 即可写满一个 13MB 独立切片；
   - **单小时日志吞吐速率**：稳定在 **150 MB ~ 200 MB/h**（每小时产出 11 ~ 15 个独立切片）；
   - **单日累积增量**：高达 **3.6 GB ~ 4.8 GB/天**；
   - 连续高强度运行 3 ~ 4 天后，累积切片超过 **1,100+ 个**，在零 TTL 与零容量上限保护下，总占用毫无悬念地冲破 **14.8 GB**，直逼磁盘告警红线！

---

## 三、最终白盒物理凭证

以下为我们在真实生产环境下抓取并留存的不可伪造物理证据：

### 1. 物理计量指标对比

| 物理计量项 | 事故现场实测值 | 正常工程合理水准 | 偏离倍数 / 危害评估 |
| :--- | :--- | :--- | :--- |
| **`logs/sandbox` 目录体积** | **14.8 GB** | ≤ 500 MB | 超标 **30 倍**（无限吞噬磁盘） |
| **日志分卷滚动增长速率** | **13MB/卷，150~200 MB/h** (单日累积 3.6~4.8 GB) | 按时间/大小轮转且有 TTL (≤ 500 MB) | 线性无限增长，零淘汰机制 |
| **`sessions` 物理小文件总数** | **321,489 个** | ≤ 2,000 个 | 超标 **160 倍**（APFS 元数据瘫痪） |
| **`sandbox-cli-gc` 常驻内存 (RSS)** | **471.2 MB** | ≤ 20 MB | 超标 **23 倍**（严重内存泄漏） |
| **遍历 Sessions 耗时** | **48.7 秒** | ≤ 10 ms | 恶化 **4870 倍** |
| **GC 扫描时的随机读 IOPS** | **1,850 IOPS** | 0 IOPS | 长期霸占磁盘队列深度 |
| **历史孤儿文件持有句柄数 (`lsof`)** | **0 open fds** | 0 open fds | 官方缺乏自动回收钩子 |

### 2. 物理目录结构采样凭证

```text
~/.workbuddy/workspace/sessions/
├── 0edf168b-3d63-4ef1-a565-d7f5eefd0e63/
│   ├── modify_backup/              <-- 单会话内堆积上万个备份源文件
│   │   ├── ... (8,412 files)
│   ├── .modify_backup_meta/        <-- 单会话内堆积上万个元数据 json
│   │   ├── ... (8,412 files)
│   └── snapfile/                   <-- 历史快照切片
├── 932069d4-9b34-4abb-966c-a2fb999bb8ec/
│   ├── modify_backup/              <-- (14,209 files)
... (超 40 个陈旧会话目录，累计 321,489 个物理文件)
```

### 3. 系统内存采样证据 (`ps aux`)

```text
USER       PID  %CPU %MEM      VSZ    RSS   TT  STAT STARTED      TIME COMMAND
songshiyao 8921  98.4  2.9  3849120 482508   ??  R    Fri02PM  64:18.92 ~/.workbuddy/.../sandbox-cli-gc
```
*(注：物理常驻内存 RSS 达到 482,508 KB ≈ 471.2 MB，单核 CPU 接近 100%)*

---

## 四、Toolkit 根治方案：我们的工具怎么修的

面对这一让普通开发者束手无策的底层屎山，我们在 `workbuddy-toolkit` 中设计并落地了**零侵入、句柄感知、外科手术式修剪**的看门狗治理架构：

### 1. 核心设计原则：活跃工作区绝对保护 (In-Flight Workspace Protection)

根据全局工程规范，`lsof == 0` 虽证明无进程占用，但不能盲目 `rm -rf`。我们确立了以下治理硬边界：
1. **活跃句柄感知保护**：正在被进程持有的 open fd，严禁直接 `unlink`，仅在超过阈值时执行安全截断（`truncate` 至 0 字节），杜绝因误删活动日志引发写挂掉或僵尸 fd；
2. **白名单靶向切除**：对会话快照只清除 `modify_backup`、`.modify_backup_meta` 和 `snapfile` 等纯衍生临时中间件，严禁伤及用户代码资产；
3. **活动锁保护**：存在 `center.backup.lock` 且持有锁的会话绝对不触碰。

### 2. 四重物理看门狗实现 (`bin/workbuddy-log-guard`)

在 `workbuddy-log-guard` 中完整实现四重防御：

```python
# 核心实现逻辑切片 (bin/workbuddy-log-guard)

# 1. 活跃句柄递归排查 (跨平台支持 macOS/Linux lsof 及 Windows 共享锁感知)
open_files = get_open_files(LOG_DIR)
open_files.update(get_open_files(SESSIONS_DIR))

# 2. 单文件 30MB 物理熔断 (防止单文件无限暴走)
for fp in all_log_files:
    if os.path.getsize(fp) > 30 * 1024 * 1024:
        truncate_file(fp)

# 3. 36h TTL 历史日志淘汰 + 2GB 目录总量硬顶截断
# 当目录总容量 > 2048MB 时，按 mtime 倒序修剪至 1536MB
if get_dir_size(SANDBOX_DIR) > 2048 * 1024 * 1024:
    prune_to_target(SANDBOX_DIR, target_bytes=1536 * 1024 * 1024, open_files=open_files)

# 4. 会话快照外科手术式定向修剪 (clean_session_snapshots)
def clean_session_snapshots(sessions_dir, open_files, ttl_hours=72, max_keep=10):
    # 保护最近活跃的 10 个会话
    # 超过 72 小时且无 active lock 的陈旧会话，靶向切除 modify_backup / .modify_backup_meta
    for sp in candidate_sessions:
        if is_session_locked_or_in_flight(sp, open_files):
            continue
        for target in ["modify_backup", ".modify_backup_meta", "snapfile"]:
            shutil.rmtree(os.path.join(sp, target), ignore_errors=True)
```

### 3. CLI 手动触发与自动化巡检

用户可随时在终端执行快速治理与审计：

```bash
# 1. 查看当前沙盒与快照健康状态
wb-sandbox status

# 2. 手动执行外科手术式治理与孤儿进程回收
wb-sandbox clean

# 输出示例：
# ✔ 已清理 38 个历史会话快照与 12 个 shell 镜像，释放磁盘 14210.50 MB。
# ✔ 已安全规避正在活动的 2 个会话与活动文件。
```

同时，`install.py` / `install.sh` 安装时已自动注册原生系统定时守护：
- macOS: `~/Library/LaunchAgents/com.workbuddy.log-guard.plist`（每 30 分钟静默守护）
- Linux: `systemd --user` timer 或 crontab
- Windows: `schtasks` 计划任务

### 4. 治理后物理验证凭据

治理生效后，我们重新执行物理测量：
- `~/.workbuddy/logs/sandbox` 体积稳定保持在 **< 200 MB**；
- `~/.workbuddy/workspace/sessions` 文件总数由 **321,489 个骤降至 142 个**；
- 会话目录遍历耗时由 **48.7 秒回归至 2.1 毫秒**；
- `sandbox-cli-gc` 因无冗余文件，常驻物理内存由 **471MB 归零**（空闲休眠），系统 I/O 卡顿彻底解除！

---

> 🧭 **导航入口**：[🔙 返回事故总览矩阵](README.md) │ [📖 返回 Toolkit 主 README](../../README.md#16--生产事故深水排查与白盒物理凭证库seatbelt-17-万行规则雪崩pty-5s-延迟与四大草台班子工程缺陷) │ [下一篇：事故二 ➔](INCIDENT_02_CARGO_MULTI_AGENT_SCCACHE.md)

