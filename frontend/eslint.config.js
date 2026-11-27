// ESLint 扁平配置（Vue 3 + TypeScript）
//
// 目标：建立前端静态检查门禁，拦截真实缺陷（未使用变量、可疑写法等）。
// 策略：首轮仅拦截 error 级问题；风格类与存量治理项（如显式 any）降为 warn，
// 渐进清理，避免一次性大范围改动。
import js from '@eslint/js'
import globals from 'globals'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    // 构建产物、依赖与测试脚手架不参与业务 lint
    ignores: ['dist/**', 'node_modules/**', 'tests/**', 'playwright-report/**', 'test-results/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
        // vite.config.js define 注入的构建常量（类型声明见 src/env.d.ts）
        __BUILD_VERSION__: 'readonly',
        __BUILD_TIME__: 'readonly',
      },
    },
    rules: {
      // 下划线前缀的未使用参数/变量视为有意保留
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // 存量显式 any 约 180 处：先告警，不阻塞门禁
      '@typescript-eslint/no-explicit-any': 'warn',
      // 单文件组件命名沿用现状（页面级组件非多词命名是项目既有约定）
      'vue/multi-word-component-names': 'off',
      // v-html 默认禁止：确需使用时须先转义/经 utils/sanitizeHtml 消毒，并逐行
      // `eslint-disable-next-line vue/no-v-html -- 原因` 说明为何安全。
      'vue/no-v-html': 'error',
      // 存量确认卡通过 prop 对象直接编辑表单（ConfirmCard 等）：降为告警，
      // 组件重构（本地副本 + emit）留待前端结构治理批次处理
      'vue/no-mutating-props': 'warn',
    },
  },
)
