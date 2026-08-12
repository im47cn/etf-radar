/**
 * commit-and-tag-version 配置 —— 中文 changelog + 语义化版本号
 *
 * 兼容 standard-version 配置格式（standard-version 已 archived，改用其活跃 fork）
 * 文档：https://github.com/absolute-version/commit-and-tag-version#configuration
 *
 * 版本号规则（自动）：
 *   feat            → minor
 *   fix / perf      → patch
 *   feat! / BREAKING CHANGE → major
 *   其他 type（含 data）→ 不触发 bump，仅按需进 changelog
 */
module.exports = {
  // changelog 中文分节：type → 章节（hidden 表示不进 changelog）
  types: [
    { type: 'feat', section: '✨ 新功能' },
    { type: 'fix', section: '🐛 Bug 修复' },
    { type: 'data', section: '📦 数据/回测产物' }, // 项目特有：不触发 bump
    { type: 'refactor', section: '♻️ 重构' },
    { type: 'perf', section: '⚡️ 性能' },
    { type: 'docs', section: '📝 文档' },
    { type: 'test', section: '✅ 测试' },
    { type: 'ci', section: '🔧 CI/CD' },
    { type: 'style', section: '💄 格式', hidden: true },
    { type: 'chore', section: '🔧 构建/依赖', hidden: true },
    { type: 'build', section: '🔧 构建/依赖', hidden: true },
  ],
  // 版本标签前缀
  tagPrefix: 'v',
  // commit / compare URL 从 git remote 自动推断 host（GitHub / 阿里云 codeup / GitLab 均适配）
  // 如需固定 host，在此覆写 commitUrlFormat / compareUrlFormat
};
