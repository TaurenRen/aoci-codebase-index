# 实测踩坑清单

全部来自 2026-10-09 在真实商用项目（微信小程序 + Node 后端）上的首建过程。

## 一、范围与基线

### 1. 项目不是 Git 仓库 → 直接卡死

AOCI 的认知对象是 Git 跟踪集合。非 git 项目先 `git init` + 首次提交。

### 2. 没有 .gitignore → 认知预算被打爆

实测：未规范时 init 预估全量索引 **618,570 tokens**；补了 Node 标准 .gitignore 后降到 **148,540**（差 4 倍）。
超过它自己的 `max_tokens=400000` 会直接不健康。

**必须排除的典型目录**：`node_modules/` `.venv/` `dist/` `build/` `coverage/` `uploads/` `logs/` `.env*`
以及 **AI 工具资产目录**（`.cursor/`、`.workbuddy/`、`.trae/`）——这类目录在现代项目里动辄几千个文件，
全是技能文档和 PDF，跟业务代码无关，却会被默认当成源码。

### 3. 改 `.aoci/config.json` 的 exclude_dirs 收窄范围 → 策略身份漂移

现象：Guide 卡在 `scope_change_required`，`policy_identity_aligned=false`，后续 maintain 全部 `repair_required`。

### 4. `scope rule add --action exclude` 大批排除 → 要求真人 TTY 确认

现象：

```
错误: 需要真人审批。…请精确输入：APPLY MANAGED SCOPE <plan-digest>
```

管道喂进去不算（`human_tty_digest_confirmation_required`）——必须是真实终端。
大批量移除条目超过 `entry_removal_percent=25` 就触发。

**正确做法**：从 git 源头排除，见下条。

### 5. 正道：让 Git 不管这些目录

```bash
printf ".cursor/\n.workbuddy/\ndocs/\n" >> .gitignore
git rm -r --cached .cursor .workbuddy docs -q     # 只移出索引，磁盘保留
git add -A && git commit -m "chore: 收敛仓库认知范围"
rm -rf .aoci aoci.txt aoci.meta.txt aoci.code.txt
aoci init --locale zh-CN
```

### 6. `scan --force` 在有 Managed Scope Baseline 后不被允许

```
错误: 已有Managed Scope Baseline不能通过scan --force重建；
      请使用scope preview/apply …
```

收窄范围要走 `scope activate`（它会走 preview/apply 事务），不要 `scan --force`。

## 二、条目被机器拒收（实测三轮收敛）

### 7. 标签插了分隔符 → `object_tag_dictionary_violation`

写 `FC3-T` 或 `CUT5T` 都被拒，cause：`D Trait value - is not declared by the current Meta dictionary`。
合法形态是 **4 位**：`FC3T`。

### 8. 模块位用了 `F` → `object_tag_dictionary_violation`

code 的 B 位字典没有 `F`。配置/声明类文件用 `C`（配置策略）。

### 9. S 超长 → `fras_s_too_long`

按重要性卡配额，别把"这个文件很重要"写进去。

### 10. A 项数超限 → `fras_a_too_many_items`

只留最稳定的对外契约，≤6 项。

### 11. 字段 token 超预算 → `entry_field_budget_exceeded`

token = UTF-8 字节/3。中文一个字 1 token，标点也算。

### 12. 建议：写自动修复循环

提交 → 解析 `findings` 里的 `expected`（形如 `max_runes=50` / `max_items=6` / `max_tokens=40`）
→ 裁对应字段 → 整批重交。实测 14 → 10 → 0，三轮收敛。

## 三、集成

### 13. MCP 配好不会自动生效

要**重启宿主**并在连接器里对新的 server 点「信任」；后台画布不渲染小程序卡片/视频组件，以手机预览为准。

### 14. 宿主没加载 MCP 也能调

用 stdio 起 `aoci mcp --repo <根>`，发 JSON-RPC：`initialize` → `notifications/initialized` → `tools/call`。
**`notifications/initialized` 不能省**，否则 `tools/call` 被拒。

### 15. 工具名与参数（rc19）

9 个工具：`aoci_get_entries` `aoci_header` `aoci_maintain` `aoci_overview` `aoci_remove_entry`
`aoci_report` `aoci_rules` `aoci_search` `aoci_update_entry`

`aoci_update_entry` 顶层：`code_batch_id`（= `maintain.code_plan.batch_id`）、`entries[]`；
每项：`path`、`source_sha256`、`candidate_id`、`new_entry`。
`code_batch_id` **绝不能**填 `authoring_batch.batch_identity`。

### 16. 许可别踩

上游 AOCI-CODE 是 **FSL-1.1-MIT**，不是 MIT/Apache：
允许使用、修改、内部部署；**禁止**把它做成竞争性产品/托管服务对外提供。
两年后自动转 MIT。写文章/做二次分发时要说清。
