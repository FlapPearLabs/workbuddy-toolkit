# PR 工程审计报告

> 审计对象：`wb-logout`（WorkBuddy 账号登出功能）
> 审计时间：2026-10-24 14:55 – 15:10 (GMT+8)
> 审计性质：独立工程审计，非开发方自述
> 报告生成方式：依据当前可访问的对话记录、Git 对象、代码内容与测试输出重建

---

## 0. 审计范围与方法

### 0.1 证据来源

| 类别 | 具体来源 | 可访问性 |
|---|---|---|
| 学生指令 | 本次审计会话可访问的 8 条用户消息 | 可直接引用原文 |
| Agent 执行 | 同一会话内的工具调用记录与输出 | 可直接核验 |
| Git 对象 | 两个本地仓库的 `log` / `diff` / `branch` / `reflog` / `worktree list` | 可直接核验 |
| 测试输出 | 会话内实际执行的命令与返回 | 可直接核验 |
| 上游 PR 对照 | GitHub API 读取的 open PR 列表与详情 | 可直接核验 |

### 0.2 上下文缺口（必须前置声明）

**13:47–13:52 这一段活动在本次审计会话中不可访问。** 该时段（对目标仓库的初步侦察、connector 权限 403 的三次探测、一次 reconnect 尝试及其 401 结果）仅存在于 Agent 自行写入的工作日志摘要中，**没有原始对话记录**。凡涉及该时段，本报告一律标注为「部分核验」或「无法核验」，不据其推断学生行为。

### 0.3 证据等级定义

- **已核验**：有 Git 对象、代码、命令输出或对话原文直接支撑。
- **部分核验**：有间接证据（如 Agent 写入的日志），但原始记录缺失。
- **无法核验**：仅有事后的文字描述。

### 0.4 测试结论的时效声明

本报告引用的测试结果分两类，已在第 9 节逐项标注：

- **当时执行**：在开发过程中实际跑过、现在仍可复现的命令与输出。
- **本次补跑**：为撰写报告重新执行的验证。

---

## 1. PR 基本信息

| 项目 | 内容 |
|---|---|
| 目标仓库 | `FlapPearLabs/workbuddy-toolkit`（MIT，Python 3.8+） |
| PR 链接 | https://github.com/FlapPearLabs/workbuddy-toolkit/pull/27 |
| 本地分支 | `feat/logout-command` |
| 基准 SHA | `4e832c07bf35ffcae12fe42d2c71ffcf674cbabe`（origin/main） |
| 功能提交 SHA | `e8e83e8c9419f20de57225f03e2183214430b1ee` |
| 报告提交 SHA | `97448ee82ce6b48d9ddd0eef877c3e00d6dba9e6` |
| 最终 SHA | 以 PR 页面 head 为准（缺陷修复提交位于本报告更新之后） |
| 远端状态 | 已推送至 fork `nlsans/workbuddy-toolkit`，分支 `feat/logout-command` |
| 变更文件 | `bin/workbuddy`（logout 相关函数与两处路由）、`install.py`（别名注册）、`tests/test_logout.py`（11 项测试，新增文件）、`PR_ENGINEERING_AUDIT.md`（本报告，新增文件） |
| 合计 | 4 files，全部为新增，无既有逻辑改写（精确行数以 PR 页面 Files changed 为准） |
| 功能 | 新增 `workbuddy logout` / `wb-logout`：写登出标记后删除本地凭据文件，可预览、可备份 |

### 1.1 PR 创建过程（已核验）

PR 并非一次达成，前后经历三次失败：

| 阶段 | 阻塞点 | 证据 |
|---|---|---|
| 首次尝试 | GitHub connector 仅只读 | `create_repository` / `fork_repository` 均返回 403 `Resource not accessible by integration` |
| 二次尝试 | 本机无 GitHub 凭据 | `cmdkey /list` 无 github 记录；GCM 非交互模式返回 `Cannot prompt because user interactivity has been disabled` |
| 三次尝试 | 无 `gh` CLI、PATH 指向精简版 PortableGit | `gh: command not found`；`bin/` 下无 credential helper |

**最终解决路径（已核验）**：

1. 确认系统安装的 Git for Windows 自带 `git-credential-manager` 2.9.1，且系统级 gitconfig 已配 `credential.helper = manager`——此前误判"无法推送"实为用错了 git 二进制。
2. 由提交者在真实终端完成一次 OAuth 授权，凭据写入 Windows 凭据管理器（`cmdkey` 出现 1 条 github 记录，`GCM get` 可返回 `username=nlsans`）。
3. 通过 GitHub REST API 完成 fork（`nlsans/workbuddy-toolkit`，首次轮询即就绪）。
4. `git push fork feat/logout-command` 成功。
5. REST API 创建 PR #27，base `main` @ `4e832c0`。

**必须说明的一点**：本次 PR 的创建**完全依赖提交者手动完成 OAuth 授权这一不可省略的人工步骤**。Agent 曾尝试三种方式试图自动化（`GCM_INTERACTIVE=always` 拉 GUI、`never` 非交互、`GCM_GITHUB_AUTHMODE=devicecode`），全部失败：GUI 进程存在但取不到窗口标题且 5 分 29 秒无进展；非交互模式直接拒绝；devicecode 模式 stdout 零输出（GCM 2.9 的提示全部走 GUI）。

### 1.2 上游同类 PR 对照（本次审计新发现）

审计期间读取上游 open PR 列表，发现同一时段存在 4 个同主题 PR：

