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
| `wb-remove` | 删除已保存账号（默认移入回收站） | 清理不再使用的账号备份 |
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
wb-remove <别名>                     # 移入回收站，可还原
wb-remove <别名> --purge             # 彻底删除，不留副本
wb-remove <别名> --force             # 允许删除当前活跃账号的备份 / 身份无法确认的条目
wb-remove <别名> --yes               # 非交互环境必须显式确认

wb-remove --list-trash               # 查看回收站内容（含昵称、UID、大小）
wb-remove --restore <文件名>         # 从回收站恢复某个备份

wb-remove --yes -- -weird            # `--` 之后的参数一律当作别名，用于 - 开头的账号名
```

等价写法：`workbuddy remove`、`workbuddy delete`、`workbuddy rm`、`workbuddy del`、`workbuddy-remove`。
注意 `remove` / `delete` / `rm` / `del` 过去会被当作账号名去匹配 Profile，现在优先按命令解析；
若恰好有同名账号且未给目标，会提示改用 `wb-switch`。

参数校验是严格的：**未知选项会直接报错，多个目标也会报错**，都不会执行任何删除。
（早期版本会把不认识的选项静默丢弃，`remove alpha --dry-run` 会真的删掉 alpha。）

删除的安全性设计：

- **默认软删除**：文件移入 `auth_profiles/.trash/`，用 `--list-trash` 查看、`--restore` 还原
- **默认拒绝删除当前活跃账号**：它是当前唯一可用的登录态备份，删掉只能重新扫码；确需删除要显式 `--force`
- **身份无法确认时拒绝**：凭据文件损坏、`account` 为空或结构异常、目标条目读不出 UID —— 这些情况无法证明"不是活跃账号"，一律拒绝，需 `--force` 才放行
- **交互式终端二次确认**；非交互环境（脚本、定时任务）必须带 `--yes`
- **并发保护**：删除期间持有 `auth_profiles/.remove.lock`，拿不到锁直接失败，不会降级为无锁执行
- **删除墓碑**：被删账号的 UID 记录在 `auth_profiles/.removed.json`，`wb-checkin` 的自动发现会跳过它，
  否则"当前登录账号"会被自动重新入库、删除等于没删。用 `wb-login` 或 `wb-save` 重新保存该账号即解除标记
- 删除最后一个账号时会额外提示「此后本地没有任何账号备份」
- 失败时退出码为 `1`，便于脚本判断

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