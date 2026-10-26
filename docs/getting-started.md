# 入门指南

这份文档只解决一件事：把 WorkBuddy Toolkit 安装好，并完成第一次可验证的使用。

> 如果你只是想知道项目解决什么问题，请先看仓库根目录的 [README](../README.md)。

## 1. 系统要求

- macOS、Linux 或 Windows 10/11
- Python 3.8+（版本校验只针对 WorkBuddy 自带解释器；PATH 里的解释器按原样使用）
- 已安装并至少登录过一次 WorkBuddy 客户端
- 不要求额外的 Python 第三方依赖

## 2. 推荐安装方式

### macOS / Linux / Windows 通用

```bash
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git ~/.workbuddy/toolkit
cd ~/.workbuddy/toolkit
python3 install.py
```

Windows 如果命令是 `python`：

```powershell
git clone https://github.com/FlapPearLabs/workbuddy-toolkit.git $HOME\.workbuddy\toolkit
cd $HOME\.workbuddy\toolkit
python install.py
```

默认只安装命令行工具与 sidecar 模块：**不修改 WorkBuddy 数据库，也不注册任何后台任务**。在交互式终端中，安装程序会逐项询问下面这些可选能力（直接回车 = 否）；也可以用参数显式开启：

| 参数 | 作用 |
|---|---|
| `--init-workspace` | 开启多账号工作区共享（等同 `workbuddy init`，可用 `workbuddy rollback` 恢复） |
| `--with-checkin` | 注册每日 09:00 自动签到（会给每个已保存账号发送一次保活对话）。Windows 上若任务计划程序不可用，自动降级为登录时执行（仅签到，不含保活对话） |
| `--with-log-guard` | 注册日志 / 沙盒看门狗（每 30 分钟） |
| `--with-router` | 注册容灾路由常驻服务 127.0.0.1:8047（仅 macOS LaunchAgent） |
| `--with-services` | 以上三项后台任务全部开启 |
| `--no-input` | 不询问，未显式开启的一律跳过（CI / Agent 场景） |

`install.py` 与 `install.sh` 支持相同的参数。仓库 clone 在 `~/.workbuddy/toolkit` 或其他任意位置均可。

### 系统原生安装脚本

macOS / Linux：

```bash
cd ~/.workbuddy/toolkit
./install.sh
```

Windows PowerShell：

```powershell
cd $HOME\.workbuddy\toolkit
.\install.ps1
```

## 3. 第一次初始化

安装完成后，先运行：

```bash
workbuddy init
workbuddy doctor
workbuddy status
```

这三步分别用于：

1. 开启多账号工作区共享：会话原始归属会先备份到数据库旁路表，随时可用 `workbuddy rollback` 逐个恢复。
2. 检查当前 WorkBuddy 版本、凭据格式和本地运行时兼容性。
3. 查看当前账号与已保存账号配置的状态。

如果 `doctor` 报告不兼容，不要继续强行切换账号。先按诊断结果处理。

## 4. 添加和切换账号

添加一个新账号：

```bash
wb-login
```

查看账号：

```bash
wb-list
```

切换账号：

```bash
wb-switch
```

Toolkit 会在切换前同步当前登录态，降低旧账号配置覆盖新 Token 的风险。

### 可选：让多个账号共用记忆

默认不开启。确认要让各账号共享长期记忆时：

```bash
workbuddy memory on
```

开启后切号时会自动汇总并渲染；也可以手动执行 `workbuddy memory collect` + `workbuddy memory apply` 先看效果。

它不会覆盖你的原文：日常渲染是“你文件里现在的内容 + 追加段落”，原文逐字保留在开头；首次接入时会另存一份快照，只给 `restore` 用。
疑似重复的条目只保留质量更高的一条，落选版本留档。想还原（同时摘掉分诊写入 SOUL / USER 的段落）：

```bash
workbuddy memory restore <账号>
```

## 5. 自动签到与账号巡检

手动运行一次签到：

```bash
wb-checkin
```

检查凭据健康度：

```bash
wb-audit
```

后台调度默认不开启。需要时重新运行安装程序并加上 `--with-checkin` / `--with-log-guard`，会按系统接入原生调度：

- macOS：`launchd`
- Linux：`systemd --user`，必要时降级到 `cron`
- Windows：任务计划程序

> 自动签到与保活对话会以客户端身份批量访问 WorkBuddy 服务。多账号自动化可能触发平台风控或违反服务条款，请自行评估后再开启。

## 6. 让 AI 编程 Agent 帮你安装

如果你使用 Codex、Claude Code、Cursor、Hermes、OpenCode 或其他能执行终端命令的 Agent，可以把下面的任务交给它：

```text
请帮我安装并验证 WorkBuddy Toolkit：

1. 克隆 https://github.com/FlapPearLabs/workbuddy-toolkit.git 到 ~/.workbuddy/toolkit。
2. 根据当前操作系统运行 `install.py --no-input`；如果 Python 命令不同，请自行适配。
3. 依次运行 workbuddy init、workbuddy doctor、workbuddy status。
4. 不要修改 WorkBuddy 应用包本体。
5. 如果 doctor 报告不兼容，停止后续写操作并告诉我具体诊断结果。
6. 如果环境支持任务调度，再询问我是否启用每日 wb-checkin；我确认后再运行 `install.py --with-checkin`，不要擅自创建我没有确认的后台任务。
7. 最后汇报：安装位置、doctor 结果、当前账号状态、后台调度是否启用。
```

这个版本刻意比旧 README 中的长提示词更短。Agent 应以仓库当前实现和 `workbuddy doctor` 的实际输出为准，而不是依赖一段长期可能过期的安装说明。

## 7. 常用命令

```text
wb-help       查看命令帮助
wb-login      添加账号
wb-list       查看账号列表
wb-status     查看当前状态
wb-switch     切换账号
wb-audit      检查账号健康度
wb-checkin    签到与每日任务
wb-usage      查看积分消耗与流速
wb-chat       从终端调用模型
wb-router     管理容灾路由
wb-models     查看模型与倍率信息
wb-doctor     兼容性与故障诊断
```

完整说明见 [命令参考](command-reference.md)。

## 8. 安全回退

需要退出 Toolkit 时，可以运行：

```bash
python3 uninstall.py
```

或使用对应平台的卸载脚本。卸载会：

- 注销 Toolkit 注册的所有后台任务；
- 还原 `wb-models` 改写过的 `~/.workbuddy/models.json` 条目（否则这些模型会指向已停止的 127.0.0.1:8047）；
- 询问是否回滚工作区共享，并按备份恢复每个会话与自动化任务的原始账号归属（`--yes` / `--no-rollback`）；
- 删除 Toolkit 自己的配置与日志（`--keep-config` 可保留）；
- **保留** `~/.workbuddy/auth_profiles/` 中的账号凭证，以及 clone 在 `~/.workbuddy/toolkit` 的源码仓库。

## 下一步

- [功能参考](feature-reference.md) — 完整能力索引
- [命令参考](command-reference.md) — 命令和使用场景
- [架构说明](architecture.md) — 系统边界与设计原则
- [工程笔记](engineering-notes.md) — 为什么项目会做成现在这样
- [事故复盘](incidents/README.md) — 真实故障、证据与修复