| PR | 作者 | 主题 | 与本次关系 |
|---|---|---|---|
| #25 | `wangkeyu-520` | `wb-remove` 删除已保存账号（软删除 + 活跃账号保护） | **功能互补，非重复** |
| #24 | `liyifei818` | 账号删除功能，移入本地回收站可恢复 | 同上 |
| #23 | `2708039738` | 支持删除本地已保存的账号凭证 | 同上 |
| #26 | `2708039738` | 跨账号共享整份账号档案 | 无关 |

**关键区分（已核验）**：上述 PR 操作对象是 `~/.workbuddy/auth_profiles/` 下的**账号备份**；本次 `wb-logout` 操作对象是 `.../Data/Public/auth/workbuddy-desktop.info`（**当前活跃凭据**）并写入 `.logged-out` 标记。两者作用域不同，不构成功能重复。

**但审计必须指出一个调研缺陷**：开发过程中只查阅了 README 的命令表和主文件代码，**未检查 open PR 列表**。若当时查看 #25，可直接借鉴其对抗测试设计、退出码处理、软删除思路与文档更新范围。这一遗漏属于 Agent 调研流程的缺失，第 8.3 节详述。

---

## 2. 执行摘要

### 2.1 实际完成的内容

1. 从 `app.asar` 逆向出 WorkBuddy 登出机制：登录态由「凭据文件 + `.logged-out` 标记」共同决定，且存在保护分支 WB-44172——凭据被删而标记缺失时，程序判定为"凭据意外丢失"并保留内存会话，这正是"删了文件也退不掉"的根因。
2. 先实现为独立技能（`~/.workbuddy/skills/workbuddy-signout`，commit `0604892`，11 项测试）。
3. 学生要求提 PR 后，重新调研上游架构，方案从"独立脚本"改为"集成进 `bin/workbuddy`"，避免游离模块。
4. 新增 `wb-logout` 子命令（+155 行）、安装器注册（+3 行）、9 项测试。

### 2.2 主要设计
- 顺序不可逆：**先原子写标记，再删凭据**。
- 删除前先备份到 `~/.workbuddy/logout_backup/<时间戳>/`。
- 默认预览，`--yes` 才落盘；客户端运行中则中止。
- 路径收敛为模块级常量，便于测试替换（沿用上游 `PROFILES_DIR` 做法）。

### 2.3 主要风险（详见 6.3、第 9 节）

| 级别 | 风险 | 状态 |
|---|---|---|
| P1 | `-f` / `--force` 被当作 `--yes` 别名，可跳过预览直接删除；与上游 #25 的 `--force` 语义冲突 | **已修复**（见 8.4） |
| P2 | `_logout_cache_targets()` 用未校验的 uid 拼接路径，理论上可越界 | **已修复**（见 8.4） |
| P2 | Linux 分支 `pgrep -f "CodeBuddy"` 为推测，未在 Linux 验证 | 未验证 |
| P3 | 备份目录无上限清理 | 未修复 |

### 2.4 测试状态
- 新增测试 **11/11** 通过（`tests.test_logout`）：初审时 9 项，缺陷修复后补 2 项。
- 补充的 2 项经**先红后绿**验证：回退到修复前版本时均失败，恢复后通过（见 8.4）。
- 上游全量 219 项：1 项报错，单独重跑该项通过，判定为中文 Windows 编码环境问题，与本次改动无关。
- 真实环境冒烟：预览模式验证通过，未修改任何真实凭据。

### 2.5 当前已知局限
- 无文档更新（未改 `README.md` / `docs/command-reference.md` / `docs/feature-reference.md`），而同批 #25 全部更新。
- 无对抗性测试，无回归逐命令对比。
- PR 的创建依赖提交者手动完成一次 OAuth 授权，Agent 无法全自动完成（见 1.1）。

---

## 3. 真实开发时间线

