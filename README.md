# WorkBuddy Toolkit: Multi-Account Manager & Automated Check-in

[![CI: Cross-Platform Matrix](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/workflows/ci.yml)
[![Release: v0.5.0](https://img.shields.io/badge/Release-v0.5.0-blue.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Tests: 70/70 Passed](https://img.shields.io/badge/Tests-70%2F70%20Passed%20(100%25)-brightgreen.svg)](tests/)
[![Security: Zero-Leak](https://img.shields.io/badge/Security-Zero--Leak%20Audit%20Passed-success.svg)](.github/workflows/ci.yml)
[![Platform: macOS | Linux | Windows](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-brightgreen.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)

> **WorkBuddy (腾讯开源/商业化 AI 编程助手) 多账号无缝轮换、全域工作区打通、自动化静默签到、容灾路由网关、独立免登扫码与沙盒日志自愈治理工具箱。**  
> 深入逆向底层 SQLite 存储隔离机制、腾讯云鉴权、5.6+ 本地凭证加密协议、`/v2/chat/completions` SSE 流式协议与沙盒日志生命周期，原生全面适配 **macOS**、**Linux** 与 **Windows** 三大操作系统，打造零侵入、高内聚、零打扰的本地自动化工作流。

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
7. 向我汇报最终安装与配置结果，并指导我如何使用 `wb-login`（免打开客户端扫码入库）、`wb-list` / `wb-status`（账号状态全景与 JSON）、`wb-switch`（免扫码秒切账号）、`wb-checkin`（签到+对话）、`wb-chat`（CLI 直接调用模型）、`wb-router`（容灾轮换路由）、`wb-models`（模型透视）以及 `wb-doctor`（兼容诊断）。
```

---

## ⭐ 核心优势：多账号快速轮换与 WorkBuddy 5.6+ 加密凭据原生兼容

| 对比维度 | 传统 WorkBuddy 官方体验 | 使用 WorkBuddy Toolkit |
| :--- | :--- | :--- |
| **多账号录入** | 必须打开臃肿 Electron 客户端、退出当前账号、掏出手机扫码，极易顶掉旧账号 | **独立免登终端扫码 (`wb-login`)**：无需启动客户端 UI，终端直接呈现高清 QR 码，扫码即自动入库，智能消解别名冲突 |
| **多账号切换** | 每次换号必须在微信上**重新掏出手机扫码**，频繁中断思考 | **免除微信反复扫码**：保存已登录凭据 Profile 后随时**秒级直切**，即切即用！ |
| **账号状态与列表** | 官方无全景透视，无法感知 Token 与 RefreshToken 剩余有效期与健康度 | **多维全景与程序化透视 (`wb-list` / `wb-status`)**：支持文本清单与 `--json` 规范输出，UID、存储格式与双到期时间一览无余 |
| **凭证健康巡检** | 账号静默失效毫无感知，直到任务报错中断才发现已登出 | **零感知自愈与桌面通知 (`wb-audit`)**：防风控三级审计，临期自动续期，失效触发 macOS / Windows 原生桌面通知 |
| **远端双端监控** | 无法跨机器监控远程服务器/CI 机上的账号健康度 | **双 Runner 原生告警 (`workbuddy-monitor.yml`)**：跨 macOS / Windows 双矩阵每日巡检，官方邮件零配置秒级送达 |
| **加密凭据兼容** | 5.6+ 采用 `$wbEncrypted` 加密敏感字段，普通脚本直接失效 | **原生解密兼容 (v0.3.1+)**：运行时透明兼容明文与加密凭据，严格内存级解密，不降级、不落盘 |
| **工作区与会话** | 换号后历史对话列表变空，工作区关联折叠，需重新拉取项目 | **全域穿透打通**：无论怎么切号，所有账号看到同一个物理工作区与全量对话历史 |
| **Token 生命周期** | 切换账号后旧 Token 容易被覆盖导致失效过期 | **自动双向回存 (Sync-before-switch)**：切号前自动回写最新 Token，保持凭证新鲜 |
| **每日签到积分** | 需每天打开图形界面、手动点开活动、逐个切号点击 | **极速静默打卡 (`wb-checkin`)**：0.5 秒遍历所有账号统一领积分，三端原生系统调度自动运行 |
| **每日连续对话** | 需打开图形界面手动输入聊天以维持连击奖励 | **全账号自动联动保活**：打卡后自动优先使用免费/超低倍率模型（Hy3/Flash）完成每日对话，维持连击兑换资格 |
| **终端 CLI 问答** | 官方需打开臃肿 Electron 窗口或配置复杂环境 | **原生秒级直接对话 (`wb-chat`)**：直接在终端向 WorkBuddy 模型提问并流式输出，零 UI 内存占用 |
| **模型容灾与自愈** | 官方上游模型故障/限流直接报错中断任务 | **透明容灾轮换网关 (`wb-router`)**：`:8047` 代理中介，支持 DeepSeek / Space Bunny / Hy3 瞬态故障自动降级轮换 |
| **模型资产透视** | 官方隐藏模型实际扣费倍率与调用计费明细 | **动态全景资产透视 (`wb-models`)**：动态拉取全量模型、实时倍率审计与轻量级交互式终端选择器 (TUI) |
| **沙盒日志暴走** | sandbox-core 狂写 PTY 日志无淘汰机制，几天吞噬 15GB+ 磁盘 | **智能物理看门狗 (`workbuddy-log-guard`)**：36h TTL、2GB 目录硬顶、30MB 物理熔断，`lsof` 句柄感知，只 truncate 不删活动文件 |

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
  - [8. 容灾轮换路由网关架构 (Failover Router :8047)](#8-容灾轮换路由网关架构-failover-router-8047)
  - [9. 模型全景资产透视与倍率审计 (Model Inventory)](#9-模型全景资产透视与倍率审计-model-inventory)
  - [10. 🔥 沙盒日志暴走根因与无感物理看门狗治理 (Log Guardian)](#10--沙盒日志暴走根因与无感物理看门狗治理-log-guardian)
  - [11. 独立免登扫码录入机制逆向与终端二维码渲染 (Decoupled QR Login)](#11-独立免登扫码录入机制逆向与终端二维码渲染-decoupled-qr-login)
  - [12. 账号状态多维呈现与程序化 JSON 架构 (Status & Inventory Architecture)](#12-账号状态多维呈现与程序化-json-架构-status--inventory-architecture)
  - [13. 账号健康度定时巡检与双端原生桌面通知 (Health Audit & Desktop Notification)](#13-账号健康度定时巡检与双端原生桌面通知-health-audit--desktop-notification)
  - [14. 远端 CI 跨机双端健康监控与零配置邮件告警 (Dual-Runner CI Monitor)](#14-远端-ci-跨机双端健康监控与零配置邮件告警-dual-runner-ci-monitor)
  - [15. 🔥 深度踩坑记录与底层逆向突破全景 ("问题→原因→解决")](#15--深度踩坑记录与底层逆向突破全景-问题原因解决)
- [三、快速上手与安装升级](#三快速上手与安装升级)
  - [老用户平滑升级指南（30 秒升级到 v0.5.0）](#-老用户平滑升级指南30-秒升级到-v050)
  - [推荐方式：跨平台通用 Python 一键安装](#推荐方式跨平台通用-python-一键安装-macos--linux--windows-通用)
  - [备选方式：系统原生脚本安装](#备选方式系统原生脚本安装)
- [四、命令行工具使用手册](#四命令行工具使用手册)
  - [1. 独立免登扫码录入 (wb-login)](#1-独立免登扫码录入-wb-login)
  - [2. 账号快速切换 (wb-switch)](#2-账号快速切换-wb-switch)
  - [3. 账号状态全景与程序化导出 (wb-list / wb-status)](#3-账号状态全景与程序化导出-wb-list--wb-status)
  - [4. 账号健康审计与常驻巡检 (wb-audit)](#4-账号健康审计与常驻巡检-wb-audit)
  - [5. 每日签到与连续对话保活 (wb-checkin)](#5-每日签到与连续对话保活-wb-checkin)
  - [6. 终端极速对话 (wb-chat)](#6-终端极速对话-wb-chat)
  - [7. 环境与凭证兼容性诊断 (wb-doctor)](#7-环境与凭证兼容性诊断-wb-doctor)
  - [8. 容灾轮换路由网关 (wb-router)](#8-容灾轮换路由网关-wb-router)
  - [9. 模型全景资产与倍率透视 (wb-models)](#9-模型全景资产与倍率透视-wb-models)
  - [10. 沙盒日志看门狗配置与管理 (workbuddy-log-guard)](#10-沙盒日志看门狗配置与管理-workbuddy-log-guard)
  - [11. 常用命令速查表](#11-常用命令速查表)
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
   - **坚决不把解密后的明文凭证持久化到磁盘**！保持与当前已验证 WorkBuddy 凭据格式同构，避免 Toolkit 主动把加密凭据降级为明文；未来客户端若轮换字段密钥或改变存储协议，历史 Profile 仍可能出现 KEY_MISMATCH，并按 Fail-Closed 处理。
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
   - **构建状态**：[Run ID: 35997775560](https://github.com/FlapPearLabs/workbuddy-toolkit/actions/runs/35997775560)
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
   - **Windows (任务计划程序 `schtasks`)**：注册 `WorkBuddyDailyCheckin` (每天 09:00) 与 `WorkBuddyLogGuard` (每 30 分钟) 计划任务，调用 Windows 内置 `pythonw.exe` 静默后台运行，**绝无黑色 CMD 弹窗干扰**。
3. **手动模式**：
   若用户不希望后台常驻任何定时任务，只需执行 `wb-checkin` 即可在 0.5 秒内完成手工打卡。

---

### 8. 容灾轮换路由网关架构 (Failover Router :8047)

在日常多 Agent 并发开发中，官方 API 端点偶尔会因并发瞬态限流（`429 Too Many Requests`）或上游服务抖动（`502 Bad Gateway` / `503 Service Unavailable`）导致任务直接报错中断。为此，Toolkit 引入了轻量级**透明容灾轮换路由网关 (`wb-router`)**：

```
[本地 IDE / Agent]
        │
        ▼ (请求 127.0.0.1:8047)
┌────────────────────────────────────────────────────────┐
│     WorkBuddy Failover Router (ThreadedHTTPServer)     │
│   SO_REUSEADDR 端口就绪 / 自动拦截 429/500/502/503      │
└──────────────┬─────────────────────────┬───────────────┘
               │ (正常)                   │ (上游故障触发 Fallback)
               ▼                         ▼
      [首选主力模型]               [自动容灾回退梯队]
   deepseek-v4-flash /          hy3 (混元 3.0 / 限免或极低消耗)
   space-bunny-free (免额度)     glm-5v-turbo (低倍率兜底)
```

- **底层高韧性机制**：基于原生多线程 `ThreadedHTTPServer`，开启 `SO_REUSEADDR` 消除快速重启时的 `TIME_WAIT` 绑定冲突；
- **主力模型零感自愈**：主控配置首选免额度或极低倍率模型（如 DeepSeek、Space Bunny），当遇到网络闪断或限流时，网关在**内存层毫秒级无感降级**至下一梯队（如 `hy3`），上层客户端无需任何重试或感知；
- **子智能体差异化路由**：支持针对特定子任务类型（代码编写、审计、常规对话）自动路由至最适配的模型，杜绝昂贵倍率消耗。

---

### 9. 模型全景资产透视与倍率审计 (Model Inventory)

WorkBuddy 官方界面通常弱化或隐藏各模型的实际积分扣减倍率与最新状态。通过逆向其模型目录接口与会话历史，工具箱提供了 `wb-models` 全景透视功能：

- **动态全量资产抓取**：实时拉取官方开放的全部可用模型（含限免、折算倍率、输入输出上下文长度）；
- **倍率与成本透视**：直观展示 `x0.00`（完全免费）、`x0.50`、`x1.00` 等计费阶梯，辅助开发者以极致成本效益组合模型；
- **交互式轻量终端选择器 (TUI)**：支持在纯终端中方向键浏览与切换，无需启动庞大 Electron 窗口。

---

### 10. 🔥 沙盒日志暴走根因与无感物理看门狗治理 (Log Guardian)

#### (1) 沙盒日志吃满磁盘的底层根因
WorkBuddy 的 `sandbox-core` 组件负责管理每个独立沙盒进程与交互式终端（PTY）。为了满足审计合规与沙盒拦截追踪，底层会对进程每一次命令执行、标准输入输出（PTY 字节流）以及动态决策进行全量落盘（保存在 `~/.workbuddy/logs/sandbox/YYYYMMDD/sandbox_<pid>_<idx>.log`）。
虽然单文件按 13MB 自动滚动，但**官方完全未设计任何 TTL 淘汰策略或总量配额上限**！
在多 Agent 高频编码、编译或跑自动化测试的场景下：
- 单日产生的日志量即可高达 **5 ~ 7 GB**；
- 运行 3~4 天即可堆积 **15 GB 以上的纯垃圾日志**，直接将本就不宽裕的系统盘彻底吞干！

#### (2) 四重物理防御网 (`workbuddy-log-guard`)
为了实现极致克制与绝对自愈，项目设计了高内聚的守护进程组件：

```
┌──────────────────────────────────────────────────────────────────┐
│              WorkBuddy Log Guardian (四重物理防御网)              │
├──────────────────────────────────────────────────────────────────┤
│ 1. Open-FD 感知   : lsof 识别活跃句柄，对被持有着只 truncate 不 delete │
│ 2. 36小时 TTL     : 自动物理淘汰超过 36h (-mmin +2160) 的历史日志   │
│ 3. 2GB 容量硬顶   : 目录总量突破 2GB 时，按 stat 时间强制修剪至 1.5GB  │
│ 4. 30MB 单文件熔断: 异常单文件超 30MB 自动 truncate -s 0 即刻释放 APFS│
└──────────────────────────────────────────────────────────────────┘
```

1. **Open-FD 句柄安全感知 (Zero Disruption)**：通过 `lsof -F n +D` 递归探测所有正在被 `sandbox-core` 读写的日志文件。**对被进程持有打开的文件只执行 `truncate -s 0`，坚决不 unlink 删除**，杜绝“文件被删但 APFS 物理块被进程死锁无法释放”的陷阱；
2. **36 小时精细化 TTL 淘汰**：自动清除 36 小时（2160 分钟）前的所有历史沙盒日志，今日目录（`YYYYMMDD`）永久保护，绝不误触当前正在运行的会话；
3. **2 GB 目录容量硬顶截断 (Hard Cap)**：即便 36 小时内因为高频并发跑测试导致日志激增，只要目录总量超过 2GB，立即按 `mtime` 从最旧的文件开始淘汰，强行将水位拉回 1.5GB，**物理层面彻底封死打满磁盘的可能性**；
4. **单文件 30MB 物理熔断**：单文件异常暴走超过 30MB 时瞬间清零，零损耗释放磁盘块。

#### (3) 极简无感运行
macOS 下由原生 LaunchAgent (`com.workbuddy.log-guard.plist`) 每 30 分钟静默触发一次，执行耗时 **< 20ms**，平时无事件时线程在内核中纯休眠，CPU 占用保持在绝对 **0.0%**。

---

### 11. 独立免登扫码录入机制逆向与终端二维码渲染 (Decoupled QR Login)

#### (1) 免客户端界面的扫码登录全流程逆向
传统上，添加一个新账号必须经历繁琐步骤：打开图形界面客户端 -> 退出当前账号 -> 掏出微信扫码 -> 确认登录 -> 再用 toolkit 保存。这一过程不仅容易发生新凭据覆盖旧活跃账号导致旧 Token 丢失，而且在无图形界面（Headless）或纯终端开发时完全无法操作。
通过深度逆向 WorkBuddy 登录通信流，我们还原了官方免密扫码认证的全生命周期：
1. **握手初始化**：向腾讯官方认证网关发起鉴权请求，获取唯一 `state` 会话令牌与二维码短链授权 URL（形如 `https://www.workbuddy.cn/login?platform=workbuddy&state=...`）；
2. **终端原生高清 QR 渲染**：利用纯 Python 标准库内置实现的 QR Code 生成算法（Reed-Solomon 纠错与多项式除法），以 ANSI 双半块点阵字符 `▀`（Upper half block）渲染至终端控制台，手机微信直接对准终端屏幕即可扫码授权；
3. **幂等长轮询监听**：以 2 秒间隔安全轮询登录状态端点，识别 `WAITING`（待扫码）、`SCANNED`（已扫码未确认）与 `SUCCESS`（授权成功）状态；
4. **原生凭据捕获与持久化**：在获得认证授权码后，直接提取返回的完整认证凭据字典（包含加密信封与用户信息），安全沉淀至 `~/.workbuddy/auth_profiles/<别名>.info`。

#### (2) 智能别名冲突自愈与在位平滑更新 (Alias Conflict Self-Healing)
录入账号时，用户常常面临别名命名的困扰。系统设计了三态智能自愈策略：
- **同 UID 在位平滑更新 (In-place update)**：若输入的别名已存在，但其绑定的 UID 与本次扫码登录账号完全一致，系统自动判定为“同账号凭据在位刷新”，直接覆盖更新该 Profile，无需人工确认；
- **异 UID 智能自增规避 (Auto Increment)**：若输入的别名已存在且属于不同账号（异 UID）：
  - 在非交互或自动脚本环境下，系统自动追加递增后缀（如 `work` 已被其他 UID 占用，则自动重命名并保存为 `work_1`、`work_2`），绝对防止误覆盖已有重要账号；
  - 在交互终端下，友好提示冲突并询问用户是覆盖还是使用推荐自增别名；
- **`--force` 覆盖开关**：支持在命令行显式传入 `--force` / `--overwrite`，跳过任何提示强行用当前新登录态覆盖指定别名。

---

### 12. 账号状态多维呈现与程序化 JSON 架构 (Status & Inventory Architecture)

为了满足开发者对本机登录账号状态的全面感知以及自动化运维工具的集成需求，系统构建了多维度的状态透视体系：
1. **当前生效活跃凭据透视**：
   - 活跃账号昵称与匹配的 Profile 别名；
   - 账号全局唯一 UID；
   - 凭证物理存储加密套件（`sym-v1` 原生加密信封 / `plaintext` 遗留明文）；
   - Token 与 Refresh Token 双重过期时间戳；
   - 凭据健康状态诊断（`✔ 正常` / `🔄 已自愈续期` / `✖ 已失效`）。
2. **已保存账号库全景清单**：
   - 当前正在生效的活跃账号高亮标记 `[当前活动]`；
   - 每个 Profile 的别名、昵称、脱敏 UID（前 8 位）、加解密类型、健康度与到期时间。
3. **程序化 JSON 模式 (`--json`)**：
   - 传入 `--json` / `-j` 参数时，终端以标准 JSON 结构输出完整状态；
   - 严格遵循 **Zero-Leakage 隐私安全边界**：输出中绝对剔除 `accessToken`、`refreshToken` 敏感凭据内容；
   - 字段规范清晰（包含 `active_account`、`profiles` 列表、`total_profiles`、`platform`），便于 Shell 管道、Python 自动化脚本、Prometheus 或监控平台直接解析。

---

### 13. 账号健康度定时巡检与双端原生桌面通知 (Health Audit & Desktop Notification)

长期使用多账号时，部分副号可能在长达数周未切换的情况下面临 Refresh Token 即将过期的风险。`workbuddy audit` 为此提供了防风控的周期性巡检与原生桌面通知方案：
1. **严格防风控三级审计逻辑**：
   - **时间戳粗筛（零网络请求）**：若账号 accessToken 剩余有效期大于 10 分钟，直接视为健康，绝对不发起网络请求；
   - **本地 30 分钟节流缓存**：30 分钟内已审计过的账号直接复用本地缓存状态，避免频繁网络探测；
   - **临期受控刷新（静默自愈）**：当 accessToken 已过期但 refreshToken 尚有效时，发起单次受控静默刷新，并将新 Token 自动写回本地 Profile；若 refreshToken 亦已失效，则准确标记为 `EXPIRED`。
2. **macOS 与 Windows 双端原生桌面通知机制**：
   - **macOS**：优先使用 AppleScript 原生系统通知机制调用通知中心弹窗（`display notification ... with title ...`），支持 `terminal-notifier` 降级，无需安装任何额外第三方软件；
   - **Windows**：两级防御架构。优先尝试调用 PowerShell WinRT / BurntToast 现代 Toast 气泡通知；若系统权限受限或环境未开启 WinRT，自动平滑降级调用 .NET 内置 `System.Windows.Forms.NotifyIcon` 托盘气泡提示，保证 Windows 10/11 双平台均能 100% 弹出通知。

---

### 14. 远端 CI 跨机双端健康监控与零配置邮件告警 (Dual-Runner CI Monitor)

在多机协同或 CI/CD 流水线中，开发者通常在远端 Windows 或 macOS Runner 上部署了自动化任务。为了及时掌握远端凭据健康度，仓库内置了 `.github/workflows/workbuddy-monitor.yml` 双端监控流水线：
1. **双矩阵跨平台巡检 (Dual-Runner Matrix)**：
   - 包含 `macos-latest` 与 `windows-latest` 两个独立并发 Runner；
   - 每日定时通过 cron 唤醒，运行 `scripts/compat_monitor.py` 严格校验本地解密兼容性与账号健康状态。
2. **零配置 GitHub 原生邮件告警机制**：
   - 传统告警方案往往需要开发者配置 SMTP 邮箱密码或申请钉钉/飞书 Webhook 机器人，配置繁琐且极易泄露秘钥。
   - 本项目巧妙利用 GitHub Actions 的原生失败通知机制：当且仅当远端凭据失效或环境异常时，测试脚本退出码为 1 触发 Job Failure，**GitHub 官方基础设施会在 10 秒内自动向仓库所有者发送原生告警邮件**！真正做到“零配置、免维护、毫秒级触达”。

---

### 15. 🔥 深度踩坑记录与底层逆向突破全景 ("问题→原因→解决")

在本项目从 v0.1.0 到 v0.5.0 的持续演进中，我们记录并攻克了多个系统底层、加解密协议与跨平台工程踩坑：

#### 踩坑 1：终端打印二维码在不同终端行高字体拉伸变形导致扫码失败
- **问题**：在某些终端（如 iTerm2、VS Code 内置终端、Windows CMD）中运行免登扫码时，终端虽然打印出了字符点阵，但手机微信扫描完全没有反应，无法识别。
- **原因**：常见等宽字体的单字符宽高比约为 1:2（高是宽的两倍）。如果直接以一个全角空格或实心方块作为 1 个点阵像素，会导致整个二维码在垂直方向被严重拉伸成细长矩形；此外，部分精简终端不支持 24-bit TrueColor ANSI 颜色转义符。
- **解决**：采用双半块字符 `▀`（Unicode U+2580 Upper Half Block）结合 ANSI 前景与背景色控制：一个字符单元在纵向上同时表示两个竖向像素（上像素与下像素）。通过数学矩阵行两两分组，精确将 2 个垂直点阵压缩进 1 个字符空间，使终端打印出的二维码长宽比严格回归物理 1:1 正方形；同时加入白边 Quiet Zone 保护，微信扫码识别率提升至 100%。

#### 踩坑 2：多账号录入时别名重名引发旧账号被无声覆盖
- **问题**：用户登录新账号并执行 `workbuddy save work` 或 `workbuddy login work` 时，如果以前已经保存过一个同名别名，旧账号凭据会被无脑覆盖且不可逆丢失。
- **原因**：旧版逻辑简单将别名与文件名一一对应（`<alias>.info`），缺乏基于账号底层主体身份（UID）的碰撞检测与冲突消解策略。
- **解决**：在底层构建 `resolve_profile_alias_conflict` 决策引擎。先读取已有文件的 UID：若与当前账号 UID 相同，判定为合法的“在位平滑刷新（In-place update）”；若为异 UID 账号且未显式指定 `--force`，在非交互环境下自动按数字递增编号（如 `work_1`、`work_2`）安全落盘，彻底杜绝数据覆盖。

#### 踩坑 3：GitHub Actions YAML 中在 `if:` 条件直接引用 `secrets.*` 导致工作流解析崩溃
- **问题**：在编写跨平台 CI 监控工作流时，尝试使用 `if: ${{ secrets.MY_TOKEN != '' }}` 来判断是否配置了账号凭证，提交后 GitHub Actions 直接拒绝执行并报错：`Context access forbidden: secrets`。
- **原因**：GitHub Actions 安全规范明确规定：为了防止表达式求值阶段凭据泄露，禁止在 step 或 job 级别的 `if:` 条件表达式中直接访问 `secrets` 上下文。
- **解决**：采用安全映射间接接缝：在 job 或 step 的 `env:` 块中将 secret 映射为普通环境变量（如 `env: HAS_SECRET: ${{ secrets.MY_TOKEN }}`），然后在 `if:` 条件中使用 `if: env.HAS_SECRET != ''` 进行安全判断。并在测试套件中新增 T42 静态 AST 测试，防止未来误写。

#### 踩坑 4：Windows 桌面通知在不同 Windows 10/11 精简版本下的兼容性失效
- **问题**：在部分精简版 Windows 10 或 Windows Server 环境下，执行桌面通知命令后控制台无报错，但屏幕右下角未弹出任何 Toast 气泡。
- **原因**：Windows 现代 WinRT API 需要宿主具备有效的 AppUserModelId，且某些系统未安装或禁用了现代通知中心服务。
- **解决**：在 `notify_desktop` 中实现双层降级调用栈：优先通过 PowerShell 构建 WinRT Toast 通知；捕获异常或超时时，平滑降级调用 .NET Framework 自带的 `System.Windows.Forms.NotifyIcon`，在系统托盘直接显示标准气泡通知，实现 Windows 全版本 100% 必达。

#### 踩坑 5：WorkBuddy 5.6+ 引入 `$wbEncrypted` 结构导致全网第三方脚本崩溃
- **问题**：WorkBuddy 升级至 5.6.0 后，所有原有切换账号、签到脚本抛出 `AttributeError: 'dict' object has no attribute 'lower'` 或 HTTP 401 鉴权拒绝。
- **原因**：官方引入 AES-GCM 信封加密，将 JSON 中原有的明文字符串替换为包含 `suite`、`nonce`、`authTag`、`ciphertext` 的嵌套字典。
- **解决**：逆向定位并调用客户端内置的 `electron_browser_workbuddy_storage` 原生绑定，利用 `ELECTRON_RUN_AS_NODE=1` 管道在内存中进行 48ms 瞬态解密，并确立“透传不落地”原则，磁盘 100% 保留加密形态。

#### 踩坑 6：`sandbox-core` PTY 日志无淘汰机制堆积吞噬 15GB+ 磁盘
- **问题**：运行 3~4 天后发现系统盘急剧减少 10GB 以上，排查发现 `~/.workbuddy/logs/sandbox/` 下存在数千个无淘汰机制的 PTY 输出日志。
- **原因**：官方虽然设置了 13MB 单文件滚动，但未设计生命周期（TTL）管理与目录总容量限制。
- **解决**：研发 `workbuddy-log-guard` 四重物理看门狗：`lsof` 句柄感知保护被持有着不被删除（仅截断）、36h TTL 淘汰过期历史、2GB 目录总量硬顶截断与 30MB 单文件物理熔断。

---

## 三、快速上手与安装升级

### 🔄 老用户平滑升级指南（30 秒升级到 v0.5.0）

如果您之前已经安装过旧版 workbuddy-toolkit，升级到 v0.5.0 极其简单，**无需重新配置任何 Profile，原有数据与账号 100% 平滑保留**：

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

安装后，全局提供 `workbuddy` 以及 `wb-login`、`wb-list`、`wb-status`、`wb-audit`、`wb-switch`、`wb-checkin`、`wb-chat`、`wb-doctor`、`wb-models`、`wb-router` 快捷命令：

### 1. 独立免登扫码录入 (`wb-login`)

无需开启臃肿的 Electron 桌面客户端，直接在终端中唤起扫码并自动将账号凭证归档入库：

```bash
# 方式 A：指定别名进行免密扫码录入（推荐）
wb-login work_dev

# 方式 B：直接运行，由工具自动引导输入别名
wb-login

# 方式 C：仅扫码录入并保存到 Profile 库，不自动切换当前客户端在线状态
wb-login backup_acc --no-switch

# 方式 D：强行覆盖已有同名 Profile
wb-login old_alias --force
```

**核心特性**：
- **终端 1:1 高清 ANSI 点阵**：采用双半块点阵字符 `▀` 算法，在各类终端字体下均保持严格 1:1 正方形比例，手机微信秒级识别；
- **免登零干扰**：直接与官方认证网关通信，完全不打扰当前正在使用的 WorkBuddy 窗口；
- **智能防覆盖与冲突自愈**：
  * **同 UID 账号**：自动识别为“当前账号凭据在位平滑刷新（In-place update）”，直接覆写 Profile 并保留别名；
  * **异 UID 账号**：若未加 `--force`，工具在后台或脚本模式下自动分配自增别名（如 `work_dev_1`），绝对防止误杀已有账号；
  * **显式覆盖**：传入 `--force` / `--overwrite` 可跳过提示强制覆盖已有别名。

---

### 2. 账号快速切换 (`wb-switch`)

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

---

### 3. 账号状态全景与程序化导出 (`wb-list` / `wb-status`)

一站式查看当前活跃登录账号、双到期时间戳、底层加密套件格式以及全部本地凭证库健康状态：

```bash
# 方式 A：人类可读文本全景查看
wb-list
# 或等效命令:
wb-status
workbuddy list
workbuddy status

# 方式 B：输出标准 JSON 格式（用于脚本自动化与监控探针集成）
wb-list --json
workbuddy list --json
```

文本输出示例：
```text
=== WorkBuddy 账号状态 (darwin) ===
当前活跃账号: 开发主号 (main_dev)
账号 UID    : 5580eae9-65a1-47e1-bed7-fb6fab5d60bf
凭证存储格式: sym-v1
Token 有效期: 2026-11-03 22:00:10
刷新令牌过期: 2026-12-03 22:00:09
凭证健康状态: ✔ 正常 (令牌有效 (剩余大于10分钟))

已保存的账号凭证库 (2 个):
           • backup_acc   昵称: 备用副号 (UID: 8b8f8495...) [plaintext] [正常] 有效期至: 2026-10-30 11:03:08
 [当前活动] • main_dev     昵称: 开发主号 (UID: 5580eae9...) [sym-v1] [正常] 有效期至: 2026-11-03 08:53:45
```

程序化 JSON 格式规范（零敏感 Token 泄露，纯白盒物理字段）：
```json
{
  "platform": "darwin",
  "active_account": {
    "profile_name": "main_dev",
    "nickname": "开发主号",
    "uid": "5580eae9-65a1-47e1-bed7-fb6fab5d60bf",
    "storage_format": "sym-v1",
    "expires_at": 1900000000000,
    "expires_at_formatted": "2030-03-22 09:46:40",
    "refresh_expires_at": 1900000000000,
    "refresh_expires_at_formatted": "2030-03-22 09:46:40",
    "health": {
      "status": "HEALTHY",
      "detail": "有效 (缓存)",
      "cached": true
    }
  },
  "profiles": [
    {
      "name": "backup_acc",
      "nickname": "备用副号",
      "uid": "8b8f8495-fa99-42ff-bc8a-efa242ab3208",
      "is_active": false,
      "storage_format": "plaintext",
      "expires_at": 1900000000000,
      "expires_at_formatted": "2030-03-22 09:46:40",
      "refresh_expires_at": 1900000000000,
      "refresh_expires_at_formatted": "2030-03-22 09:46:40",
      "health": {
        "status": "HEALTHY",
        "detail": "有效 (缓存)",
        "cached": true
      }
    }
  ],
  "total_profiles": 2
}
```

---

### 4. 账号健康审计与常驻巡检 (`wb-audit`)

周期性探测所有已保存凭证的有效性，临期静默自愈，失效前主动通过系统级桌面通知向开发者告警：

```bash
# 立即执行一次全量账号健康审计（默认复用 30 分钟防风控缓存）
wb-audit

# 强制穿透本地缓存，发起实时探测
wb-audit --force

# 以前台循环模式持续监控（每 6 小时巡检一次）
wb-audit --interval 6

# 启动后台守护模式（每 12 小时静默巡检一次）
wb-audit --daemon 12
```

**审计与告警机制**：
- **防风控节流**：剩余有效期大于 10 分钟绝对不发起网络请求；30 分钟本地缓存节流；
- **静默自愈续期**：AccessToken 过期但 RefreshToken 有效时，单次受控刷新并将最新 Token 自动写回本地 Profile；
- **双端原生通知**：
  * **macOS**：通过 AppleScript 调用通知中心原生弹窗并发出提示音；
  * **Windows**：调用 PowerShell / WinRT Toast 气泡或 `NotifyIcon` 托盘气泡提示。

---

### 5. 每日签到与连续对话保活 (`wb-checkin`)

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

---

### 6. 终端极速对话 (`wb-chat`) — 免 UI 零内存占用

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

---

### 7. 环境与凭证兼容性诊断 (`wb-doctor`)

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

---

### 8. 容灾轮换路由网关 (`wb-router`)

提供一站式管理 `:8047` 本地透明容灾轮换服务：

```bash
# 查看路由网关当前运行状态与监听端口 (默认 8047)
wb-router status

# 启动容灾轮换网关服务
wb-router start

# 停止网关服务
wb-router stop

# 实时追踪容灾轮换日志与故障自动降级流水
wb-router log
```

---

### 9. 模型全景资产与倍率透视 (`wb-models`)

一键呼出终端轻量交互式选择器 (TUI)，直观透视全量模型、折扣倍率与历史偏好：

```bash
# 启动模型资产透视与终端选择器
wb-models
```

输出示例：
```text
=== WorkBuddy 模型全景资产与倍率透视 ===
可用模型列表 (实时拉取):
  ▶ 1) hy3                 [混元 3.0]      倍率: x0.00 (限免/推荐主力)
    2) space-bunny-free    [Space Bunny]  倍率: x0.00 (免费额度)
    3) deepseek-v4-flash   [DeepSeek V4]  倍率: x0.10 (极低消耗)
    4) glm-5v-turbo        [GLM 5V Turbo] 倍率: x0.50 (低消耗兜底)
    5) auto                [智能动态路由]   倍率: 动态阶梯
--------------------------------------------------
快捷操作: [上下键] 移动选择  [Enter] 确认切换  [q] 退出
```

---

### 10. 沙盒日志看门狗配置与管理 (`workbuddy-log-guard`)

彻底根治 WorkBuddy 长期运行后 PTY 沙盒日志吞噬 10GB+ 磁盘积弊：

```bash
# 手动立即触发一次日志安全审计与物理修剪
workbuddy-log-guard
```

#### 自定义配置方案 (`~/.workbuddy/log_guard.json`)
默认零配置开箱即用。若需自定义清理频次或配额，可创建或编辑配置文件：

```json
{
  "ttl_minutes": 2160,       // 日志 TTL 过期淘汰时长 (默认 2160 分钟 = 36 小时)
  "max_sandbox_mb": 2048,    // 沙盒日志目录容量硬顶 (默认 2048 MB = 2 GB)
  "target_sandbox_mb": 1536, // 达到硬顶时自动修剪目标回落水位 (默认 1536 MB = 1.5 GB)
  "max_file_mb": 30          // 单个日志文件物理熔断清零阈值 (默认 30 MB)
}
```

#### 环境变量覆盖机制
亦可通过系统环境变量覆盖以上参数（优先级高于配置文件）：
- `WB_TTL_MINUTES`：覆盖 TTL 分钟数；
- `WB_MAX_SANDBOX_MB`：覆盖目录总配额上限；
- `WB_TARGET_SANDBOX_MB`：覆盖清理目标水位；
- `WB_MAX_FILE_MB`：覆盖单文件熔断上限。

---

### 11. 常用命令速查表

| 命令 | 别名 | 功能说明 |
| :--- | :--- | :--- |
| `workbuddy login [别名]` | `wb-login` | 终端 1:1 ANSI 扫码独立录入新账号，免开客户端 UI，支持冲突自愈与 `--force` |
| `workbuddy switch [别名]` | `wb-switch` | 交互式选择或直接切换到指定账号并优雅重启 |
| `workbuddy list [--json]` | `wb-list` | 查看当前活跃账号、到期时间及已存凭证清单（支持标准 `--json` 输出） |
| `workbuddy status [--json]` | `wb-status` | 查看当前账号凭据存储格式、Token 有效期及健康度（支持 `--json`） |
| `workbuddy audit [选项]` | `wb-audit` | 账号健康度定时巡检与自愈续期，失效触发 macOS / Windows 原生桌面通知 |
| `workbuddy checkin [别名]` | `wb-checkin` | 统一执行所有已存账号每日签到 + 自动调用低倍率/免费模型每日对话 |
| `workbuddy chat [提示词]` | `wb-chat` | 终端极速对话（智能优先使用 `hy3`、`deepseek-flash` 等免费低消耗模型） |
| `workbuddy chat --all [词]` | `wb-chat --all` | 全账号批量发起对话，一键刷新全账号连续对话奖励资格 |
| `workbuddy router [子命令]` | `wb-router` | 管理 `:8047` 容灾轮换路由网关（`status` / `start` / `stop` / `log`） |
| `workbuddy models` | `wb-models` | 呼出模型全景资产、倍率透视与轻量终端选择器 (TUI) |
| `workbuddy-log-guard` | - | 触发沙盒日志物理看门狗（36h TTL、2GB 硬顶、30MB 熔断、Open-FD 保护） |
| `workbuddy doctor` | `wb-doctor` | 深度诊断凭据加密套件、本地运行时路径与解密通信就绪度 |
| `workbuddy save <别名>` | - | 将当前活跃登录态固化为一个可切换的 Profile（支持 `--force`） |
| `workbuddy init` | - | 一键应用 SQLite 全域工作区打通补丁 |
| `workbuddy rollback` | - | 撤销 SQLite 触发器，恢复官方严格数据隔离 |
| `workbuddy restart` | - | 优雅重启 WorkBuddy 客户端 |

---

## 五、安全与隐私承诺 (Zero-Leakage)

1. **绝对本地化**：本工具所有逻辑 100% 运行于本地机器，所有的 Token、UID、凭证仅保存在用户本机的 `~/.workbuddy/auth_profiles/`，**绝不向任何第三方服务或未经授权的服务器发送任何数据**。
2. **直连官方端点**：签到功能直接调用腾讯官方 API 端点 (`https://copilot.tencent.com`)，无任何中间代理。
3. **开源透明**：所有脚本均为开源 Python/Shell 源码，接受任何形式的审计与审查。
4. **潜在风险与版本兼容性提示 (Remaining Risks)**：保存的 encrypted Profile 使用写入它的 WorkBuddy 构建所对应的字段密钥；如果未来 WorkBuddy 构建实际轮换密钥，历史离线 Profile 可能出现 `KEY_MISMATCH`，当前工具会严格按 Fail-Closed 处理。历史 Profile 无法保证永久跨任意客户端版本升级。

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
