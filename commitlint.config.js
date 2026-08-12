/**
 * commitlint 配置 —— commit message 规范校验
 *
 * 规则等级：2 = error（阻断提交）| 1 = warn（警告不阻断）| 0 = 关闭
 * 文档：https://commitlint.js.org/reference/rules.html
 *
 * 设计原则：适配本项目既有提交习惯
 *   - type 强制校验（含本项目特有的 data: 数据/回测产物提交）
 *   - scope / 长度 仅 warn，避免阻断中文 + 量化描述的长主题行
 *   - 触发：scripts/hooks/commit-msg
 */
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // ── type 必须在枚举内（强制）────────────────────────────────
    //    data 为本项目特有 type：数据/回测产物更新，历史占比较高，必须保留
    'type-enum': [
      2,
      'always',
      [
        'feat', 'fix', 'docs', 'style', 'refactor', 'test',
        'chore', 'ci', 'perf', 'build', 'revert',
        'data', // 项目特有：数据/回测/配置产物提交
      ],
    ],

    // ── scope 建议（warn，业务域靠 warn 放行，不阻断）────────────
    //    枚举来自历史提交统计，新增域时追加
    'scope-enum': [
      1,
      'always',
      [
        'backend', 'frontend', 'ui',
        'signals', 'evidence', 'temperature', 'portfolio', 'membership',
        'radar', 'gate', 'core',
        'ci', 'deps', 'lint', 'scripts', 'hooks', 'vite',
        'docs', 'test',
      ],
    ],

    // ── 长度规则（warn，中文 subject + 量化描述常超长，不阻断）────
    'subject-max-length': [1, 'always', 72],
    'header-max-length': [1, 'always', 120],

    // ── 关闭英文大小写规则（中文 subject 不适用）──────────────────
    'subject-case': [0],
    'type-case': [0],
    'scope-case': [0],

    // ── body / footer 前置空行（推荐）─────────────────────────────
    'body-leading-blank': [1, 'always'],
    'footer-leading-blank': [1, 'always'],
  },
};
