# 提交与发布工作流

本项目已集成 **commitlint**（提交信息校验）+ **commit-and-tag-version**（语义化版本与中文 CHANGELOG）。
本文档为日常速查，配置见根目录 `commitlint.config.js` / `.versionrc.js`。

---

## 1. 提交信息规范

格式：`type(scope): 主题行`，由 `commit-msg` hook 自动校验。

### type（强制，违反则阻断提交）

| type | 含义 | 版本影响 |
|---|---|---|
| `feat` | 新功能 | minor |
| `fix` | Bug 修复 | patch |
| `perf` | 性能优化 | patch |
| `refactor` | 重构（不改行为） | 不 bump |
| `docs` | 文档 | 不 bump |
| `test` | 测试 | 不 bump |
| `ci` | CI/CD | 不 bump |
| `chore` | 构建/依赖/工程 | 不 bump |
| `style` | 格式 | 不 bump |
| `build` | 构建 | 不 bump |
| `revert` | 回退 | 不 bump |
| `data` | **数据/回测产物更新**（本项目特有） | 不 bump |

### scope（warn，仅警告不阻断）

建议从以下取值：`backend` `frontend` `ui` `signals` `evidence` `temperature` `portfolio` `membership` `radar` `gate` `core` `ci` `deps` `lint` `scripts` `hooks` `vite` `docs` `test`。新增业务域时同步追加到 `commitlint.config.js`。

### 其他规则

- `subject-max-length`：72（warn，中文主题行常超长，仅警告）
- `header-max-length`：120（warn）
- 关闭英文大小写校验（中文适用）
- `feat!:` 或 body 里 `BREAKING CHANGE:` → 触发 major bump

### 示例

```
feat(signals): 共振信号方向化
fix(evidence): ljung_box 改 chi2.sf 根治 p 值下溢
data(temperature): 校准温度系数 2026-08-12
docs: 精简 v1.1.0 CHANGELOG
```

---

## 2. 日常提交

`commit-msg` hook（`scripts/hooks/commit-msg`）会在每次 `git commit` 自动校验，非法 type 直接阻断。

```bash
git commit -m "feat(signals): 新增共振检测"      # 合法 → 通过
git commit -m "wip: 临时提交"                    # 非法 type → 阻断
```

**紧急绕过**（仅在特殊情况下使用）：

```bash
git commit --no-verify -m "..."
```

---

## 3. 语义化版本发布

发布三步：预览 → 发布 → 推送。

```bash
# 1. 预览：bump 到哪个版本、CHANGELOG 会生成什么（不写文件、不打 tag）
npm run release:dry

# 2. 正式发布：bump package.json + 写 CHANGELOG.md + 创建 release commit + 打 v* tag
npm run release

# 3. 推送 commit 与 tag
git push --follow-tags
```

### 版本号规则（自动）

- `feat` → minor（如 `1.1.0 → 1.2.0`）
- `fix` / `perf` → patch（如 `1.1.0 → 1.1.1`）
- `feat!` / `BREAKING CHANGE` → major（如 `1.1.0 → 2.0.0`）
- 其他 type（含 `data`）→ 不触发版本升级

### 当前版本基线

- `v0.1.0`（2026-06-15，MVP）
- `v1.1.0`（2026-08-12，首个语义化版本，含 v0.1.0 之后历史）

---

## 4. CHANGELOG 维护

- 每次 `npm run release` 自动**追加**新版本段落，不会覆盖已有内容
- CHANGELOG 按 type 中文分节：`✨ 新功能` / `🐛 Bug 修复` / `♻️ 重构` / `⚡️ 性能` / `📝 文档` / `✅ 测试` / `🔧 CI/CD`
- `data` / `style` / `chore` / `build` 默认不进 CHANGELOG（`.versionrc.js` 中 `hidden: true` 或不入 types）
- **手工精简**：可直接编辑 `CHANGELOG.md` 删除噪音条目（如曾删除 v1.1.0 的 363 条 data 记录），不影响后续自动生成

---

## 5. 文件索引

| 文件 | 作用 |
|---|---|
| `commitlint.config.js` | commitlint 规则（type/scope/长度） |
| `.versionrc.js` | commit-and-tag-version 配置（中文分节、版本规则） |
| `package.json` | 版本号 + `release` / `release:dry` 脚本 |
| `scripts/hooks/commit-msg` | commit-msg 钩子（触发 commitlint） |
| `CHANGELOG.md` | 变更记录（自动生成 + 可手工精简） |

---

## 6. 常见问题

**Q: push 时 pre-push hook 跑很久？**
A: 该 hook 做 mypy/tsc/diff-cover（变更行覆盖 ≥80%）。仅当本次提交含 `.py`/`.ts` 变更时才触发，纯文档/配置提交会自动跳过。

**Q: 忘了 type 写错了怎么办？**
A: 若尚未推送，`git commit --amend -m "正确的 message"`；若已推送，改正后 `git push --force-with-lease`（慎用）。

**Q: 不想某次提交触发版本升级？**
A: 用不触发 bump 的 type（如 `chore` / `refactor` / `data`），避免 `feat` / `fix`。