| 时间 | 阶段 | 发起方 | 实际动作 | 证据 |
|---|---|---|---|---|
| 11:34 | 需求输入 | 学生 | 提出登出需求，附三条约束 | 消息原文 |
| 11:34–11:49 | 分析定位 | Agent | 读 `~/.workbuddy` 结构；解析 `app.asar` 目录树；提取 `main/file-authentication-storage.js`、`dev-env-override.js`；定位 `getLogoutMarkerPath` 与 WB-44172 注释 | 工具调用记录 |
| 11:49–12:03 | 实现 v1.0.0 | Agent | 写独立技能；只读 `status` 验证 | 文件、命令输出 |
| 12:02 | 需求重复 | 学生 | 原文重发同一需求（切至 Agent 模式） | 消息原文 |
| 12:03–12:04 | 端到端验证 | Agent | 假 auth 目录跑完整闭环 + 还原；确认真实凭据未被触碰 | 命令输出 |
| 13:33 | 需求变更 | 学生 | 要求做成 PR 并测试，追加"影响即停"约束 | 消息原文 |
| 13:33–13:43 | 影响面审计 | Agent | 审出 6 处影响面缺陷并修复；11 项测试；`git init`；commit `0604892`；导出 bundle | 文件、命令输出、Git |
| 13:47–13:52 | 上游侦察 | **上下文缺失** | 记忆摘要称：读 README、三次 403、一次 reconnect 后 401 | **仅 Agent 日志，无法核验** |
| 13:55 | 需求变更 | 学生 | 要求把 PR 提到指定仓库 | 消息原文 |
| 14:02 | 需求聚焦 | 学生 | 要求解决权限与提交问题 | 消息原文 |
| 14:03–14:12 | 环境诊断 | Agent | 发现系统 Git 2.55 + GCM 2.9.1 可用；拉起 GCM 失败 | 命令输出 |
| 14:14 | 需求 | 学生 | 要求自动提交 | 消息原文 |
| 14:14–14:17 | 交互尝试 | Agent | GCM 三种模式均失败（GUI 无标题、非交互拒绝、devicecode 无 stdout） | 命令输出 |
| 14:18 | **需求纠偏** | **学生** | 要求先解决主文件读取问题 | 消息原文 |
| 14:19–14:31 | 定位 + 实现 | Agent | `git clone --depth 1`（1.5M）成功；grep 定位结构；实现 `wb-logout`；9 项测试；全量回归；冒烟；commit `e8e83e8` | 命令输出、Git |
| 14:55 | 审计 | 学生 | 要求独立审计 | 消息原文 |
| 15:05 | 提交要求 | 学生 | 要求把审计报告附加到 PR 并提交上游 | 消息原文 |
| 15:06 | **PR 创建完成** | Agent 执行 + 学生人工授权 | fork `nlsans/workbuddy-toolkit` → push `feat/logout-command` → REST API 建 PR #27 | PR 元数据、`git push` 输出 |
| 15:11 | 缺陷修复 | **学生**（回复"修"） | 修缺陷 A/B 两处、补 2 项测试、执行先红后绿校验、同步报告与 PR 正文 | diff、测试输出 |
| 15:12 | 报告一致性修正 | Agent | 因 PR 创建，原报告 §1"PR 不存在"失效，改写为实际状态 | commit diff |

**阶段跳过的记录**：全程**没有**出现"方案讨论—学生确认—再实现"的显式环节；**没有** Worktree；**没有**多 Agent 分工；**没有**独立审查者（无论人或 Agent）。

---

## 4. 学生原始指令摘录

> 以下均为逐字引用，未润色。省略号表示截断，未改动字词。

### 指令 1（11:34，初始需求）

> 我发现work Buddy登录的账号无法退出登录，帮我写一份可以退出登录的技能的程序，并且配好一个套长期共用的python环境。不要直接运行，不要影响已经存在的技能，不要让我安装别的软件。

- **学生想解决**：本机无法退出登录；同时要一个可复用的 Python 环境。
- **约束**：不运行、不影响现有技能、不装新软件。
- **Agent 执行**：逆向 `app.asar`，定位 WB-44172；写技能；全程只跑只读 `status`。
- **结果**：技能落 `~/.workbuddy/skills/workbuddy-signout/`；复用已有 venv（3.13.14），未装任何包。
- **审计结论**：**能证明**学生设置了明确的安全边界，且 Agent 遵守了（无写操作、无新增依赖）。**不能证明**学生参与了技术方案设计。

### 指令 2（12:02）

> （与指令 1 完全相同的原文重发）

- **Agent 执行**：未察觉是重复需求，直接进入端到端验证并补充交付说明。
- **审计结论**：无法判断学生意图（切换模式导致重发，还是要求重做）。**Agent 未就此澄清，属于沟通缺陷。**

### 指令 3（13:33）

> 做成pr并帮我测试一下，不要影响到我的电脑系统和其他软件如有影响立刻停止并改正技能代码

- **学生想解决**：交付形态从"本机脚本"升级为"可提交的 PR"，并追加系统安全约束。
- **Agent 执行**：做影响面审计，发现并修复 6 处问题（含 `*Extension` 通配扫描、`restore` 路径穿越）；11 项测试；`git init`；commit `0604892`。
- **结果**：技能 v1.1.0，工作区干净。
- **审计结论**：**这条指令是整轮工作中对结果影响最大的一条**——"如有影响立刻停止并改正"直接触发了安全审计，是学生主动设定的质量闸门。**能证明**学生具备风险前置意识；**不能证明**学生事先知道存在哪些具体缺陷。

### 指令 4（13:55）

> 帮我把pr发给https://github.com/FlapPearLabs/workbuddy-toolkit/pulls这个网页的作者

- **学生想解决**：把成果提交到具体上游仓库。
- **Agent 执行**：侦察仓库（部分核验，见 0.2）、fork 失败、报告阻塞。
- **结果**：未产生 PR。
- **审计结论**：学生对"向开源仓库提 PR"的流程认知不完整（该 URL 是 PR 列表页，操作对象应是仓库）。**能证明**目标明确；**不能证明**了解 fork/PR 机制。

### 指令 5（14:02）

> 帮我解决权限和无法提交的问题

- **Agent 执行**：诊断出"无法提交"的真实原因是 PATH 指向 WorkBuddy 精简版 PortableGit，而系统 Git 自带 GCM 且已配 `credential.helper=manager`。
- **审计结论**：学生把问题定义为"权限 + 提交"两个技术阻塞，方向正确但未给约束。**根因诊断完全由 Agent 完成。**

### 指令 6（14:14）

> 自动帮我提交

- **Agent 执行**：尝试 GCM 三种交互模式均失败，说明 OAuth 授权无法零交互。
- **审计结论**：学生期望全自动，但未意识到 OAuth 需人工授权一次。**Agent 未能在该轮说服学生完成授权，导致后续两轮仍在处理同一阻塞。**

### 指令 7（14:18）

> 先解决主文件的读取问题

