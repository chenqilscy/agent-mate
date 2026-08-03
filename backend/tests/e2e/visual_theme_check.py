"""U 系列视觉 / 主题验收骨架 (U-01~U-04)。

UI 层无法纯断言「视觉」，本骨架用 Playwright 驱动真实浏览器做「可观测」的自动检查，
对应功能验收清单里的 U 系列：

  U-01 明暗双主题：切换 body.dark 后，关键组件不得出现「文字色与背景色相同或都接近
       极端色」（白底白字 / 深底深字坑 WB-004/008）。本项目反复踩此坑，务必双主题核对。
  U-02 视觉零重设计：仅做结构性存在性断言（不校验像素）；具体 class 需对齐
       src/styles/{tokens,app}.css 与腾讯 WorkBuddy 参考原型。
  U-03 窄宽抽屉：viewport ≤900px 下关键布局容器仍可见（抽屉/响应式）。
  U-04 平台抽象：在 web 环境运行（不 import Tauri），本脚本即 web 路径验证。

前置（本机一次性）：
  pip install playwright && playwright install chromium
  pnpm install
  pnpm dev            # 前端 :8102 代理 /api → 后端 :8101（需后端已起）
运行：
  python backend/tests/e2e/visual_theme_check.py
  # 或 pytest backend/tests/e2e/visual_theme_check.py
"""
from __future__ import annotations

import os
import re
import sys
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.stderr.write("Playwright 未安装：pip install playwright && playwright install chromium\n")
    raise

BASE_URL = os.getenv("AGENTMATE_WEB_URL", "http://localhost:8102")

SELECTORS = {
    "app_shell": ".shell",
    "sidebar": ".sidebar",
    "main": ".main",
    "page": ".agentmate-page-container",
}
# 需要做「明暗对比」检查的组件（避免白底白字 / 深底深字）。
CONTRAST_CHECK_SELECTORS = [".sidebar", ".main"]


def _luminance(rgb: str) -> float:
    """简单相对亮度(0~1)，用于判断文字与背景是否接近同色/极端色。"""
    nums = re.findall(r"[\d.]+", rgb)
    if len(nums) < 3:
        return -1.0
    r, g, b = (float(x) for x in nums[:3])

    def lin(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


class VisualThemeCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page(viewport={"width": 1280, "height": 900})
        cls.page.goto(BASE_URL, wait_until="networkidle")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.pw.stop()

    def _visible(self, selector: str) -> bool:
        try:
            self.page.wait_for_selector(selector, timeout=5000, state="visible")
            return True
        except Exception:
            return False

    # ---- U-02 结构性存在性 ------------------------------------------- #
    def test_key_components_present(self) -> None:
        for name, sel in SELECTORS.items():
            self.assertTrue(self._visible(sel), f"缺失组件: {name} ({sel}) — 请对齐真实选择器")

    # ---- U-01 明暗双主题对比 ----------------------------------------- #
    def test_no_invisible_text_in_light(self) -> None:
        self._check_contrast("light")

    def test_no_invisible_text_in_dark(self) -> None:
        self.page.evaluate("document.body.classList.add('dark')")
        try:
            self._check_contrast("dark")
        finally:
            self.page.evaluate("document.body.classList.remove('dark')")

    def _check_contrast(self, theme: str) -> None:
        for sel in CONTRAST_CHECK_SELECTORS:
            if not self._visible(sel):
                continue
            color, bg = self.page.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return ["", ""];
                    const cs = getComputedStyle(el);
                    return [cs.color, cs.backgroundColor];
                }""",
                sel,
            )
            lc, lb = _luminance(color), _luminance(bg)
            msg = f"{theme}: {sel} color={color} bg={bg} 疑似白底白字/深底深字(WB-004/008)"
            self.assertFalse(lc < 0 or lb < 0, f"无法解析样式 {sel}")
            # 文字与背景亮度差过小 → 不可读
            self.assertGreater(abs(lc - lb), 0.05, msg)

    # ---- U-03 窄宽抽屉 ----------------------------------------------- #
    def test_narrow_drawer_layout(self) -> None:
        self.page.set_viewport_size({"width": 900, "height": 800})
        self.assertTrue(self._visible(SELECTORS["app_shell"]), "窄宽下布局容器不可见")
        self.assertTrue(self._visible(".shell-nav-toggle"), "窄宽下侧栏恢复入口不可见")
        self.page.set_viewport_size({"width": 1280, "height": 900})


if __name__ == "__main__":
    unittest.main()
