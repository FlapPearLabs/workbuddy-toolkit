# WorkBuddy Toolkit: Multi-Account Manager & Automated Check-in

[![CI: Cross-Platform Matrix](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/workflows/ci.yml)
[![Release: v0.3.1](https://img.shields.io/badge/Release-v0.3.1-blue.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Tests: 26/26 Passed](https://img.shields.io/badge/Tests-26%2F26%20Passed%20(100%25)-brightgreen.svg)](tests/)
[![Security: Zero-Leak](https://img.shields.io/badge/Security-Zero--Leak%20Audit%20Passed-success.svg)](.github/workflows/ci.yml)
[![Platform: macOS | Linux | Windows](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-brightgreen.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)

> **WorkBuddy (腾讯开源/商业化 AI 编程助手) 多账号无缝轮换、全域工作区打通、自动化静默签到与每日连续对话保活工具箱。**  
> 深入逆向底层 SQLite 存储隔离机制、腾讯云鉴权、5.6+ 本地凭证加密协议与 `/v2/chat/completions` SSE 流式协议，原生全面适配 **macOS**、**Linux** 与 **Windows** 三大操作系统，打造零侵入、高内聚、零打扰的本地自动化工作流。

---

## 🤖 复制发给你的 AI Agent：一键全自动安装与自适应调度

> **只需将下方提示词直接复制并发送给你的终端 AI Coding Agent（如 Antigravity、WorkBuddy、Claude Code、Hermes、OpenCode、Codex 或 Cursor），Agent 将自动识别当前操作系统（macOS / Linux / Windows）、全自动拉取仓库、安装配置、智能探测自身的 `schedule` 调度能力并向你输出交付报告：**

```text
请帮我安装并配置 WorkBuddy 多账号管理与自动化签到工具包 (workbuddy-toolkit)：
1. 识别当前操作系统平台（macOS、Linux 或 Windows），克隆开源仓库：
   git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git ~/.workbuddy/toolkit
2. 进入目录并执行适配当前系统的一键安装程序：
   - 跨平台通用推荐方式（任何操作系统均可用）：
     cd ~/.workbuddy/toolkit && python3 install.py   (Windows 下执行: python install.py)
   - 或使用系统原生安装脚本：
     macOS / Linux : cd ~/.workbuddy/toolkit && ./install.sh
     Windows (PowerShell) : cd ~\.workbuddy\toolkit ; .\install.ps1
3. 执行 `workbuddy init` 确保全域工作区打通触发器已激活；
4. 执行 `workbuddy doctor` 诊断本地凭证格式与解密运行时兼容性；
5. 执行 `workbuddy status` 检查当前账号状态与已存凭证库；
6. 智能探测你自身（当前 AI Agent）是否拥有内置的 `schedule` / cron 调度功能：
   - 【若拥有 schedule 功能】（如 Antigravity、WorkBuddy 等内置调度器）：
     默认使用你的 schedule 工具注册一个每日定时任务（Cron: 0 9 * * *, 触发时运行 workbuddy checkin 自动执行签到与每日对话保活，并向我汇总汇报收益）。
     同时询问我：“已为您默认配置每天早晨 09:00 自动打卡（含每日签到积分与连续对话保活）并汇报，请问您是否需要调整打卡时间或汇报偏好？”
   - 【若没有 schedule 功能】（如部分普通 CLI Agent）：
     如实告诉我当前环境没有内置 Agent 调度能力，并请我选择签到方式：
     ① 采用安装脚本已配置的系统原生守护定时打卡（macOS launchd / Linux systemd timer / Windows 任务计划程序，每天 09:00 静默打卡写入日志）；
     ② 完全关闭后台自动打卡，后续每次由我手动在终端输入 `wb-checkin` 随时打卡。
7. 向我汇报最终安装与配置结果，并指导我如何使用 `wb-switch`（免扫码秒切账号）、`wb-checkin`（签到+对话）、`wb-chat`（CLI 直接调用模型）以及 `wb-doctor`（兼容诊断）。
```

---

## ⭐ 核心优势：多账号快速轮换与 WorkBuddy 5.6+ 加密凭据原生兼容

| 对比维度 | 传统 WorkBuddy 官方体验 | 使用 WorkBuddy Toolkit |
| :--- | :--- | :--- |
| **多账号切换** | 每次换号必须在微信上**重新掏出手机扫码**，频繁中断思考 | **免除微信反复扫码**：保存已登录凭据 Profile 后随时**秒级直切**，即切即用！ |
| **加密凭据兼容** | 5.6+ 采用 `$wbEncrypted` 加密敏感字段，普通脚本直接失效 | **原生解密兼容 (v0.3.1+)**：运行时透明兼容明文与加密凭据，严格内存级解密，不降级、不落盘 |
| **工作区与会话** | 换号后历史对话列表变空，工作区关联折叠，需重新拉取项目 | **全域穿透打通**：无论怎么切号，所有账号看到同一个物理工作区与全量对话历史 |
| **Token 生命周期** | 切换账号后旧 Token 容易被覆盖导致失效过期 | **自动双向回存 (Sync-before-switch)**：切号前自动回写最新 Token，保持凭证新鲜 |
| **每日签到积分** | 需每天打开图形界面、手动点开活动、逐个切号点击 | **极速静默打卡 (`wb-checkin`)**：0.5 秒遍历所有账号统一领积分，三端原生系统调度自动运行 |
| **每日连续对话** | 需打开图形界面手动输入聊天以维持连击奖励 | **全账号自动联动保活**：打卡后自动优先使用免费/超低倍率模型（Hy3/Flash）完成每日对话，维持连击兑换资格 |
| **终端 CLI 问答** | 官方需打开臃肿 Electron 窗口或配置复杂环境 | **原生秒级直接对话 (`wb-chat`)**：直接在终端向 WorkBuddy 模型提问并流式输出，零 UI 内存占用 |

---

## 目录
- [一、支持平台与系统要求](#一支持平台与系统要求)
- [二、架构与底层逆向原理解析](#二架构与底层逆向原理解析)
  - [1. 工作区与会话“假丢失”根因剖析](#1-工作区与会话假丢失根因剖析)
  - [2. SQLite 触发器穿透与全域共享机制](#2-sqlite-触发器穿透与全域共享机制)
  - [3. 账号快速轮换与双向 Token 同步](#3-账号快速轮换与双向-token-同步)
  - [4. 🔥 核心攻坚：WorkBuddy 5.6+ 本地加密凭据逆向与安全兼容层](#4--核心攻坚workbuddy-56-本地加密凭据逆向与安全兼容层)
    - [(1) 逆向背景：$wbEncrypted 加密信封结构剖析](#1-逆向背景wbencrypted-加密信封结构剖析)
    - [(2) 攻坚过程：发现客户端内置原生 Node 绑定扩展](#2-攻坚过程发现客户端内置原生-node-绑定扩展)
    - [(3) 架构设计原则：DO NOT DECRYPT FOR STORAGE（透传不落地）](#3-架构设计原则do-not-decrypt-for-storage透传不落地)
    - [(4) 稳健性保障：昵称字典防御降级链与 Fail-Closed 阻断机制](#4-稳健性保障昵称字典防御降级链与-fail-closed-阻断机制)
    - [(5) 物理取证与测试验证：本地实测 + 跨平台 CI 矩阵 + 平台真实可用度](#5-物理取证与测试验证本地实测--跨平台-ci-矩阵--平台真实可用度)
    - [(6) 智能诊断体系：wb-doctor 全方位自检](#6-智能诊断体系wb-doctor-全方位自检)
  - [5. 每日签到协议逆向与幂等领取架构](#5-每日签到协议逆向与幂等领取架构)
  - [6. 每日连续对话协议逆向与模型倍率智能梯队](#6-每日连续对话协议逆向与模型倍率智能梯队)
  - [7. 三端原生后台定时调度与自适应探测](#7-三端原生后台定时调度与自适应探测)
- [三、快速上手与安装升级](#三快速上手与安装升级)
  - [老用户平滑升级指南（30 秒升级到 v0.3.1）](#-老用户平滑升级指南30-秒升级到-v031)
  - [推荐方式：跨平台通用 Python 一键安装](#推荐方式跨平台通用-python-一键安装-macos--linux--windows-通用)
  - [备选方式：系统原生脚本安装](#备选方式系统原生脚本安装)
- [四、命令行工具使用手册](#四命令行工具使用手册)
- [五、安全与隐私承诺 (Zero-Leakage)](#五安全与隐私承诺-zero-leakage)
- [六、回滚与卸载指南](#六回滚与卸载指南)
- [七、开源协议](#七开源协议)

---

## 一、支持平台与系统要求

| 操作系统 | 支持级别 | 守护进程调度器 | 凭证存储路径 |
| :--- | :--- | :--- | :--- |
| **macOS** | 原生完整支持 (Apple Silicon / Intel) | `launchd` (`~/Library/LaunchAgents`) | `~/Library/Application Support/CodeBuddyExtension/...` |
| **Linux** | 原生完整支持 (主流桌面与服务器发行版) | `systemd --user` (降级至 `crontab`) | `~/.config/CodeBuddyExtension/...` (遵循 XDG 规范) |
| **Windows** | 原生完整支持 (Windows 10 / 11) | Windows 任务计划程序 (`schtasks` / `pythonw`) | `%APPDATA%\CodeBuddyExtension\...` |

- **依赖要求**：
  - Python 3.8+（系统自带、Python 官网或包管理器安装均可，**零第三方 pip 依赖**，纯 Python 标准库编写）
  - 已安装并登录过至少一个账号的 WorkBuddy 客户端（macOS `WorkBuddy.app` / Windows `WorkBuddy.exe` / Linux `workbuddy`）

---

## 二、架构与底层逆向原理解析

### 1. 工作区与会话“假丢失”根因剖析

WorkBuddy 客户端基于 Electron 架构开发，其本地状态核心保存在 SQLite 数据库中：  
`~/.workbuddy/workbuddy.db`

在逆向客户端主进程及后端 RPC (`server.js`) 源码时发现，其查询会话历史的 SQL 过滤条件如下：

```sql
SELECT * FROM sessions 
WHERE (user_id = :currentUserId OR user_id IS NULL OR user_id = '') 
  AND deleted_at IS NULL;
```

而工作区列表（Workspaces）是根据如下联合逻辑动态生成的：
```sql
SELECT * FROM workspaces 
WHERE EXISTS (
    SELECT 1 FROM sessions 
    WHERE sessions.cwd = workspaces.path 
      AND (sessions.user_id = :currentUserId OR sessions.user_id IS NULL OR sessions.user_id = '')
);
```

**结论**：
当用户从账号 A 切换到账号 B 时，由于历史会话记录中的 `sessions.user_id` 硬编码为了账号 A 的 UID，导致账号 B 的查询被 `user_id = :currentUserId` 拦截，结果为空集；进而由于无法关联到活跃会话，左侧工作区树随之折叠隐藏。**实际上物理文件和数据库记录从未丢失，纯粹是被应用层基于 UID 的过滤条件遮蔽。**

---

### 2. SQLite 触发器穿透与全域共享机制

既然官方过滤逻辑明确包含 `OR user_id = ''`，我们便无需劫持二进制文件或修改前端 JS 代码，只需在本地数据库建立两枚**原子级 SQLite 触发器**：

```sql
-- 触发器 1: 新建会话时，自动将 user_id 规范为空字符串
CREATE TRIGGER IF NOT EXISTS trg_sessions_force_shared_insert
AFTER INSERT ON sessions
BEGIN
    UPDATE sessions SET user_id = '' WHERE id = NEW.id;
END;

-- 触发器 2: 会话被更新或重赋值 UID 时，自动强制重置为空
CREATE TRIGGER IF NOT EXISTS trg_sessions_force_shared_update
AFTER UPDATE OF user_id ON sessions
WHEN NEW.user_id != '' AND NEW.user_id IS NOT NULL
BEGIN
    UPDATE sessions SET user_id = '' WHERE id = NEW.id;
END;
```

**技术优势**：
- **零 CPU/内存占用**：触发器由 SQLite 引擎在事务内毫秒级触发，无需任何常驻进程轮询。
- **高韧性**：只要 SQLite 数据库未被完全重建，触发器将持续生效。
- **平滑回滚**：仅需 `DROP TRIGGER` 即可恢复官方的数据隔离策略。

---

### 3. 账号快速轮换与双向 Token 同步

#### (1) 凭证存储机制
WorkBuddy 的当前登录凭证以 JSON 格式存储在如下路径：  
`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`

包含字段：
- `account.uid`: 用户全局唯一标识
- `account.nickname`: 用户昵称
- `auth.accessToken`: 访问令牌（通常有效期 30 天，5.6+ 可能为 `$wbEncrypted` 加密信封）
- `auth.refreshToken`: 刷新令牌（通常有效期 60 天）
- `auth.expiresAt`: 毫秒级过期时间戳

客户端通过 `FileAuthenticationStorage` 的 `fs.watch` 实时监听该文件。

#### (2) 双向 Token 回存机制 (Sync-before-Switch)
客户端运行期间会自动在后台刷新临期 Token。如果简单粗暴地用旧文件覆盖，可能会丢失刷新后的最新凭证。因此切换器设计了严格的 **双向回存协议**：
1. **写前同步**：读取当前在线的 `workbuddy-desktop.info`，将其最新 Token 同步回存到对应的 `~/.workbuddy/auth_profiles/<name>.info`。
2. **原子切换**：通过临时文件 `workbuddy-desktop.info.tmp` + `os.replace` 原子写入目标账号凭证，并清理登出标记文件。
3. **属主同步**：更新 `automations` 表中的常驻自动化任务属主，防止任务在切换账号后失效。
4. **优雅重启**：通过 AppleScript 发送标准退出指令，确认关闭后再重新唤起客户端加载新身份。

---

### 4. 🔥 核心攻坚：WorkBuddy 5.6+ 本地加密凭据逆向与安全兼容层

在 WorkBuddy 5.6.x 大版本更新中，官方对其桌面客户端本地持久化的认证凭据实施了重大架构重构，这也成为了本项目有史以来最重要的一次底层技术攻坚。

#### (1) 逆向背景：$wbEncrypted 加密信封结构剖析
在 5.5.x 及更早版本中，用户登录态保存在 `workbuddy-desktop.info` 中，关键字段（如 `accessToken`、`refreshToken` 和 `nickname`）均为标准的明文字符串。
然而自 **5.6.0** 起，官方客户端引入了基于 AES-GCM 的敏感字段信封加密规范。打开该 JSON 文件，所有核心认证字段全部被替换为了结构化的字典对象：

```json
{
  "auth": {
    "accessToken": {
      "$wbEncrypted": {
        "suite": 1,
        "keyId": "0123456789abcdef",
        "nonce": "mY6VvXf84s/n59iA",
        "authTag": "fP9/w2c9p0K3x...",
        "ciphertext": "8xA4L+90Vb..."
      }
    },
    "refreshToken": {
      "$wbEncrypted": { "suite": 1, ... }
    }
  },
  "account": {
    "nickname": {
      "$wbEncrypted": { "suite": 1, ... }
    },
    "uin": "10001",
    "uid": "wb_user_9876543210"
  }
}
```

**为什么这会导致所有第三方脚本与旧版工具全线崩溃？**
1. **展示与排序层异常中断**：旧版代码中大量假设 `nickname` 为字符串，频繁执行 `nickname.lower()` 或字符串拼接。遇到新版结构化字典时，直接抛出致命崩溃：`AttributeError: 'dict' object has no attribute 'lower'`。
2. **鉴权头被非法字典污染**：原有 API 调用逻辑直接将 `auth.accessToken` 拼装到 HTTP 请求头 `Authorization: Bearer <token>`。由于 `token` 变成了字典，发出的请求头变成了畸形的 `Bearer {'$wbEncrypted': ...}`，直接被腾讯云网关拒绝并导致 401 鉴权失败。

#### (2) 攻坚过程：发现客户端内置原生 Node 绑定扩展
面对官方客户端的突然升级，如果采用传统的脆弱解法（如逆向分析二进制寻找硬编码密钥、或者通过动态 Hook 注入进程内存），不仅开发与维护成本极高，而且一旦官方客户端发生次级小版本更新就会立即失效，对用户极不负责。

我们深入审计了 WorkBuddy 客户端的物理安装包（macOS `/Applications/WorkBuddy.app` 与 Windows 安装目录）及底层的 Electron 37.x 运行时，经过细致的符号表与主进程 RPC 逆向，发现了核心破局点：
WorkBuddy 官方在其桌面端底层预编译并内嵌了一个 C++ 原生扩展绑定：
```javascript
// WorkBuddy 客户端底层原生存储与加解密绑定
const binding = process._linkedBinding('electron_browser_workbuddy_storage');
const storageLogger = binding.loggerGet();
```
该模块与桌面端的安全密钥环（Keyring）深度结合，并向外暴露了原生加解密接口。

更为关键的是，由于 WorkBuddy 是标准的 Electron 应用，它天生支持官方的 `ELECTRON_RUN_AS_NODE=1` 环境变量！
这意味着：**我们无需修改任何官方二进制文件、无需安装第三方编译工具，直接借助用户本机已有的官方 WorkBuddy 可执行文件本身，就能以完全受控的 Node.js 管道模式唤起该底层扩展，以纯原生、无侵入、极高速度（~48ms）完成瞬态求值！**

#### (3) 架构设计原则：DO NOT DECRYPT FOR STORAGE（透传不落地）
在实现兼容层时，我们制定了严苛的**安全边界铁律**：

1. **磁盘凭据 100% 保持官方原生加密形态（Opaque Blob Passthrough）**：
   - 当用户执行 `workbuddy save` 归档账号 Profile、执行 `workbuddy switch` 切换身份、或在切号前自动回写 Token 时，Toolkit 严格将 `$wbEncrypted` 信封视为**不透明对象**进行原子读写。
   - **坚决不把解密后的明文凭证持久化到磁盘**！磁盘上的所有 Profile 文件与官方桌面客户端文件格式保持完全镜像同构，既规避了明文泄露风险，又保障了官方客户端无论如何升级都能平滑识别。
2. **纯内存管道瞬态解密与安全生命周期保证**：
   - 仅在需要向腾讯官方发起签到或终端对话网络请求的前一瞬间，通过管道调用本地 WorkBuddy 运行时获取临时 Token。
   - **实际实现与安全边界保证**：
     - plaintext credential 不主动持久化
     - 不写 auth profile
     - 不写临时文件
     - 不写日志
     - 不主动打印
     - 仅在当前进程/子进程内瞬态使用
   - **物理内存擦除边界说明**：Node.js 解密助手中的底层 JS Buffer（如密钥与解密原始 bytes）在完成使用后会调用 `.fill(0)` 尽力擦除底层缓冲区；但须明确：上层 JavaScript 字符串、JSON 序列化传输管道以及 Python 运行时中的 `bytes`/`str` 对象，受高级语言不可变对象特性与垃圾回收机制约束，技术上无法保证立即物理 zeroization。工具通过绝不落盘、绝不打印、绝不写日志与严格 Fail-Closed 原则确保凭据安全闭环。

#### (4) 稳健性保障：昵称字典防御降级链与 Fail-Closed 阻断机制
1. **5 级安全防守回退链（Safe Nickname Fallback）**：
   针对 `account.nickname` 也被加密的情况，我们重构了全量展示层与 Profile 匹配逻辑，实现了严格的类型防守链：
   ```
   [account.nickname] 
       │
       ├─► 1. 已经是干净的纯文本 str ──► 直接使用
       ├─► 2. 属于加密信封 $wbEncrypted ──► 尝试内存瞬态解密
       ├─► 3. 解密不可用/失败 ──► 安全降级取纯数字 account.uin
       ├─► 4. uin 不存在 ──► 安全降级取 account.uid 前 8 位 (如 "wb_user_")
       └─► 5. 兜底回退 ──► 使用 Profile 文件别名或 "未知用户"
   ```
   这确保了传给后续业务逻辑的昵称绝对是安全、合法的 `str`，彻底杜绝了任何 `.lower()` 崩溃问题。
2. **绝对 Fail-Closed 阻断策略**：
   在网络请求发起前，由 `is_valid_token_string()` 强行校验 Token。若遇到加密信封但本机未找到 WorkBuddy 运行时、或凭据已损坏，Toolkit **坚决不向腾讯云服务器发送任何网络请求**，立即就地阻断并输出明确的修复指引，杜绝因发送畸形请求破坏账号信誉或触发服务端风控。

#### (5) 物理取证与测试验证：本地实测 + 跨平台 CI 矩阵 + 平台真实可用度
我们坚信「拿物理证据说话」，对本版本进行了立体式的严密测试验证：

1. **真实物理机实测取证（Local Smoke Test）**：
   - **测试环境**：macOS 15.x (Apple Silicon) 真实物理开发机。
   - **目标客户端**：官方正式版 WorkBuddy 5.6+（内置 Electron 37.10.3）。
   - **物理证据**：通过管道调用本地原生绑定，执行耗时仅 **48ms**，内存占用近乎为零，成功完成加密字段解析并完成静默打卡与连续对话。
2. **全覆盖自动化测试套件（26/26 100% Passed）**：
   在 [`tests/test_toolkit.py`](tests/test_toolkit.py) 中新增了专属的 **T1 至 T17** 测试用例：
   - `T1`: 遗留旧版明文凭据直接解析，不触发子进程，性能零损耗；
   - `T2`: 准确识别 `$wbEncrypted` 加密信封特征；
   - `T3`: 损坏或不完整的加密信封触发 Fail-Closed 拒绝；
   - `T4`: 缺少客户端运行时环境下 Fail-Closed 友好报错，零网络请求；
   - `T5`: 字典格式 Token 绝不进入 HTTP 请求头；
   - `T6`: 昵称加密字典安全降级，杜绝 `.lower()` 崩溃；
   - `T7`-`T9`: Profile 保存、切换、Token 同步全流程 100% 保持加密信封不透明透传；
   - `T10`: 旧版明文 Profile 零回归；
   - `T11`-`T13`: Doctor 诊断在明文、加密可用、加密缺失三种场景下的矩阵断言；
   - `T14`: 日志与标准输出绝不泄露明文 Token 与私钥；
   - `T15`: API 网络层确保仅合法 ASCII 字符串才可发出请求；
   - `T16`: 加密昵称支持中文、空格与 Unicode 解析，严格拒绝 NUL 及不可见控制字符并安全回退；
   - `T17`: accessToken 验证器严格性断言，确保放宽 nickname 不得降低 token 安全防线。
   - **本地执行结果**：`Ran 26 tests in 0.274s -> OK`。
3. **GitHub Actions 跨平台 CI 矩阵全绿验证**：
   - **构建状态**：[Run ID: 35994709530](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/runs/35994709530)
   - **矩阵覆盖**：涵盖 macOS / Ubuntu / Windows 三大操作系统 × Python 3.9 / 3.11 / 3.12 共 9 个测试环境组合，外加 1 项 Zero-Leak 安全审计，**10 / 10 任务全部 SUCCESS 绿色通过**！
4. **各操作系统平台真实可用度一览**：
   - **macOS**：**REAL VERIFIED (真实物理验证)**。原生适配默认安装路径 `/Applications/WorkBuddy.app/Contents/MacOS/Electron`，开箱即用。
   - **Windows**：**IMPLEMENTED & CI VERIFIED (代码实现并经 CI 验证)**。原生适配默认安装路径 `%LOCALAPPDATA%\Programs\WorkBuddy\WorkBuddy.exe`，支持通过 `WORKBUDDY_EXE` 自定义路径，CI 3 平台版本全绿。
   - **Linux**：**DETECT & FAIL CLOSED (保护阻断)**。因腾讯官方目前暂未推出 Linux 桌面客户端，旧版明文凭证 100% 兼容；若遇到加密凭证，Toolkit 将自动执行 Fail-Closed 安全拦截并提示配置自定义运行时。

#### (6) 智能诊断体系：wb-doctor 全方位自检
全新内建诊断子命令：
```bash
workbuddy doctor   # 或简写 wb-doctor
```
一键扫描并直观呈现整条调用链的健康状态：
```text
=== WorkBuddy Toolkit Doctor ===

Auth file             : OK (~/.workbuddy/auth/workbuddy-desktop.info)
Credential format     : encrypted
Encrypted scheme      : detected (sym-v1 / suite 1)
WorkBuddy runtime     : FOUND (/Applications/WorkBuddy.app/Contents/MacOS/Electron)
Credential resolver   : AVAILABLE (Electron 37.10.3)
Profile count         : 2
API capability        : READY

RESULT: COMPATIBLE
```

---

### 5. 每日签到协议逆向与幂等领取架构

通过对 `app.asar` 内通信层及运行时日志分析，我们还原了 WorkBuddy 签到活动的底层通信协议：

```
[客户端]                                        [腾讯云 Copilot 后端]
   |                                                    |
   |--- 1. POST /v2/billing/meter/checkin-activity-status -->|
   |<-- 2. {"today_checked_in": true/false, ...} -------|  (只读探测)
   |                                                    |
   | [若 today_checked_in == false]                     |
   |--- 3. POST /v2/billing/meter/daily-checkin -------->|  (执行领取)
   |<-- 4. {"code": 0, "credit": 100, ...} ------------|
```

#### (1) 请求参数最小集
```http
POST /v2/billing/meter/checkin-activity-status HTTP/1.1
Host: copilot.tencent.com
Authorization: Bearer <accessToken>
X-User-Id: <account_uid>
Content-Type: application/json
User-Agent: WorkBuddy/5.5.3

{}
```

#### (2) 关键逆向发现
- **无需 TuringShield 签名校验**：客户端内部虽然引入了 `TuringShield.bundle` 设备指纹，但服务端的签到与查询接口完全遵循标准 OAuth 鉴权，**未强制校验 `X-Device-Token`**。直接发送标准 Bearer Token 请求即可合法返回。
- **严格两段式幂等保证**：先通过只读接口获取当前签到状态与连续天数；若已签到则直接跳过，绝不滥发重复请求，彻底规避风控风险。

---

### 6. 每日连续对话协议逆向与模型倍率智能梯队

WorkBuddy 体系设有**每日连续对话打卡奖励**（连续天数可累积连击特权与积分商城兑换资格）。然而官方桌面端必须启动完整的 Electron 渲染窗口并在 UI 中手动键入对话，内存占用大且无法自动化。

项目通过对底层通信层的逆向，攻破了终端免 UI 原生对话的关键通道：

#### (1) 通信协议与 SSE 流式要求
- **接口端点**：`https://copilot.tencent.com/v2/chat/completions`（遵循 OpenAI 兼容规范）。
- **SSE 流式硬性约束**：后端网关拒绝非流式请求（返回 `400 Non-stream chat request is currently not supported`），必须配置 `"stream": true` 并使用 `Accept: text/event-stream` 请求头。
- **纯标准库流式解析器**：通过 Python 原生 `urllib.request` 实现轻量级 SSE 逐行 chunk 解析，零额外外部依赖。

#### (2) 智能倍率与免费模型优先调度策略
为了在达成每日连续对话任务的同时**彻底杜绝积分浪费**，工具箱设计了智能倍率梯队：
1. **第一梯队 (`hy3`)**：混元 3.0 大模型，当前官方处于限时免费 / 极低折扣期，优先作为默认主力；
2. **第二梯队 (`deepseek-v4-flash`)**：超轻量 Flash 模型，极速响应且倍率极低；
3. **第三梯队 (`auto` / `glm-5v-turbo`)**：官方智能路由与低消耗 Turbo 兜底。

遇到特定模型暂时不可用时，系统自动向下无缝容灾回退（Fallback），并在完成打卡后输出简明的回复摘要（如 `[每日对话] 模型: hy3 (低倍率/免费) -> 回复: "你好" ✔`）。

---

### 7. 三端原生后台定时调度与自适应探测

为了让每日签到做到真正的“零打扰、免记挂”，项目原生实现了三大主流操作系统的后台定时守护体系，并支持 AI Agent 运行时的**自适应能力探测 (Capability Probing)**：

```
┌─────────────────────────────────────────────────────────────────┐
│              Agent 自适应能力探测 (Schedule Probing)              │
└──────────────┬───────────────────────────────────┬──────────────┘
               ▼                                   ▼
   [具备 schedule 工具]                    [无内置 schedule 工具]
         │                                       │
         ▼                                       ▼
 自动注册 Agent 内置定时任务              用户自由二选一方案：
 (每日 09:00 自动唤醒对话并汇报战报)        ① 采用系统原生后台守护进程静默打卡
                                         ② 无需定时打卡，随时手动输入 wb-checkin
```

1. **AI Agent 内置调度层（推荐）**：
   对于具备内置 `schedule` 工具的 Agent（如 Antigravity、WorkBuddy 等），可在会话中注册常驻 cron（`0 9 * * *`），每天早晨自动唤醒、拉起签到，并在对话窗口中向用户发送美观的收益战报。
2. **操作系统原生守护层 (Zero-Touch 后台静默)**：
   - **macOS (`launchd`)**：`~/Library/LaunchAgents/com.workbuddy.dailycheckin.plist`，开机自启、盒盖休眠唤醒补跑。
   - **Linux (`systemd --user`)**：`~/.config/systemd/user/workbuddy-dailycheckin.timer`，开机自启且支持 `Persistent=true` 唤醒补跑；无 systemd 环境自动降级至用户 `crontab`。
   - **Windows (任务计划程序 `schtasks`)**：注册 `WorkBuddyDailyCheckin` 计划任务，调用 Windows 内置 `pythonw.exe` 静默后台运行，**绝无黑色 CMD 弹窗干扰**。
3. **手动模式**：
   若用户不希望后台常驻任何定时任务，只需执行 `wb-checkin` 即可在 0.5 秒内完成手工打卡。

---

## 三、快速上手与安装升级

### 🔄 老用户平滑升级指南（30 秒升级到 v0.3.1）

如果您之前已经安装过旧版 workbuddy-toolkit，升级到 v0.3.1 极其简单，**无需重新配置任何 Profile，原有数据与账号 100% 平滑保留**：

```bash
# 1. 进入本地已有仓库目录，拉取最新发布代码
cd ~/.workbuddy/toolkit
git pull

# 2. 重新运行通用安装脚本（自动刷新并部署 wb-doctor 诊断工具及新版软链接）
python3 install.py      # Windows 用户请执行: python install.py

# 3. 运行环境自检，确认当前系统与 WorkBuddy 5.6+ 本地加密兼容性
wb-doctor
```

#### 升级诊断与异常排查：
- **正常情况**：`wb-doctor` 输出 `RESULT: COMPATIBLE`，代表本机环境已完全就绪，您可直接继续使用 `wb-switch`、`wb-checkin` 和 `wb-chat`。
- **若提示 `WorkBuddy runtime: MISSING`**：
  说明您的 WorkBuddy 客户端安装在非默认系统路径下（如安装在自定义应用目录或次级磁盘）。此时只需配置环境变量指向您的客户端可执行程序即可：
  ```bash
  # macOS 示例（若修改了默认安装路径）
  export WORKBUDDY_EXE="/Applications/WorkBuddy.app/Contents/MacOS/Electron"
  
  # Windows 示例（PowerShell 临时生效，或写入系统环境变量）
  $env:WORKBUDDY_EXE = "D:\Software\WorkBuddy\WorkBuddy.exe"
  
  # 永久生效：macOS/Linux 请将 export 语句追加至 ~/.zshrc 或 ~/.bashrc
  ```

---

### 推荐方式：跨平台通用 Python 一键安装 (macOS / Linux / Windows 通用)

无论您使用的是 macOS、Linux 还是 Windows，只要安装了 Python 3.8+，在克隆仓库后直接运行通用安装器即可：

```bash
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git ~/.workbuddy/toolkit
cd ~/.workbuddy/toolkit
python3 install.py      # Windows 下请运行: python install.py
```

安装器将全自动完成：
1. **自动识别操作系统**并部署 CLI 脚本（macOS/Linux 安装到 `~/.local/bin`；Windows 安装到 `~/.workbuddy/bin` 并生成 `.cmd` 垫片且自动写入用户 `PATH` 环境变量）；
2. **初始化数据库**：对本地 `workbuddy.db` 注入全域工作区互通触发器；
3. **激活原生系统定时任务**：macOS (`launchd`) / Linux (`systemd timer` 或 `crontab`) / Windows (`schtasks` 计划任务)；
4. **挂载 IDE 伴随体**：若检测到 Antigravity，自动挂载 Scheduled Tasks Sidecar。

---

### 备选方式：系统原生脚本安装

#### 选项 A：macOS / Linux (Shell)
```bash
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git ~/.workbuddy/toolkit
cd ~/.workbuddy/toolkit
./install.sh
```

#### 选项 B：Windows (PowerShell)
在 PowerShell 中运行（无需管理员权限）：
```powershell
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git $HOME\.workbuddy\toolkit
cd $HOME\.workbuddy\toolkit
.\install.ps1
```

> **提示**：安装完成后若提示找不到 `wb-switch`：
> - **macOS / Linux**：请确保 `~/.local/bin` 在 `PATH` 中（如在 `~/.zshrc` 中添加 `export PATH="$HOME/.local/bin:$PATH"`）；
> - **Windows**：重新打开一个 PowerShell 或 CMD 窗口即可自动加载最新用户 `PATH`。

---

## 四、命令行工具使用手册

安装后，全局提供 `workbuddy`、`wb-switch`、`wb-checkin`、`wb-chat` 以及 `wb-doctor` 快捷命令：

### 1. 账号快速切换 (`wb-switch`)

```bash
# 方式 A：打开交互式数字选择菜单 (CC Switch 风格)
wb-switch

# 方式 B：直接指定账号别名或昵称进行秒切
wb-switch my_account_2
```

交互菜单示例：
```text
==============================================
       WorkBuddy 账号切换器 (CC Switch 风格)    
==============================================
当前在线账号: main_dev (当前使用中)

请选择要切换的目标账号:
 ▶ 1) main_dev     [昵称: 开发主号] (当前使用中)
   2) backup_acc   [昵称: 备用副号]

   q) 退出 (Cancel)
----------------------------------------------
请输入序号 [1-2] 进行切换:
```

### 2. 每日签到与连续对话保活 (`wb-checkin`)

```bash
# 自动扫描所有已存账号 + 当前在线账号，统一检查签到并自动调用免费/低倍率模型触发每日对话
wb-checkin

# 或仅为特定账号执行打卡
wb-checkin backup_acc

# 若本次只想签到、跳过每日对话调用：
wb-checkin --no-chat
```

输出示例：
```text
=== WorkBuddy 自动每日签到与连续对话 (2 个账号) ===
 ✔ backup_acc    [昵称: 备用副号] 今日已签到 | 连续 4 天 | 累计签到奖励 400 积分
    💬 [每日对话] 模型: hy3 (低倍率/免费) -> 回复: "你好" ✔
 🎉 main_dev     [昵称: 开发主号] 签到成功！+100 积分 | 连续签到 6 天
    💬 [每日对话] 模型: hy3 (低倍率/免费) -> 回复: "你好" ✔
----------------------------------------------
```

### 3. 终端极速对话 (`wb-chat`) — 免 UI 零内存占用

无需开启庞大的 Electron 桌面窗口，直接在终端中向 WorkBuddy 模型提问，秒级流式响应：

```bash
# 向当前活跃账号发送对话（智能优先免费/最低倍率模型）
wb-chat "用 Python 写一个快速排序"

# 对所有已保存账号批量发送问候，统一触发每日连续对话奖励
wb-chat --all "请回复：你好"

# 为指定保存的账号别名发送对话
wb-chat backup_acc "请回复：测试通过"
```

输出示例：
```text
=== WorkBuddy CLI 对话 (2 个账号) ===
提示词: 请回复：你好
 ✔ main_dev     [昵称: 开发主号] 模型: hy3 -> 你好！
 ✔ backup_acc   [昵称: 备用副号] 模型: hy3 -> 你好！
----------------------------------------------
```

### 4. 环境与凭证兼容性诊断 (`wb-doctor`)

一键检查本地凭据格式与 WorkBuddy 运行时原生解密能力：

```bash
workbuddy doctor   # 或 wb-doctor
```

输出示例：
```text
=== WorkBuddy Toolkit Doctor ===

Auth file             : OK (~/.workbuddy/auth/workbuddy-desktop.info)
Credential format     : encrypted
Encrypted scheme      : detected (sym-v1 / suite 1)
WorkBuddy runtime     : FOUND (/Applications/WorkBuddy.app/Contents/MacOS/Electron)
Credential resolver   : AVAILABLE (Electron 37.10.3)
Profile count         : 2
API capability        : READY

RESULT: COMPATIBLE
```

### 5. 查看账号状态与凭证有效期

```bash
workbuddy status
```

### 6. 保存新登录的账号

当你在 WorkBuddy 界面退出并用微信扫码登录了新账号后：
```bash
workbuddy save <取一个名字>
# 例如: workbuddy save acc_3
```
*注：即使你忘记执行 `save`，下次运行 `wb-checkin` 时脚本也会自动识别新账号并完成自动建档入库。*

### 7. 常用命令速查表

| 命令 | 别名 | 功能说明 |
| :--- | :--- | :--- |
| `workbuddy switch [别名]` | `wb-switch` | 交互式选择或直接切换到指定账号并优雅重启 |
| `workbuddy checkin [别名]` | `wb-checkin` | 统一执行所有已存账号每日签到 + 自动调用低倍率/免费模型每日对话 |
| `workbuddy chat [提示词]` | `wb-chat` | 终端极速对话（智能优先使用 `hy3`、`deepseek-flash` 等免费低消耗模型） |
| `workbuddy chat --all [词]` | `wb-chat --all` | 全账号批量发起对话，一键刷新全账号连续对话奖励资格 |
| `workbuddy doctor` | `wb-doctor` | 深度诊断凭据加密套件、本地运行时路径与解密通信就绪度 |
| `workbuddy status` | `workbuddy list` | 查看当前活跃账号、Token 有效期及全部本地凭证列表 |
| `workbuddy save <别名>` | - | 将当前活跃登录态固化为一个可切换的 Profile |
| `workbuddy init` | - | 一键应用 SQLite 全域工作区打通补丁 |
| `workbuddy rollback` | - | 撤销 SQLite 触发器，恢复官方严格数据隔离 |
| `workbuddy restart` | - | 优雅重启 WorkBuddy 客户端 |

---

## 五、安全与隐私承诺 (Zero-Leakage)

1. **绝对本地化**：本工具所有逻辑 100% 运行于本地机器，所有的 Token、UID、凭证仅保存在用户本机的 `~/.workbuddy/auth_profiles/`，**绝不向任何第三方服务或未经授权的服务器发送任何数据**。
2. **直连官方端点**：签到功能直接调用腾讯官方 API 端点 (`https://copilot.tencent.com`)，无任何中间代理。
3. **开源透明**：所有脚本均为开源 Python/Shell 源码，接受任何形式的审计与审查。
4. **潜在风险与版本兼容性提示 (Remaining Risks)**：保存的 encrypted Profile 使用写入它的 WorkBuddy 构建所对应的字段密钥；如果未来 WorkBuddy 构建实际轮换密钥，历史离线 Profile 可能出现 `KEY_MISMATCH`，当前工具会 fail closed。不要声称历史 Profile 可永久跨任意客户端升级。

---

## 六、回滚与卸载指南

如果你不再需要此工具，或希望完全还原到官方初始状态：

### 推荐方式：跨平台通用 Python 一键卸载
```bash
python3 uninstall.py    # Windows 下运行: python uninstall.py
```
卸载程序会自动注销各系统定时器（macOS launchd / Linux systemd 或 crontab / Windows 任务计划）、清理 CLI 软链接及垫片，并询问是否回滚 SQLite 触发器。

### 原生脚本卸载方式
- **macOS / Linux**：
  ```bash
  ./uninstall.sh
  ```
- **Windows (PowerShell)**：
  ```powershell
  .\uninstall.ps1
  ```

---

## 七、开源协议

本项目采用 [MIT License](LICENSE) 许可证发布。欢迎提交 Issue 与 Pull Request！