- **学生想解决**：不打补丁式推进，先解决根因（读不到 193KB 主文件就无法正确集成）。
- **Agent 执行**：改用 `git clone --depth 1`，1.5M 拿到全仓；grep 定位 `get_auth_file()`(:52)、`main()`(:4212)、`atomic_write_json()`(:785)；随后完成真正的集成实现。
- **结果**：commit `e8e83e8`，321 行新增。
- **审计结论**：**这是学生在本轮中最有价值的一次判断**。此前 Agent 的方案是"提交独立 sidecar 模块 + 声明需维护者接线"，属于降级交付；学生要求先解决读取，直接导致方案升级为符合上游架构的完整实现。**能证明**学生具备"不接受降级交付、追根因"的工程直觉；**不能证明**学生事先知道用 git clone 可以解决。

---

## 5. 需求分析及代码定位

### 5.1 需求边界是否被区分（已核验）

| 概念 | 是否有明确区分 | 证据 |
|---|---|---|
| 清除本地活跃凭据 | ✅ | 实现直接操作 `AUTH_FILE` |
| 退出当前账号（含标记） | ✅ | 写入 `.logged-out`，与主程序恢复逻辑对齐 |
| 服务端账号注销 / 远端登出 | ✅ 明确排除 | 实现中无任何网络请求；代码注释与交付说明均声明"纯本地操作，不请求服务端吊销 token" |
| 删除已保存的账号备份（profile） | ✅ 明确排除 | 作用域为 `auth_profiles/`，本次不触及；与上游 #23/#24/#25 的边界清晰 |

### 5.2 真实凭据位置如何被找到（已核验）

不是猜测，而是从主程序逆向得出，链条完整：

1. 解析 `app.asar` 头部，列出 258 个含 auth/login/token 的文件名，过滤 `node_modules` 后锁定 `main/file-authentication-storage.js`。
2. 该文件 `getAuthSavePath()` 返回 `path.join(filePathService.sharedDataPath, 'auth', '<id>.info')`。
3. 反查 `sharedDataPath` 实现：`path.join(this.basePath, 'Data', 'Public')`。
4. 磁盘实探命中 `<LOCALAPPDATA>/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`（7158 B，`$wbEncrypted` 信封）。
5. 在 `dev-env-override.js` 中定位导出的 `vn`，其定义为 `getLogoutMarkerPath(t) { return \`${t}.logged-out\` }`。
6. 在 `file-authentication-storage.js` 中读到保护分支注释 `WB-44172`。

**交叉验证（本次审计新增）**：上游 `bin/workbuddy:63-64` 独立地使用了同一路径 `localappdata/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`，与逆向结论一致。

### 5.3 是否研究既有代码再确定实现位置（已核验）

| 环节 | 证据 |
|---|---|
| 先读上游结构再做方案 | 13:55 之后先读 README/`llms.txt`/目录，判断"不适合整包塞入" |
| 定位命令分发方式 | grep 到 `main()`(:4212)，确认是**手写 if/elif 链**而非 argparse |
| 定位写入惯例 | grep 到 `atomic_write_json(path, data, mode=0o600)`(:785)，新代码沿用同一套 tempfile + fsync + `os.replace` |
| 定位安装器注册点 | `install.py:47-62 CLI_ALIASES`、`:65-80 WINDOWS_SUBCOMMAND_SHIMS` |
| 测试风格对齐 | 读 `tests/test_toolkit.py:28-50`，采用其 `SourceFileLoader` + tempfile 沙箱模式 |

**结论：实现位置的确定确有代码依据，非推测。** 但需注意：这一整套调研发生在**第 7 条指令之后**，即学生在 14:18 才要求解决读取问题；在此之前 Agent 的方案（独立模块）是**未充分调研**的结果。

### 5.4 是否避免重复实现已有能力（部分核验）

- 复用了：`atomic_write_json` 思路、`AUTH_FILE`、`COLOR_*`、`subprocess` 探测模式、测试加载方式。
- **遗漏**：未复用 `get_active_account()` 来做"当前活跃账号"判定；未参考上游已有的文件锁、退出码规范（`sys.exit(0 if ok else 1)`）。
- **未做**：未检查 open PR（见 1.2），错过 #25 的对抗测试与软删除设计。

---

## 6. 工程工作流分析

### 6.1 Git（已核验）

| 项目 | 实际情况 | 评价 |
|---|---|---|
| 独立分支 | `feat/logout-command` | ✅ 做到了 |
| 分阶段 Commit | 技能仓库 1 个 commit；上游 1 个 commit | ⚠️ 未拆分子阶段 |
| Diff 检查 | 生成了 `format-patch`（19.9 KB） | ✅ 有检查动作 |
| 改动范围控制 | 321 insertions / **0 deletions** | ✅ 纯新增，未改既有逻辑 |
| Push / PR | 15:06 完成：push 至 fork，创建 PR #27 | ✅（依赖人工授权） |
| 回退操作 | 无（未出现需要回退的情形） | — |

`reflog` 完整记录（上游仓库）：
```
e8e83e8 HEAD@{0}: commit: feat: add logout command to clear local credentials
4e832c0 HEAD@{1}: checkout: moving from main to feat/logout-command
4e832c0 HEAD@{2}: clone: from https://github.com/FlapPearLabs/workbuddy-toolkit.git
```
**仅三步，无 rebase、无 amend、无 reset。历史干净但过程单薄。**

### 6.2 Worktree（已核验：**未使用**）

