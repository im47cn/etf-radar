import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // 数据 URL 集中门禁 (2026-09-27 审查裁决): fetch 的 URL 禁止硬编码
      // /data/ 前缀或裸 /latest /snapshots 路径 —— vite publicDir 平铺结构下
      // 会生产 404 静默失效, 而 MSW 通配掩盖使单测全绿 (useEventsSnapshot
      // 实例, 失效近 3 个月未察觉)。必须走 @/lib/dataUrls 导出的构造。
      'no-restricted-syntax': ['error',
        {
          selector: "CallExpression[callee.name='fetch'] Literal[value=/data/]",
          message: 'fetch URL 禁止含 /data/ 前缀: publicDir 平铺结构下生产 404。用 @/lib/dataUrls。',
        },
        {
          selector: "CallExpression[callee.name='fetch'] TemplateLiteral",
          message: 'fetch URL 禁止模板字符串直拼数据路径: 绕过 dataUrls 集中构造, 前缀错配不可测。用 @/lib/dataUrls 导出 (如 snapshotFileUrl/stockOhlcUrl)。',
        },
        {
          selector: "CallExpression[callee.name='fetch'] Literal[value=/^\\/(latest|snapshots|stocks|holdings)\\//]",
          message: 'fetch URL 禁止硬编码数据路径字面量: BASE 前缀错配不可测。用 @/lib/dataUrls 导出。',
        },
      ],
    },
  },
])
