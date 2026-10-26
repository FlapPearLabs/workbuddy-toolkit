# WorkBuddy Toolkit

[![CI: Cross-Platform Matrix](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/workflows/ci.yml)
[![Release: v0.7.0](https://img.shields.io/badge/Release-v0.7.0-blue.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Tests: 200/200 Passed](https://img.shields.io/badge/Tests-200%2F200%20Passed-brightgreen.svg)](tests/)
[![Security: Zero-Leak](https://img.shields.io/badge/Security-Zero--Leak%20Audit%20Passed-success.svg)](.github/workflows/ci.yml)
[![Platform: macOS | Linux | Windows](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-brightgreen.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)

**让 WorkBuddy 多账号真正适合长期使用。**

WorkBuddy Toolkit 是一套本地旁路工具（sidecar），用于解决多账号切换、凭据生命周期、自动签到、跨账号工作区、模型容灾和运行时稳定性问题。

```text
登录多个账号  →  保存账号配置  →  秒级切换
                    │
                    ├── 自动签到 / 健康巡检
                    ├── 工作区与历史会话共享
                    ├── 跨账号记忆汇总（去重择优，原文不动）
                    ├── WorkBuddy 5.6+ 凭据兼容
                    ├── 命令行 / 模型清单 / 容灾路由
                    └── 沙盒治理 / 日志保护 / 环境诊断
```

**只想把工具用起来？** 直接看 [快速开始](#快速开始)。  
**想知道它为什么这么设计？** 看 [架构说明](docs/architecture.md)、[工程笔记](docs/engineering-notes.md) 和 [事故复盘](docs/incidents/README.md)。

---

## 为什么需要 WorkBuddy Toolkit？

多账号本身不难。难的是多账号长期运行后出现的状态问题。

| 原生使用中的问题 | Toolkit 的处理方式 |
|---|---|
| 添加或切换账号时要反复走登录流程 | 保存本地账号配置，使用 `wb-login` / `wb-switch` |
| 切账号后历史会话、工作区像“消失”了一样 | 复用 WorkBuddy 的共享会话语义，保持本地工作区连续 |
| 每个账号都要重新教一遍称呼、偏好和规矩 | `wb-memory` 汇总各账号记忆，只把规则跨账号发布，重复条目保留质量更高的一条，原文不改写 |
| WorkBuddy 自动刷新 Token 后，旧账号配置可能覆盖新状态 | 切换前先同步当前凭据，再执行替换 |
| 副号长期不用，失效时才发现 | `wb-audit` + `wb-status` 做健康巡检 |
| 每日签到、连续任务需要重复操作 | `wb-checkin` + 平台原生调度 |
| WorkBuddy 更新后内部格式或运行时行为变化 | `wb-doctor` 显式检查兼容性和上游漂移 |

Toolkit 还提供模型资产查看、终端调用、可选容灾路由、沙盒自愈和日志生命周期治理。这些是高级能力，不是第一次安装必须理解的内容。完整能力索引见 [功能参考](docs/feature-reference.md)。

---

## 快速开始

### 1. 安装

macOS / Linux / Windows 通用推荐方式：

```bash
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git ~/.workbuddy/toolkit
cd ~/.workbuddy/toolkit
python3 install.py
```

Windows 如果使用 `python` 命令：

```powershell
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git $HOME\.workbuddy\toolkit
cd $HOME\.workbuddy\toolkit
python install.py
```

也可以使用平台原生脚本：

```text
macOS / Linux   ./install.sh
Windows         .\install.ps1
```

默认只安装命令行工具，**不改数据库、不注册后台任务**。交互式终端中会逐项询问可选能力；也可用 `--init-workspace`、`--with-checkin`、`--with-log-guard`、`--with-router`、`--with-services`、`--no-input` 显式指定，详见 [入门指南](docs/getting-started.md#2-推荐安装方式)。

### 2. 初始化并检查环境

```bash
workbuddy init
workbuddy doctor
workbuddy status
```

`doctor` 是关键步骤。WorkBuddy 是 Toolkit 的上游依赖，单看版本号不能证明当前运行时一定兼容。

### 3. 添加并切换账号

```bash
wb-login
wb-list
wb-switch
```

### 4. 跑一次日常任务

```bash
wb-checkin
wb-audit
```

完整安装说明见 [入门指南](docs/getting-started.md)。

<details>
<summary><strong>让 Codex / Claude Code / Cursor / Hermes 等 AI 编程 Agent 帮你安装</strong></summary>

把下面这段发给能执行终端命令的 Agent：

```text
请帮我安装并验证 WorkBuddy Toolkit：

1. 克隆 https://github.com/FlapPearLabs/workbuddy-toolkit.git 到 ~/.workbuddy/toolkit。
2. 根据当前操作系统运行 `install.py --no-input`；如果 Python 命令不同，请自行适配。
3. 依次运行 workbuddy init、workbuddy doctor、workbuddy status。
4. 不要修改 WorkBuddy 应用包本体。
5. 如果 doctor 报告不兼容，停止后续写操作并告诉我具体诊断结果。
6. 如果环境支持任务调度，再询问我是否启用每日 wb-checkin；我确认后再运行 `install.py --with-checkin`，不要擅自创建我没有确认的后台任务。
7. 最后汇报安装位置、doctor 结果、当前账号状态和后台调度状态。
```

更完整的说明见 [入门指南中的 AI Agent 安装部分](docs/getting-started.md#6-让-ai-coding-agent-帮你安装)。

</details>

---

## 核心能力

### 交互式控制中心 — `wb-tool`

不喜欢记忆琐碎的 CLI 命令与参数？直接输入 `wb-tool`（或 `workbuddy tool`），即可启动遵循《Don't Make Me Think》与设计四原则（CRAP）打造的极简终端控制台：

```text
╭─ WorkBuddy 工具箱 (wb-tool v0.7.0) ─────────────────────────────────────────╮
│  当前账号: Cat_1 (正常) │ 今日消耗: 92.2 积分 │ 已存账号: 3 个               │
╰──────────────────────────────────────────────────────────────────────────────╯

[ 主菜单 ]
────────────────────────────────────────────────────────────
  [1] 查看积分  ── 查看今日与历史消耗，支持实时刷新和明细下钻
  [2] 切换账号  ── 免扫码一键切号，支持查看已存账号并录入新号
  [3] 每日签到  ── 一键领取每日积分奖励，自动发送保活打卡对话
  [4] 模型切换  ── 查看可用模型列表与费率，切换常用默认模型
  [5] 清理磁盘  ── 清理后台残留临时缓存，释放被占用的电脑空间
  [6] 重启软件  ── 一键关闭并重新打开客户端，使新配置即时生效
  [0] 退出    ── 关闭工具箱，返回命令行终端
────────────────────────────────────────────────────────────
请选择操作编号 [0-6]: 
```

- **零记忆负担**：全中文直观选项，摒弃生硬技术黑话；
- **面包屑级联回退**：子菜单按 `0`、`q` 或 `Esc` 原地返回上一级，仅在主菜单退出；
- **连续操作闭环**：操作完成后原地刷新顶栏状态卡片，退出时自动输出会话审计报告。

### 账号管理

```text
wb-login      添加 / 刷新账号配置
wb-list       查看已保存账号
wb-status     查看当前账号与凭据状态
wb-switch     切换账号
wb-remove     删除账号（移入本地回收站，可恢复）
wb-remove --list-trash       查看回收站
wb-remove --restore <文件名> 恢复单个账号
wb-remove --empty-trash      清空回收站（不可恢复）
wb-memory     跨账号记忆汇总（去重择优，只发布规则）
wb-audit      检查账号健康度
```

核心目标不是“能切号”，而是**切号时尽量不破坏 WorkBuddy 已经刷新的最新状态**。

记忆汇总默认不开启。开启后切号时会把其他账号的**规则**追加到当前账号 `MEMORY.md` 末尾的受管段落里：账号原文逐字保留，疑似重复的条目只保留质量更高的一条，落选版本留档。

```text
workbuddy memory collect        汇总所有账号 MEMORY.md，去重择优入库
workbuddy memory compact        给超长/偏好事实类条目建分片，窗口里只留一行索引
workbuddy memory apply [账号]   渲染进指定账号（省略则全部）
workbuddy memory rebalance      把准则/画像按节分流到 SOUL、USER（默认只出计划）
workbuddy memory forget <关键词>  移出共享库并留墓碑，不再复活（默认只预览）
workbuddy memory conflicts      查看互相否定的规则
workbuddy memory status         库规模、可发布条数、各账号字数
workbuddy memory restore <账号>  用快照还原（同时摘掉分诊写入的 SOUL / USER 段落）
workbuddy memory on / off       开启 / 关闭切号时自动汇总渲染
```

- **`--budget N`**：共享段落自身的字数预算，默认 800。每条按“正文 + 3”计，最多 20 条，先到先得；给账号原文留出 4,000 字窗口里的位置，不是文件总长度。渲染按最终整篇长度校验，原文优先，原文自己就顶满 4,000 时不会再补换行。
- **`apply` 的基线是“文件当前的自有内容”**：你在 `MEMORY.md` 里删掉一条，下次 `apply` 不会把它写回来；只有 `restore` 才回到快照。
- **分诊按节搬**：文档有 ≥2 个 `##` 标题时整节迁移（标题、列表、缩进子项一起走），散条目文档才逐行搬；CLI 逐节打印“留下 / 搬走”。实测一个 5,953 字的记忆分诊到 2,542 字，同账号 SOUL 从 1,792 字增到 5,253 字。
- **为什么只发布规则不发布事实**：客户端只注入 `MEMORY.md` 前 4,000 字，事实类条目又长又多，放行就会挤掉别人的原文；况且路径、客户名、内部 URL 这类本机事实跨账号带过去只会造成污染。默认只发布红线、显式指令、项目约定（P0–P2），含本机路径 / 邮箱 / URL / UUID 的条目、以及以 `>` / `*` / `_` / `|` 开头的文档碎片一律不跨账号。
- **长规则落分片**：`compact` 把超长或偏好/事实类条目的原文写到 `cache/shared_memory/shards/<id>.md`，`apply` 只在窗口剩余预算里补最多 8 行索引（`- [P1] … → shards/…`）。分片正文不会被注入，它是“规则别丢”的存放处。
- **可回滚**：目录在 `~/.workbuddy/cache/shared_memory/`，快照 `originals/<uid>/`、备份 `backups/<账号目录>/`（保留最近 10 份）。`restore` 会连 SOUL / USER 里由分诊写入的受管段落一起摘掉，等于回到分诊前。

完整用法、失效场景与回滚步骤见 [跨账号记忆共享](docs/memory-sharing.md)，能力边界见 [功能参考](docs/feature-reference.md#跨账号记忆汇总--workbuddy-memory)。

### 自动化

```text
wb-checkin    每日签到与连续任务
wb-usage      积分消耗与流速统计
```

后台任务默认不开启。需要时用 `install.py --with-checkin` 接入系统原生调度：

- macOS：`launchd`
- Linux：`systemd --user`，必要时降级到 `cron`
- Windows：任务计划程序；被组策略或安全软件拦截时，自动降级为登录时执行

> 多账号自动签到与保活对话会以客户端身份批量访问 WorkBuddy 服务，可能触发平台风控或违反服务条款，请自行评估。

> **Windows 降级触发器**：如果 `schtasks` 注册失败，安装器会在当前用户的「启动」
> 文件夹写入 `WorkBuddyDailyCheckin.vbs` 作为兜底（只在启用了 `--with-checkin`
> 且任务计划不可用时才会出现）。`uninstall.py` 会删除它，任务计划恢复后重新运行
> 安装器也会自动清理。
>
> 如果 `schtasks` 本身可用、只是 `daily` 触发器被策略限制，也可以手动改用登录
> 触发器：`schtasks /create /tn WorkBuddyDailyCheckin /tr "<命令>" /sc onlogon /f`。

### 开发者工具

```text
wb-chat       终端直接调用 WorkBuddy 模型
wb-models     查看模型资产与倍率信息
wb-router     可选模型容灾路由
wb-doctor     环境、凭据与运行时诊断
wb-help       当前版本命令帮助
```

### 运行时稳定性

Toolkit 还包含一组从真实故障中长出来的保护机制：

- WorkBuddy 5.6+ 加密凭据兼容；
- 跨账号工作区 / 会话连续性；
- 跨账号记忆汇总（去重择优、原文不改写、快照可还原）；
- 沙盒规则与会话状态修复；
- 异常日志 / 临时文件生命周期限制；
- IPC 超时与异常边界；
- 并发修复路径的互斥保护；
- 可回滚的旁路安装模型。

这些能力的完整解释不再塞在 README 中。先看 [功能参考](docs/feature-reference.md)，需要理解实现边界时再看 [架构说明](docs/architecture.md) 和 [工程笔记](docs/engineering-notes.md)。

---

## 按你的目的阅读

### 我只想把工具用起来

按这个顺序看：

1. [入门指南](docs/getting-started.md)
2. [命令参考](docs/command-reference.md)
3. 出现异常时先运行 `wb-doctor`

### 我想理解它怎么工作

按这个顺序看：

1. [功能参考](docs/feature-reference.md)
2. [架构说明](docs/architecture.md)
3. [工程笔记](docs/engineering-notes.md)
4. [事故复盘](docs/incidents/README.md)
5. [架构决策记录（ADR）](docs/adr/) / [详细规格](docs/specs/)

### 我是 AI Agent

仓库提供 [`llms.txt`](llms.txt) 作为轻量入口。执行任何状态修改前，仍应以当前代码、命令帮助和 `workbuddy doctor` 的实际结果为准。

---

## 工作原理

```text
                     WorkBuddy 桌面端
                           │
          ┌────────────────┼────────────────┐
          │                │                │
        凭据             SQLite          运行时
          │                │                │
          ▼                ▼                ▼
      账号配置库        会话共享         沙盒 / 日志
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                   WorkBuddy Toolkit
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       账号命令行         自动化            诊断
       登录/列表          签到             doctor/audit
       切换/状态          定时任务          事故取证
                           │
                           ▼
                       可选容灾路由
```

### 四条设计原则

**1. 旁路集成，不修改应用本体**  
尽量在 WorkBuddy 外部完成集成，不把修改永久写进应用包。

**2. 切换前先保存最新状态**  
切换账号前先同步当前活跃状态，避免旧账号配置反向覆盖新 Token。

**3. 解密用于运行，不用于明文存储**  
需要运行时访问加密凭据时，不因此把敏感字段长期保存成明文副本。

**4. 主动检测上游变化**  
WorkBuddy 更新后如果路径、格式或协议发生变化，优先让 `doctor` 报出来，而不是制造“看起来正常”的假绿状态。

更详细的组件关系见 [架构说明](docs/architecture.md)。

---

## 工程笔记

README 只保留三个最能说明这个项目为何存在的案例。

### 1. WorkBuddy 5.6+ 加密凭据兼容

WorkBuddy 5.6 系列改变了本地敏感凭据的表示方式。旧脚本如果默认 `accessToken` / `refreshToken` 永远是普通字符串，会直接失效。

Toolkit 增加运行时兼容层，同时坚持一个边界：**需要解密能力，不等于把解密结果持久化。**

[查看工程笔记 →](docs/engineering-notes.md#3-workbuddy-56-改变了凭据存储方式)

### 2. “切号后工作区丢了”并不等于数据丢了

调查发现，本地记录仍在；变化的是账号身份参与了会话可见性过滤。Toolkit 因此处理会话归属和共享语义，而不是复制一套项目目录。

[查看工程笔记 →](docs/engineering-notes.md#2-工作区没有丢只是被账号过滤隐藏了)

### 3. 沙盒和日志问题最终变成了生产事故

项目后期遇到过异常日志增长、会话产物堆积、规则膨胀和命令卡顿等真实故障。这些事故最终形成了日志保护、沙盒自愈和更深的 `doctor` 取证路径。

证据和复盘单独保存：

- [事故 01：沙盒日志与快照耗尽](docs/incidents/INCIDENT_01_SANDBOX_LOG_SNAPSHOT_EXHAUSTION.md)
- [事故 02：多 Agent Cargo 构建缓存压力](docs/incidents/INCIDENT_02_CARGO_MULTI_AGENT_SCCACHE.md)
- [事故 04：Seatbelt 规则膨胀与 PTY 卡死](docs/incidents/INCIDENT_04_SEATBELT_RULE_EXPLOSION_AND_PTY_FREEZE.md)
- [事故 05：多账号共享工作区积分虚增、免登录入账号漏计与 CI 假性全绿](docs/incidents/INCIDENT_05_MULTI_ACCOUNT_SESSION_OVERLAP_AND_TIMEZONE_DRIFT.md)

[查看全部事故复盘 →](docs/incidents/README.md)

---

## 常用命令速查

| 命令 | 用途 |
|---|---|
| `wb-login` | 添加或刷新账号 |
| `wb-list` | 查看账号配置 |
| `wb-status` | 查看当前状态 |
| `wb-switch` | 切换账号 |
| `wb-remove` | 删除账号（移入本地回收站，可恢复） |
| `wb-memory` | 跨账号记忆汇总（只发布规则，可还原） |
| `wb-audit` | 凭据健康巡检 |
| `wb-checkin` | 每日签到 / 连续任务 |
| `wb-usage` | 使用量与积分流速 |
| `wb-chat` | 终端模型调用 |
| `wb-models` | 模型资产与倍率 |
| `wb-router` | 模型容灾路由 |
| `wb-doctor` | 兼容性和故障诊断 |
| `wb-help` | 查看当前版本帮助 |

完整说明见 [命令参考](docs/command-reference.md)。

---

## 平台支持

| 平台 | 系统集成 | 凭据位置 |
|---|---|---|
| macOS | `launchd` | WorkBuddy macOS 应用数据目录 |
| Linux | `systemd --user` / `cron` 降级方案 | XDG 风格应用数据目录 |
| Windows 10/11 | 任务计划程序 / 登录启动项降级 | `%APPDATA%` 应用数据目录 |

要求：

- Python 3.8+（3.8 校验只针对 WorkBuddy 自带解释器；PATH 里的解释器按原样使用，不做版本检查）
- WorkBuddy 已安装并至少登录过一次
- Toolkit 基础安装主要使用 Python 标准库，不要求额外 pip 依赖

> **Windows 用户注意**：`wb-*.cmd` 启动器是安装时生成的文本，不是运行时解释的。
> 升级 Toolkit、或修复了启动器相关的问题之后，需要重新运行一次
> `python install.py` 才会生效。启动器查找解释器的顺序是：WorkBuddy 自带
> Python → `PATH` 中的 `python`（自动跳过 Microsoft Store 的占位符）
> → `py` launcher；三者都不可用时以退出码 9009 报错，而不是弹出应用商店。
>
> 启动器会把 `%LOCALAPPDATA%\Microsoft\WindowsApps\` 整段排除。该目录下既可能是
> 0 字节占位符（执行会弹出应用商店），也可能是商店版 Python 的可执行别名；
> 为了避免把占位符当解释器执行，这里选择一律排除，而不是逐个探测。
> 商店版 Python 用户请改用官方安装包，或依赖 WorkBuddy 自带解释器。
实际兼容性请运行：

```bash
workbuddy doctor
```

---

## 安全与回退

Toolkit 的安全边界比“功能更多”更重要：

- 账号配置保留在本机，所有凭据文件以 0600 原子写入；
- 加密凭据兼容不等于建立明文凭据仓库：无法加密时会明确告警，`doctor` 会列出明文保存的账号；
- 仓库不内置任何第三方 API Key，CI 与单元测试都会做 Zero-Leak 扫描；
- 容灾路由只监听 127.0.0.1，并要求每台机器独立生成的 Token（`~/.workbuddy/router_token`）；
- 后台任务默认关闭，开启后也有明确边界，不应无限等待或无限增长；
- 上游不兼容时应暴露诊断，而不是静默继续；
- 安装是可回退的：会话 / 自动化任务的原始归属与 models.json 原值都会先备份，回滚与卸载据此恢复。

卸载：

```bash
python3 uninstall.py            # 交互式；--yes 同时回滚工作区共享，--keep-config 保留配置
```

也可以使用对应平台的卸载脚本。卸载会注销后台任务、还原 models.json、按备份恢复会话归属，并保留账号凭证与 `~/.workbuddy/toolkit` 下的源码仓库。

如果你正在排查升级后的兼容问题，先运行 `wb-doctor`，再决定是否卸载。

---

## 文档导航

| 文档 | 什么时候看 |
|---|---|
| [入门指南](docs/getting-started.md) | 第一次安装和配置 |
| [功能参考](docs/feature-reference.md) | 查看完整能力索引 |
| [命令参考](docs/command-reference.md) | 找命令和使用场景 |
| [架构说明](docs/architecture.md) | 理解组件边界和设计原则 |
| [工程笔记](docs/engineering-notes.md) | 理解关键根因、逆向过程和设计取舍 |
| [事故复盘](docs/incidents/README.md) | 看真实事故、证据与修复 |
| [架构决策记录（ADR）](docs/adr/) | 看重要架构决策 |
| [详细规格](docs/specs/) | 看行为约束和详细规格 |
| [积分计量规格](docs/spec-credit-metering.md) | 看积分 / 使用量计量设计 |
| [`llms.txt`](llms.txt) | 给 AI Agent 的轻量仓库入口 |

---

## 项目理念

WorkBuddy Toolkit 不试图把所有 WorkBuddy 行为重新实现一遍。

它更像一层可观察、可诊断、可回退的本地旁路：

```text
发现真实故障
    ↓
定位实际状态边界
    ↓
做最小可逆修复
    ↓
加入诊断和回归验证
    ↓
把证据留在 docs / incidents
```

README 负责回答“这是什么、为什么需要、怎么开始”。  
实现细节、逆向过程和事故证据留给需要深入的人。

---

## 开源协议

[MIT License](LICENSE)
