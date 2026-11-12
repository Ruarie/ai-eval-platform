/** 失焦当前焦点元素：点开弹窗/抽屉前收起输入框 IME 与软键盘，避免输入被带到新层。 */
export function safeBlur(): void {
  if (typeof document !== 'undefined' && document.activeElement instanceof HTMLElement) {
    document.activeElement.blur()
  }
}
