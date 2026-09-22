# WorkBuddy Toolkit: Multi-Account Manager & Automated Check-in

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: macOS | Linux | Windows](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-brightgreen.svg)](https://github.com/FlapPearLabs/workbuddy-toolkit)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://python.org)

> **WorkBuddy (腾讯开源/商业化 AI 编程助手) 多账号无缝轮换、全域工作区打通与自动化静默签到工具箱。**  
> 深入逆向底层 SQLite 存储隔离机制与腾讯云后端鉴权协议，原生全面适配 **macOS**、**Linux** 与 **Windows** 三大操作系统，打造零侵入、高内聚、零打扰的本地自动化工作流。

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
4. 执行 `workbuddy status` 检查当前账号状态与已存凭证库；
5. 智能探测你自身（当前 AI Agent）是否拥有内置的 `schedule` / cron 调度功能：
   - 【若拥有 schedule 功能】（如 Antigravity、WorkBuddy 等内置调度器）：
     默认使用你的 schedule 工具注册一个每日定时任务（Cron: 0 9 * * *, 触发时运行 workbuddy checkin 并向我汇总汇报收益）。
     同时询问我：“已为您默认配置每天早晨 09:00 自动打卡并汇报，请问您是否需要调整打卡时间或汇报偏好？”
   - 【若没有 schedule 功能】（如部分普通 CLI Agent）：
     如实告诉我当前环境没有内置 Agent 调度能力，并请我选择签到方式：
     ① 采用安装脚本已配置的系统原生守护定时打卡（macOS launchd / Linux systemd timer / Windows 任务计划程序，每天 09:00 静默打卡写入日志）；
     ② 完全关闭后台自动打卡，后续每次由我手动在终端输入 `wb-checkin` 随时打卡。
6. 向我汇报最终安装与配置结果，并指导我如何使用 `wb-switch`（免扫码秒切账号）以及如何用 `workbuddy save <别名>` 保存当前登录态。
```

---

## ⭐ 核心终极优势：一次登录，永久免扫码！

| 对比维度 | 传统 WorkBuddy 官方体验 | 使用 WorkBuddy Toolkit |
| :--- | :--- | :--- |
| **多账号切换** | 每次换号必须在微信上**重新掏出手机扫码**，频繁中断思考 | **每个账号仅需首次扫码一次**，保存为 Profile 后随时**秒级直切，永久免扫码**！ |
| **工作区与会话** | 换号后历史对话列表变空，工作区关联折叠，需重新拉取项目 | **全域穿透打通**：无论怎么切号，所有账号看到同一个物理工作区与全量对话历史 |
| **Token 生命周期** | 切换账号后旧 Token 容易被覆盖导致失效过期 | **自动双向回存 (Sync-before-switch)**：切号前自动回写最新 Token，保持凭证新鲜 |
| **每日签到积分** | 需每天打开图形界面、手动点开活动、逐个切号点击 | **极速静默打卡 (`wb-checkin`)**：0.5 秒遍历所有账号统一领积分，三端原生系统调度自动运行 |

---

## 目录
- [一、支持平台与系统要求](#一支持平台与系统要求)
- [二、架构与底层逆向原理解析](#二架构与底层逆向原理解析)
  - [1. 工作区与会话“假丢失”根因剖析](#1-工作区与会话假丢失根因剖析)
  - [2. SQLite 触发器穿透与全域共享机制](#2-sqlite-触发器穿透与全域共享机制)
  - [3. 免扫码凭证轮换与双向 Token 同步](#3-免扫码凭证轮换与双向-token-同步)
  - [4. 每日签到协议逆向与幂等领取架构](#4-每日签到协议逆向与幂等领取架构)
  - [5. 三端原生后台定时调度与自适应探测](#5-三端原生后台定时调度与自适应探测)
- [三、快速上手与安装](#三快速上手与安装)
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
- **全版本自愈**：即便客户端升级，只要 SQLite 数据库未被彻底重建，触发器将永久生效。
- **平滑回滚**：仅需 `DROP TRIGGER` 即可恢复官方的数据隔离策略。

---

### 3. 免扫码凭证轮换与双向 Token 同步

#### (1) 凭证存储机制
WorkBuddy 的当前登录凭证以 JSON 格式存储在如下路径：  
`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`

包含字段：
- `account.uid`: 用户全局唯一标识
- `account.nickname`: 用户昵称
- `auth.accessToken`: 访问令牌（通常有效期 30 天）
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

### 4. 每日签到协议逆向与幂等领取架构

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

### 5. 三端原生后台定时调度与自适应探测

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

## 三、快速上手与安装

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

安装后，全局提供 `workbuddy`、`wb-switch`、`wb-checkin` 快捷命令：

### 1. 账号无缝切换 (`wb-switch`) — 永久免扫码

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

请选择要切换的目标账号 (一次保存，永久免扫码):
 ▶ 1) main_dev     [昵称: 开发主号] (当前使用中)
   2) backup_acc   [昵称: 备用副号]

   q) 退出 (Cancel)
----------------------------------------------
请输入序号 [1-2] 进行切换:
```

### 2. 每日签到与积分巡检 (`wb-checkin`)

```bash
# 自动扫描所有已存账号 + 当前在线账号，统一检查并领取
wb-checkin

# 或仅为特定账号执行签到
wb-checkin backup_acc
```

输出示例：
```text
=== WorkBuddy 自动每日签到 (2 个账号) ===
 ✔ backup_acc    [昵称: 备用副号] 今日已签到 | 连续 4 天 | 累计签到奖励 400 积分
 🎉 main_dev     [昵称: 开发主号] 签到成功！+100 积分 | 连续签到 6 天
----------------------------------------------
```

### 3. 查看账号状态与凭证有效期

```bash
workbuddy status
```

### 4. 保存新登录的账号 (只需做一次)

当你在 WorkBuddy 界面退出并用微信扫码登录了新账号后：
```bash
workbuddy save <取一个名字>
# 例如: workbuddy save acc_3
```
*注：即使你忘记执行 `save`，下次运行 `wb-checkin` 时脚本也会自动识别新账号并完成自动建档入库。*

### 5. 常用命令速查表

| 命令 | 别名 | 功能说明 |
| :--- | :--- | :--- |
| `workbuddy switch [别名]` | `wb-switch` | 交互式选择或直接切换到指定账号并优雅重启 (免扫码) |
| `workbuddy checkin [别名]` | `wb-checkin` | 统一执行所有已存账号的每日签到与积分到账 (后台静默) |
| `workbuddy status` | `workbuddy list` | 查看当前活跃账号、Token 有效期及全部本地凭证列表 |
| `workbuddy save <别名>` | - | 将当前活跃登录态固化为一个可切换的 Profile (永久免扫码) |
| `workbuddy init` | - | 一键应用 SQLite 全域工作区打通补丁 |
| `workbuddy rollback` | - | 撤销 SQLite 触发器，恢复官方严格数据隔离 |
| `workbuddy restart` | - | 优雅重启 WorkBuddy 客户端 |

---

## 五、安全与隐私承诺 (Zero-Leakage)

1. **绝对本地化**：本工具所有逻辑 100% 运行于本地机器，所有的 Token、UID、凭证仅保存在用户本机的 `~/.workbuddy/auth_profiles/`，**绝不向任何第三方服务或未经授权的服务器发送任何数据**。
2. **直连官方端点**：签到功能直接调用腾讯官方 API 端点 (`https://copilot.tencent.com`)，无任何中间代理。
3. **开源透明**：所有脚本均为开源 Python/Shell 源码，接受任何形式的审计与审查。

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
