# 命令参考

这份文档是 WorkBuddy Toolkit 主要命令行能力的实用索引。当前版本支持的精确参数，请以 `workbuddy help` / `wb-help` 和各命令自己的帮助输出为准。

## 命令总览

| 命令 | 用途 | 常见场景 |
|---|---|---|
| `workbuddy init` | 开启多账号工作区共享（先备份每个会话的原始归属） | 第一次安装或修复 |
| `workbuddy rollback [UID]` | 撤销共享，按备份恢复会话与自动化任务的原始归属；UID 仅用于没有备份记录的会话 | 不再需要共享或卸载前 |
| `wb-tool` | 交互式控制中心 | 免记命令引导式操作全量功能 |
| `wb-login` | 添加或刷新账号配置 | 添加新的 WorkBuddy 账号 |
| `wb-list` | 列出已保存账号 | 查看有哪些账号可用 |
| `wb-status` | 查看当前账号状态 | 确认当前身份和健康状态 |
| `wb-switch` | 切换到另一个已保存账号 | 不重新登录直接换号 |
| `wb-remove` | 删除账号（移入本地回收站，可恢复） | 清理不再使用的账号 |
| `wb-audit` | 巡检凭据健康度 | 检查过期或刷新问题 |
| `wb-checkin` | 执行每日签到 / 连续任务 | 手动或定时日常任务 |
| `wb-usage` | 查看使用量 / 积分流速 | 分析一段时间的消耗 |
| `wb-chat` | 从终端调用 WorkBuddy 模型 | 轻量命令行交互 |
| `wb-router` | 管理可选容灾路由 | 模型请求容灾 |
| `wb-models` | 查看模型清单与倍率 | 模型选择 / 成本判断 |
| `wb-doctor` | 诊断本地兼容性 | 上游更新后的首个检查命令 |
| `wb-help` | 查看已安装命令帮助 | 发现当前命令能力 |

多数 `wb-*` 命令是 Toolkit 安装后对主 `workbuddy` 命令行的便捷别名。

## 交互控制中心 (`wb-tool`)

```bash
wb-tool
# 或使用完整形式: workbuddy tool
```

启动零认知负担的引导式控制中心，集成积分查看、账号切换、每日签到、模型选择、磁盘清理与客户端重启等完整生命周期操作。支持层级面包屑回退（子菜单输入 `0` / `q` / `Esc` 返回主菜单）与原地热重载连续操作。

## 推荐的首次运行顺序

```bash
workbuddy init
workbuddy doctor
workbuddy status
wb-list
```

如果 `doctor` 已经报告运行时不兼容或只解析了一部分能力，不要一上来反复切换账号。

## 账号生命周期

### 添加账号

```bash
wb-login
```

用于添加新账号，或通过 Toolkit 登录流程刷新已有账号配置。

### 查看已保存账号

```bash
wb-list
```

如果你更关心当前活跃账号和运行时状态，用：

```bash
wb-status
```

### 切换账号

```bash
wb-switch
```

切换不是简单文件覆盖。Toolkit 会先同步当前活跃凭据，再替换目标账号配置，降低较新的 Token 被旧状态覆盖的风险。

### 删除账号

```bash
wb-remove <账号别名> [-y] [--force] [--purge-memory]   # 删除（移入回收站）
wb-remove [-y] -- -<别名>             # 删除以 - 开头的别名
wb-remove --list-trash               # 查看回收站（凭证 + 人格/记忆归档）
wb-remove --restore <文件名>         # 恢复单个账号（连同配对的人格/记忆）
wb-remove --restore-memory <归档名>  # 凭证已删/改名时，单独还原人格/记忆
wb-remove --purge <文件名> [-y] [--force-partial]  # 单条销毁（不可恢复）
wb-remove --empty-trash [-y] [--force-partial]     # 清空回收站（不可恢复）
```

顶层别名 `rm` / `del` / `delete` 与 `remove` 等价（如 `workbuddy rm <别名>`），仅为习惯兼容；脚本里建议写全 `remove`，避免与 shell 的 `rm` 混淆。

把账号从本地备份库移入回收站（`auth_profiles/.trash/`），文件名统一带微秒级删除时间戳，同微秒戳碰撞自动追加 `_N` 序号，并用 `O_CREAT|O_EXCL` 原子占位，绝不覆盖既有凭据。

要点：

- 客户端当前登录不受影响；`checkin` / `audit` / `status` 下次运行自然不再包含该账号
- 已删除的账号**不会**被每日签到的自动发现重新收录（回收站即墓碑）
- 删除当前登录账号的备份时会有黄色警告：该账号的登录态在客户端切换/退出后需要重新扫码（`wb-login`）
- 别名必须唯一匹配（支持别名/昵称，歧义时拒绝执行）；退出码 0/1 可用于脚本
- `-y/--yes` 只跳过普通确认；删除**当前登录账号的备份**属高危，即使带 `-y` 也会再问一次，只有 `--force` 才放宽该保护（`--force` 不用于跳过普通确认，与 `save --force` 语义区分）
- `wb-status` 会显示回收站条目数；「删除 = 移入回收站」，凭据仍在磁盘上，彻底销毁请 `--empty-trash`，只销毁某一条请 `--purge <文件名>`（0 字节占位等工具残留可用它清掉）

#### 连同人格/记忆一起清理

默认只删凭证，人格/记忆原样留在原地。加 `--purge-memory` 会把这些**一起移入回收站**（与凭证同一个 stem，恢复时自动配对）：