```
$ git worktree list
C:/tmp/wtk  e8e83e8 [feat/logout-command]
```

两个仓库各只有一个工作目录，`reflog` 中无任何 worktree 相关操作。

**明确结论：本次开发全程未使用 Git Worktree，未做分支物理隔离。** 单分支单目录串行开发，不存在并行冲突风险，但也没有并行收益。

### 6.3 多 Agent（已核验：**未使用**）

本次会话中**没有任何 Agent/子任务派发记录**。所有工作由单一 Agent 串行完成，无独立审查者，无并行实现。

| Agent/角色 | 接收任务 | 产出 | 验收方式 | 最终处理 |
|---|---|---|---|---|
| （无） | — | — | — | — |

**需要特别指出**：本次实现中存在**自己写代码、自己测试、自己判定通过**的情况。第 9 节中所有 PASS 结论均出自实现者自身的测试套件，**没有第三方复核**。这在教学评估中属于证据强度不足。

### 6.4 任务拆分与串并行

| 阶段 | 拆分情况 | 由谁决定 |
|---|---|---|
| 逆向定位 | 未拆分，一次连续完成 | Agent |
| 技能实现 → 影响面修复 | 学生用一条约束触发整体审查，未拆具体项 | 学生定原则，Agent 定细节 |
| 上游集成 | 拆为"读结构 → 写实现 → 写测试 → 回归" | Agent |

**没有任何一次拆分是由学生显式下达的**。学生提供的是目标与约束，分解由 Agent 完成。

### 6.5 "先讨论、再实现"是否发生

**未发生。** 8 条指令中没有任何一条要求先出方案再动手。时间线显示：指令 → 直接进入实现，中间无方案评审环节。

对照：同批 #25 的 PR 描述显示其作者至少产出了完整设计决策表（10 项决策 + 理由），但那属于事后文档，同样无法证明事前讨论过。

---

## 7. 设计决策与解耦

### 7.1 核心决策及其依据

| 决策 | 选择 | 依据 | 是否可核验 |
|---|---|---|---|
| 登出实现方式 | 写标记 + 删凭据 | 主程序 `restore()` 优先检查标记；WB-44172 保护分支 | ✅ 源码 |
| 顺序 | 先标记后删除 | 顺序颠倒会落入"凭据意外丢失"分支 | ✅ 源码注释 |
| 交付形态 | 集成进 `bin/workbuddy` | 上游为单文件 CLI，`wb-*` 由 install.py 生成 | ✅ 代码 |
| 测试隔离 | 模块级路径常量 | 沿用 `PROFILES_DIR` 的既有做法 | ✅ 代码 |
| `--deep` 范围 | 只清 account-snapshot + sidebar | 判断 `startup-route.json` 与账号无关 | ✅ 代码注释 |

### 7.2 模块解耦情况

新增内容全部为**独立函数**，未修改任何既有函数体：

- `atomic_write_text()`（:814）— 新增，不替换 `atomic_write_json`
- `get_logout_marker_path()`（:835）
- `is_workbuddy_running()`（:839）
- `_logout_cache_targets()`（:856）
- `run_logout()`（:875）
- `main()` 内新增 2 个分支（prog_name 路由、cmd 路由）
- 4 个模块级常量（:93-96）

**0 deletions 这一点是解耦的直接证据**：不存在对既有逻辑的改写，回归风险主要来自"新增分支是否抢占原有路由"。

### 7.3 考虑过但被否掉的替代方案

| 方案 | 为何被否 | 证据 |
|---|---|---|
| 提交独立 sidecar 模块 | 游离于单文件 CLI 架构之外，需维护者自行接线 | 13:55–14:18 期间的方案表述，后由学生指令 7 推翻 |
| `curl`/`urllib` 抓取主文件 | 反复超时、SSL 35 | 命令失败记录 |
| GCM devicecode 模式取凭据 | stdout 零输出，GCM 2.9 提示走 GUI | 命令输出 |

### 7.4 路由抢占风险（本次审计新发现）

`main()` 中新增 `elif cmd in ["logout", "signout", "sign-out"]` 位于 `save/backup` 之前、`status` 之后。由于 `login`/`switch`/`checkin` 已占用 `signin` 作为别名，而 `signout` 为新增词，**未与既有别名冲突**（已核验：既有 alias 列表无 signout/logo ut）。

但 `prog_name` 分支用 `if "logout" in prog_name` 做子串匹配，若未来出现名为 `xxx-logout-helper` 的启动器会误命中。当前 `CLI_ALIASES` 中不存在此类名称，**属潜在隐患而非现存缺陷**。

---

## 8. 问题发现与修复

### 8.1 开发过程中实际出现并修复的问题（已核验）

| # | 问题 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | `glob("*Extension")` 可能扫到别家软件目录 | 学生指令 3 触发的影响面审计 | 改为白名单 + 名称关键字过滤 |
| 2 | `glob("*.info")` 无差别处理同目录其他产品凭据 | 同上 | 加 `workbuddy`/`codebuddy` 前缀白名单 |
| 3 | `restore` 的 `originalPath` 零校验，可任意路径写入 | 同上 | 加写入白名单 + `relative_to` 防穿越 |
| 4 | `--deep` 顺带删 `startup-route.json`（与账号无关） | 同上 | 移出清理范围 |
| 5 | 备份无限累积 | 同上 | 保留最近 10 份自动裁剪 |
| 6 | `allowed_write_roots()` 未含 `--auth-dir` 目录 | 写测试时发现 | 增加参数传入 |
| 7 | 全量测试出现 1 项 error | 回归测试 | 定位为中文 Windows 编码问题，单独重跑通过，未改动代码 |

