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
| `wb-remove` | 删除本地已保存的账号凭证（可列出/还原回收站） | 清理不再使用的账号 |
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

删除分两层：**凭证**与**账号档案**。默认只删凭证，档案保留并在输出里列明路径；要连人格/记忆一起清，加 `--purge-memory`。

| 层 | 具体内容 | 默认 | `--purge-memory` |
|---|---|---|---|
| 凭证 | `auth_profiles/<别名>.info` | 移入回收站 | 与凭证同样处理 |
| 账号档案 | `user-<uid>-*/`（`MEMORY.md` / `SOUL.md` / `USER.md` / `IDENTITY.md`）、`memory/<uid>_memory.md(.bak)`、工具箱记忆副本 `cache/shared_memory/{originals,backups}/<uid>/` | **保留**，输出列明位置 | 与凭证配对移入回收站，`--purge` 时一并抹除 |

```bash
workbuddy remove <账号名|昵称|UID> [--yes] [--force] [--purge] [--purge-memory] [--json]
workbuddy remove --list-trash [--json]
workbuddy remove --restore <回收站文件名> [--yes] [--force] [--json]
workbuddy remove --restore-memory <归档目录名> [--json]
workbuddy remove --purge-trash <文件名|归档目录名> [--yes] [--json]
```

（`wb-remove` 是安装后提供的别名，参数完全相同。）

不涉及服务端账号；也不删会话历史（`workbuddy.db`）、`storage/user-<uid>*` 与 `~/.workbuddy/<uid>/` 下的侧栏快照——那些是会话与界面数据，不是人格/记忆。

参数：

| 参数 | 含义 |
|---|---|
| `-y` / `--yes` / `--confirm` | 跳过交互确认。非 TTY 环境（管道、cron、定时任务）**必须**带上，否则直接拒绝执行（退出码 1） |
| `--force` | 只表示「放宽保护」：删除当前活跃账号、删除身份未知的损坏凭证、恢复时覆盖同名账号、同一 UID 有多份 Profile 时仍清记忆。**不再与 `-y` 互为别名**，不能替代确认 |
| `--purge` | 凭证与已归档的账号档案永久删除，不进回收站 |
| `--purge-memory` | 同时清理该 UID 的人格/记忆档案；默认移入回收站，与 `--purge` 连用才抹除 |
| `--restore-memory <名称>` | 只还原一个记忆归档；凭证已手工删除或改名、无法用 `--restore` 配对时使用 |
| `--purge-trash <名称>` | 永久清除单条回收站残留（0 字节占位、损坏备份）；给凭证名时连同配对的记忆归档一起清 |
| `--json` | 输出机器可读结果（含 `memory_action` / `memory_bundle` / `memory_items` / `memory_kept` / `memory_links` / `memory_new`） |
| `--` | 之后的内容一律按位置参数处理，用于 `-weird` 这类以连字符开头的账号别名，例如 `workbuddy remove --yes -- -weird` |

未知选项、或给出的目标账号多于一个时，只打印用法并以**退出码 2** 结束，不执行任何删除。

常用写法：

```bash
workbuddy remove old_acc --yes                          # 只删凭证，记忆保留并提示位置
workbuddy remove old_acc --yes --purge-memory           # 凭证 + 人格/记忆一起进回收站
workbuddy remove old_acc --yes --purge --purge-memory   # 两者都彻底抹除
```

回收站布局：

```
~/.workbuddy/auth_profiles_trash/
├── <别名>-<YYYYMMDD-HHMMSS>[-序号].info      # 凭证
└── memory/<同一个 stem>/                      # 与凭证配对的账号档案
    ├── manifest.json                          # 原路径清单，restore 据此还原
    └── files/...
```

凭证备份名用 `O_CREAT|O_EXCL` 独占创建，避免并发删除同名账号时互相覆盖。

保护规则：

- 目标必须唯一匹配（别名 / 昵称 / UID 前缀），有歧义时列出候选并拒绝执行；
- 删除当前活跃账号需要显式 `--force`：客户端会保持当前登录，但本地不再有备份，切走后只能重新扫码；
- 删除活跃账号后会写一条**独立于回收站的删除墓碑**：`wb-checkin` 不会从当前登录态自动把它重新收录；重新扫码登录或 `wb-save` 该账号会解除墓碑；
- `--purge-memory` 在用户确认前先快照档案列表，确认期间新出现的档案不会被这次操作带走，输出会列明"确认后新增、已保留"；
- 非交互式环境（管道、cron、定时任务）必须显式 `--yes`，否则直接拒绝（退出码 1），避免脚本误删；
- 同一 UID 已无其他账号时，同步清理审计缓存，避免 `wb-status` / `wb-audit` 继续显示已删除账号；
- 同一 UID 若还有别的 Profile，`--purge-memory` 默认拒绝（记忆按 UID 共享，清掉会让剩下那份登录后记忆全空），确认要清需再加 `--force`；
- 凭证里没有合法 UID（损坏、缺字段、含 `../` 等路径成分）时拒绝清记忆——路径按 UID 拼接，猜错会动到别的账号；
- 账号目录本身是符号链接 / Windows junction 时**不归档、不删除**，只在输出里列出；这类路径的"删除"会作用到链接目标，风险高于收益；
- 归档在 POSIX 下目录权限收为 `0700`、清单 `0600`，避免同机其他用户读取明文人格/记忆；
- 半截 JSON 之类的损坏凭证不会被 `wb-list` 收录，此时按文件名兜底删除，但**必须显式 `--force`**，因为其身份无法校验（输出会标注身份未经校验）。

误删可从回收站恢复：

```bash
workbuddy remove --list-trash                                  # 列出凭证备份与记忆归档
workbuddy remove --restore demo-20260101-000000.info --yes     # 还原凭证 + 配对的人格/记忆
workbuddy remove --restore-memory demo-20260101-000000         # 只还原记忆归档
workbuddy remove --purge-trash demo-20260101-000000.info --yes # 单条清除损坏/占位残留
```

`--restore` 把该备份还原为 `~/.workbuddy/auth_profiles/<别名>.info`；目标已存在则拒绝，需要 `--force` 覆盖。若存在同 stem 的记忆归档，会一并还原；**已存在的记忆路径一律不覆盖**，跳过项与归档位置会在输出里列明。`--restore-memory` 用于凭证备份已被手工删除或改名的情况：它只按 `manifest.json` 把人格/记忆放回原路径，同样不覆盖已存在路径。

恢复前会校验备份能不能解析成凭证：0 字节占位或半截 JSON 默认拒绝（`refused_invalid`），避免"恢复成功但登录不了"的假象；确认要原样取回可加 `--force`，只想清理则用 `--purge-trash`。

如果账号别名刚好是 `remove` / `rm` / `delete` / `del` / `forget`，这几个词现在优先按子命令解析。切换这类账号请显式用 `workbuddy switch <别名>`；裸敲命令（如 `workbuddy rm`）只会打印用法，不会删除任何账号。

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