| 会搬走 | 不会动 |
|---|---|
| 账号目录里的 `MEMORY.md` / `SOUL.md` / `USER.md` / `IDENTITY.md` / `BOOTSTRAP.md` | `AGENT.md`（工作准则）、`workspace-state.json`（界面状态） |
| `memory/<uid>_memory.md` 与 `.bak`（云端记忆缓存） | 会话历史 `workbuddy.db`、`storage/user-<uid>*` |
| `cache/shared_memory/{originals,backups}/<uid>/`（工具箱记忆副本） | 数据根下旧代全局 `MEMORY.md` 等（不属于任何单个账号，只报告） |

- 目录名按白名单匹配：`user-<uid>-personal`、`user-<uid>-enterprise[-*]`、裸 `user-<uid>`；`user-<uid>-extra-personal` 这类长得像但不是的目录只报告、不搬
- 账号目录里只搬指定的几个文件，不整目录删，所以删账号不会顺手带走工作准则；`cache/shared_memory/{originals,backups}/<uid>/` 这类按账号独立的副本目录整体搬走（清单里标 `dir`）
- 档案进 `auth_profiles/.trash/memory/<同一个 stem>/`，里面有 `manifest.json`（原路径清单）与 `files/`；`--list-trash` 会显示项数与是否「(部分)」
- `--purge` / `--empty-trash` 会连带销毁配对归档；凭证删不掉时归档**不会**先删（避免"账号还能恢复、人格已经没了"）
- `--empty-trash` 按确认时看到的清单销毁：确认期间新增的凭证或归档不会被删，会单独列出来，重跑一次再确认
- 凭证已被清空、只剩归档（孤儿）时，`--list-trash` 仍会列出，可用 `--purge <归档名>` 销毁；`--empty-trash` 也会一并清理
- 只搬走一部分（源文件被占用/跨卷复制后删源失败）时，归档标 `partial`（`manifest.partial` + 空标记 `PARTIAL`），`--list-trash` 标「(部分)」，`--purge` / `--empty-trash` **默认拒绝**销毁它——那可能是唯一完整副本，确认不要才加 `--force-partial`
- 退出码：`0` 完成；`1` 失败或未执行（含参数错误；凭证可能已经销毁、只是档案没删掉，具体看输出）；`3` 账号已删除但档案没搬干净（只搬走一部分、归档读不出、UID 非法、同 UID 还有别的别名）。`3` 时凭证仍在回收站，可用 `--restore` 回滚
- UID 非法（含 `../`、盘符、超长）时**不会**搬数据根之外的任何目录：拒绝并打印原因，退出码 3，明文记忆留在原处等手工处理
- 同一 UID 有多个别名时，`--purge-memory` 不会搬动记忆目录（否则会把另一个别名的人格一起带走）：只删凭证并给出提示，退出码 3
- `--force-partial` 与 `--force` 不是一回事：`--force` 只放宽「删除当前登录账号备份」的保护，不能与回收站模式同用；`--force-partial` 只用于 `--purge` / `--empty-trash`，用来销毁 partial 归档
- 回收站目录本身不可读时，签到会**放弃自动入库**并给出 `--purge` / `--empty-trash` 补救提示，绝不会把已删账号复活

## 健康检查与诊断

### 凭据巡检

```bash
wb-audit
```

用于检查账号健康状态，尤其适合长期没有切换过的副号。

### 兼容性诊断

```bash
wb-doctor
```

这些情况建议先运行 `doctor`：

- 升级 WorkBuddy 后；
- 换机器后；
- 突然出现异常退出登录；
- 出现沙盒或 IPC 相关故障；
- 重装 Toolkit 后。

README 不再硬编码所有可能的诊断状态。真实运行时输出比静态兼容承诺更有价值。

### exit 137 / 命令卡死排查

当前 Toolkit 提供专门取证入口：

```bash
wb-doctor --inspect-137
```

当命令被杀，或故障特征指向沙盒 / 资源耗尽时使用。建议配合 [`docs/incidents/`](incidents/README.md) 下的事故复盘一起判断。

## 自动化

### 每日签到

```bash
wb-checkin
```

建议第一次先手动运行。确认命令本身成功后，再依赖后台定时任务。

Toolkit 安装器可以接入平台原生调度。具体方式取决于操作系统，见 [入门指南](getting-started.md)。

## 使用量查看

```bash
wb-usage
```

用于查看 Toolkit 能提供的使用量 / 积分流速信息。如果要把输出交给其他程序处理，优先使用当前版本支持的机器可读输出。

## 终端模型调用

```bash
wb-chat
```

这是可选能力。基础账号管理不要求使用终端模型调用。

## 容灾路由

```bash
wb-router
```

容灾路由是高级能力，用于把模型层故障与账号健康状态分开处理。基础安装并不要求启用。

## 模型清单

```bash
wb-models
```

用于查看 Toolkit 能观察到的模型清单和相关元数据，辅助模型选择和使用量判断。

## 机器可读状态

部分状态和诊断命令支持 JSON 输出。旧 README 曾记录 `--json` 用于状态 / 诊断场景。真正接入自动化前，请先检查当前安装版本的命令帮助，确认参数和字段名。

示例：

```bash
wb-status --json
```

自动化应依赖已文档化字段，并允许未来增加新字段。

## 安全操作顺序

WorkBuddy 上游发生变化时，建议按这个顺序：

```text
1. wb-doctor
2. wb-status
3. wb-list
4. 确认无异常后，再执行写入 / 切换 / 自动化操作
```

这样可以把兼容性检查放在状态修改之前。

## 相关文档

- [入门指南](getting-started.md)
- [架构说明](architecture.md)
- [工程笔记](engineering-notes.md)
- [事故复盘](incidents/README.md)