**关键观察**：1–5 全部由**学生的一条约束**（"如有影响立刻停止并改正"）触发，而非 Agent 自发进行安全审计。这既说明学生的约束设置有效，也说明**Agent 在没有约束时不会主动做影响面分析**。

### 8.2 学生干预记录

| 干预 | 性质 | 效果 |
|---|---|---|
| 指令 3"如有影响立刻停止并改正" | 质量闸门 | 直接导致 6 处缺陷被修 |
| 指令 7"先解决主文件的读取问题" | 方案纠偏 | 推翻降级方案，实现质量提升一个层级 |
| 指令 5"帮我解决权限和无法提交的问题" | 问题重定义 | 把模糊的"权限"拆成两个可诊断的技术问题 |

**不存在**以下行为（已核验）：
- 学生质疑 Agent 的技术判断（除约束外）
- 学生发现 Agent 遗漏的边界条件
- 学生要求增加测试（仅指令 3 有"帮我测试一下"）
- 学生要求独立验证，不相信 Agent 自述
- 学生识别不合理的复杂设计

### 8.3 审计发现的残留缺陷

以下问题在提交者要求下已修复，修复细节与验证见 8.4。**审计结论保留原始记录，不做追溯美化。**

#### 缺陷 A（P1）：`-f`/`--force` 被当作 `--yes` 别名

```python
# bin/workbuddy:882
assume_yes = any(a in ("--yes", "-y", "--force", "-f") for a in args)
```

**问题**：
1. `-f` 只有两个字符，极易误触，一旦命中将**跳过预览直接删除凭据**。
2. 与上游 #25 的语义冲突——该 PR 中 `--force` 表示"允许删除活跃账号"，即**放宽保护**；在本实现中 `--force` 却等于"跳过确认"，同名开关含义相反。
3. 与上游既有 `save --force`（覆盖写入）语义也不一致。

**建议**：只保留 `--yes` / `-y`；`--force` 若保留应明确为"允许在客户端运行时执行"，即当前 `--allow-running` 的别名。

**为何测试未发现**：9 项测试均直接传 `--yes`，未覆盖 `-f` 路径。

#### 缺陷 B（P2）：uid 未校验即拼接路径

```python
# bin/workbuddy:856-871
uid = (json.load(f) or {}).get("primary", {}).get("uid")
...
sidebar = os.path.expanduser(SIDEBAR_SNAPSHOT_TEMPLATE.format(uid=uid))   # :870
```

**问题**：`uid` 读自 `account-snapshot.json`，该文件可被本地篡改。若 uid 含 `../`，`os.remove` 将作用于白名单外的路径。实际危害受限（目标文件名固定为 `sidebar-list-snapshot.json`），但**违反最小权限原则**，且与第一阶段技能中已实现的写入白名单不一致——属于方案迭代中的能力退化。

**建议**：校验 uid 仅含 `[A-Za-z0-9-]`，或对拼接结果做 `relative_to` 校验。

#### 缺陷 C（P2，未验证）：Linux 进程探测为推测

```python
res = subprocess.run(["pgrep", "-f", "CodeBuddy"], ...)
```
上游 README 的进程名为 WorkBuddy；Linux 实际进程名未验证。若探测恒为 False，登出将不会拦截"客户端运行中"的危险情形。

#### 缺陷 D（P3）：备份目录无清理

每次登出生成 `~/.workbuddy/logout_backup/<ts>/`，无上限。上游对日志有 log_guard 治理，此处未对齐。

### 8.4 缺陷修复记录（A、B）

提交者审阅本报告后要求修复 A、B 两处缺陷。修复内容与验证如下。

| 缺陷 | 修复方式 | 位置 |
|---|---|---|
| A（P1） | 确认条件收敛为 `("--yes", "-y")`，移除 `-f` / `--force`；并加注释说明为何不复用 `--force` | `bin/workbuddy:885-887` |
| B（P2） | uid 增加字符白名单 `re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(uid))`，不符则跳过该缓存目标 | `bin/workbuddy:869-875` |

**测试补强**（`tests/test_logout.py`，用例数 9 → 11）：

| 用例 | 断言 |
|---|---|
| `test_10_force_is_not_accepted_as_confirm` | 传 `--force` 或 `-f` 均不得删除凭据、不得写入标记 |
| `test_11_uid_traversal_ignored_in_deep` | `uid` 为 `../` 时，`--deep` 不得删除 `~/.workbuddy` 之外的同名文件（用哨兵文件断言） |

**先红后绿验证**（用于排除"恒真测试"）：将 `bin/workbuddy` 临时回退到修复前版本，重跑这两个用例：

```
FAIL: test_10_force_is_not_accepted_as_confirm (tests.test_logout.TestLogout...)
FAIL: test_11_uid_traversal_ignored_in_deep (tests.test_logout.TestLogout...)
Ran 2 tests in 0.102s
FAILED (failures=2)
```

恢复修复后：

```
Ran 11 tests in 0.274s
OK
```

这一步是本次修复中唯一能证明"测试真的有效"的证据。若只展示 `Ran 11 tests OK`，无法排除两条新用例是恒真断言。

**仍未修复**：缺陷 C（Linux 进程探测未验证）、缺陷 D（备份目录无清理），保留在 §10 未解决问题中。

---

## 9. 测试和验收矩阵

### 9.1 已执行并通过（当时执行，本次可复现）

| # | 场景 | 命令 | 结果 | 范围 | 证据 |
|---|---|---|---|---|---|
| T1 | 新增测试（初审时） | `python -m unittest tests.test_logout` | `Ran 9 tests … OK` | 标记路径/预览零写/写标删凭/备份/进程拦截/覆盖/幂等/deep 边界 | 会话输出 |
| T1b | 新增测试（缺陷修复后） | 同上 | `Ran 11 tests … OK` | 增加 `-f`/`--force` 拒绝、uid 越界拒绝 | 会话输出 |
| T1c | 先红后绿校验 | 将 `bin/workbuddy` 回退到修复前，重跑新增 2 项 | `FAILED (failures=2)` | 证明两个用例非恒真断言 | 会话输出 |
| T2 | 上游全量回归 | `python -m unittest discover -s tests -t .` | `Ran 219 tests`，1 error，skipped=14 | 全仓 | 会话输出 |
| T3 | 失败项单独重跑 | 同 T2 指定单测 | `Ran 1 test … OK` | log_guard | 会话输出 |
| T4 | 真实环境冒烟 | `python bin/workbuddy logout`（预览） | 正确识别命令、定位真实凭据、进程占用告警、零修改 | 端到端路径 | 会话输出 |
| T5 | 技能仓库测试 | `python -m unittest discover -s tests` | `Ran 11 tests … OK` | 独立工具版 | 会话输出 |

### 9.2 未运行 / 未覆盖（**不得标记 PASS**）

| 场景 | 状态 | 说明 |
|---|---|---|
| 删除真实活跃账号（执行态） | **未验证** | 有意不执行，避免破坏本机登录态 |
| 客户端已在运行时强制 `--allow-running` 的真实效果 | **未验证** | 仅代码路径存在，无端到端证据 |
| Linux / macOS 行为 | **未验证** | 仅 Windows 环境 |
| uid 路径穿越（缺陷 B） | **已补测** | `test_11_uid_traversal_ignored_in_deep`，先红后绿见 8.4 |
| `-f` / `--force` 别名（缺陷 A） | **已补测** | `test_10_force_is_not_accepted_as_confirm`，先红后绿见 8.4 |
| 备份失败路径（磁盘满 / 权限） | **未覆盖** | 无对应测试 |
| 并发调用登出 | **未覆盖** | 上游 #25 做了 5 线程并发测试，此处没有 |
| 与 `wb-switch` 联合的凭据同步 | **未覆盖** | 登出后切号的行为未验证 |
| 文档/帮助文本一致性 | **未验证** | 未改 README 与 docs，帮助文本仅主文件内一行 |

### 9.3 测试设计质量评估

- **优点**：使用 `tempfile` + 模块级常量替换，隔离真实凭据（已核验：跑完后真实凭据仍为 7158 B、无标记残留）。
- **不足**：
  1. 全部 9 项均 mock 掉 `is_workbuddy_running`，该函数本身零覆盖。
  2. 无对抗性用例（对比 #25 的 12 项对抗 + 20 场景 × 3 轮）。
  3. 无"原版 vs 改后版"逐命令回归对比（#25 做了 8 条命令的逐字节比对）。
  4. 未测试新命令对既有快捷切换分支的影响（例如某账号若命名为 `logout`）。

---

## 10. 学生与 Agent 的贡献边界

### 10.1 有证据支持的学生主导判断

| 判断 | 证据 | 影响 |
|---|---|---|
| 设定"不运行 / 不影响现有技能 / 不装软件"三条边界 | 指令 1 原文 | 决定了实现方式与依赖策略 |
| 设定"影响即停并改正"质量闸门 | 指令 3 原文 | 触发 6 处安全缺陷修复 |
| 要求先解决根因（主文件读取） | 指令 7 原文 | 推翻降级方案，实现质量跃升 |
| 把"权限问题"重定义为可诊断的技术问题 | 指令 5 原文 | 使诊断得以收敛到宿主 Git/GCM |
| 选择"新建私有仓库"、授权"用 token 全自动" | 选项交互记录 | 决定了后续路径 |

### 10.2 Agent 自主执行的工作

- 全部逆向分析（`app.asar` 解析、`getLogoutMarkerPath` 定位、WB-44172 发现）
- 全部代码实现（321 行）
- 全部测试编写与执行
- 全部影响面审计与缺陷修复（在学生设定的原则下）
- 上游架构调研（Git 克隆、结构 grep、风格对齐）
- 环境诊断（系统 Git / GCM 可用性）
- 全部 Git 操作（init / branch / commit / format-patch）

### 10.3 双方协作完成

| 事项 | 学生部分 | Agent 部分 |
|---|---|---|
| 交付形态演进 | 提出"做成 PR"、"先解决读取" | 方案设计与落地 |
| 安全边界 | 提出原则 | 识别具体缺陷并修复 |
| 提交受阻处理 | 指定"先解决读取"的优先级 | 诊断与执行 |

### 10.4 无法确认归属

- 13:47–13:52 期间的具体指令与决策（上下文缺失）
- 学生对"独立模块 vs 集成”这一权衡是否知情并认可（无对应消息）
- 学生对残留缺陷 A/B 是否知情（审计前无相关讨论）

### 10.5 依赖程度评估（如实）

8 条指令中，**6 条为单句目标型指令**（"做成pr"、"自动帮我提交"、"帮我解决权限"等），未附技术方案或验收标准。学生未在任何一轮阅读或审查 Agent 生成的代码（无相关指令或提问记录）。

**这不足以判定学生不理解实现，但足以说明：本 PR 的代码正确性主要依赖 Agent，学生未建立独立验证。**

---

## 11. 证据索引

| 结论 | 证据类型 | 位置 |
|---|---|---|
| 登出标记路径规则 | 代码 | `bin/workbuddy:835` `get_logout_marker_path` |
| 顺序：先标记后删除 | 代码 | `bin/workbuddy:895-907`（`atomic_write_text` 调用先于 `os.remove`） |
| 原子写实现 | 代码 | `bin/workbuddy:814-833` |
| 进程探测 | 代码 | `bin/workbuddy:839-854` |
| deep 清理范围 | 代码 | `bin/workbuddy:856-873` |
| **缺陷 A（`-f` 别名，已修复）** | 代码 | `bin/workbuddy:885-887`（修复前为 `:882`） |
| **缺陷 B（uid 未校验，已修复）** | 代码 | `bin/workbuddy:869-875`（修复前为 `:870`） |
| 命令注册 | 代码 | `install.py:54`、`install.py:68`、`install.py:573` |
| 路由分支 | 代码 | `bin/workbuddy:4378-4383`（prog_name）、`:4497-4504`（cmd） |
| 上游凭据路径交叉验证 | 代码 | `bin/workbuddy:63-64`（origin/main） |
| 测试用例 | 代码 | `tests/test_logout.py`（163 行，9 用例） |
| 分支与提交 | Git | `feat/logout-command`，`e8e83e8`，base `4e832c0` |
| 无 worktree | Git | `git worktree list` 单条输出；`reflog` 无相关动作 |
| 改动范围 | Git | `diff --stat`：321 insertions, 0 deletions, 3 files |
| 测试结果 | 命令输出 | 见 9.1 T1–T5 |
| 上游同类 PR | GitHub API | #23/#24/#25/#26 元数据与 #25 完整正文 |
| 真实凭据未被破坏 | 命令输出 | 审计后核验：7158 B、无 `.logged-out` |

---

## 12. 供老师复核的问题

以下问题针对本次真实实现，用于检验学生是否理解自己提交的代码：

1. **顺序问题**：如果把 `run_logout` 中"写标记"和"删凭据"两步顺序对调，会出现什么现象？请结合 WB-44172 说明原因。

2. **缺陷 A 的修复依据**：`bin/workbuddy:887` 最初把 `-f` / `--force` 当作 `--yes` 的别名，现已移除。请说明：为什么 `--force` 在本仓库其他命令里的语义与"跳过确认"相反？若一个用户从 #25 的 `wb-remove --force` 迁移过来，他会预期什么、实际会发生什么？

3. **测试盲区**：`tests/test_logout.py` 中 9 个用例全部 mock 了 `is_workbuddy_running`。请说明这个函数为什么"客户端在运行"时必须返回 True，以及当前 Linux 分支的实现为什么可能不安全。

4. **范围判断**：`--deep` 清理 `account-snapshot.json` 和 `sidebar-list-snapshot.json`，但刻意不动 `startup-route.json`。请说明判断依据，以及如果误删后者会有什么实际影响。

5. **与同批 PR 的关系**：上游 #23/#24/#25 都在做"删除账号"，你的 `wb-logout` 与它们的边界是什么？如果维护者认为重复，你如何论证不重复？

---

## 13. 审计限制与未验证事项

### 13.1 原始记录缺口

| 缺口 | 影响 |
|---|---|
| 13:47–13:52 对话上下文不可访问 | 该时段的学生指令与 Agent 决策无法核验，仅有 Agent 自写日志 |
| 无独立第三方代码审查记录 | 全部 PASS 结论出自实现者自身 |
| 无 PR 评审意见 | PR #27 为本报告提交后新开，尚无维护者反馈与 CI 结论 |

### 13.2 未验证事项

- 全部 macOS / Linux 行为
- 执行态登出（有意未跑，避免破坏本机登录态）
- `--allow-running` 的真实后果
- 与 `wb-switch` / `wb-login` 的联动
- 安装器端到端（`install.py` 生成 `wb-logout` 启动器后能否正常工作）—— **仅验证了 `python bin/workbuddy logout`，未验证 `wb-logout` 别名启动器**
- CI 结果（无 push，GitHub Actions 未运行）

### 13.3 关于"是否完成验收"

本报告不给出通过/不通过结论。可供老师判断的事实是：

- 功能实现与根因分析**有完整源码级证据**。
- 工程质量与同批 #25 相比，在测试深度、文档完整性、对抗性验证三个维度上**明显偏弱**。
- 审计发现的 2 处缺陷（P1 的 `-f` 别名、P2 的 uid 未校验）已在审阅后修复并补测；仍有 2 项未处理（Linux 进程探测未验证、备份目录无清理）。
- Git 使用了独立分支、完成 push 与 PR #27，但**未分阶段提交**（全程仅 2 个 commit，功能与文档各一）。
- Worktree 与多 Agent **确认未使用**。
- 学生主导的判断集中在"约束设定"与"优先级纠偏"，**未参与技术方案设计与代码审查**。

---

*报告依据可访问记录生成，未编造任何指令、行为或测试结果。缺失部分已逐项标注。*
