#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量为 Gen2 Tech 网站注入"翻书式"页面切换过渡动画（View Transitions API，
跨文档 / Cross-Document 版本），并保证 Header 导航栏在切换时保持固定
不参与旋转（仅做极淡的淡入淡出）。

用法：
    python3 add_view_transitions.py

要求：
    与本脚本放在同一目录下的以下 HTML 文件会被就地修改（自动生成 .bak 备份）：
    about.html, services.html, products.html, products-gallery.html,
    customers.html, certifications.html, contact.html, join-us.html,
    index.html
"""

import sys
from pathlib import Path

FILES = [
    "about.html",
    "services.html",
    "products.html",
    "products-gallery.html",
    "customers.html",
    "certifications.html",
    "contact.html",
    "join-us.html",
    "index.html",
]

# ---------------------------------------------------------------------------
# 1) 在 <head> 中插入 meta 开关（配合 CSS 的 @view-transition 一起生效，
#    双重保险：部分浏览器版本优先识别 meta，部分优先识别 CSS at-rule）
# ---------------------------------------------------------------------------
OLD_VIEWPORT = (
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
)

NEW_VIEWPORT = (
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '<meta name="view-transition" content="same-origin">\n'
)

# ---------------------------------------------------------------------------
# 2) 在 </style> 之前插入翻书过渡动画的 CSS。
#    核心思路：
#    - @view-transition { navigation: auto; } 开启跨文档过渡（CSS 方式）。
#    - header#top 单独指定 view-transition-name，使其拥有独立的过渡分组，
#      不会被下面的 root（页面主体）翻页动画影响，只做极淡的透明度渐变。
#    - ::view-transition-old(root) / ::view-transition-new(root) 覆盖默认
#      的交叉淡出/淡入，换成"旧页面左旋淡出 + 新页面右侧滑入淡入"的翻书效果。
# ---------------------------------------------------------------------------
CLOSE_PATTERN = "</style>\n</head><body>"

VIEW_TRANSITION_CSS = """
/* ============================================================
   翻书式页面切换过渡动画（View Transitions API - 跨文档版本）
   - Header 导航栏固定不动，仅做极淡的淡入淡出
   - 页面主体做"翻书"效果：旧页面左旋淡出，新页面右侧滑入淡入
   ============================================================ */
@view-transition {
  navigation: auto;
}

/* Header 独立成组，不参与下面的翻书动画，只做极淡的淡入淡出 */
header#top {
  view-transition-name: site-header;
  view-transition-class: site-header;
}

/* 页面主体（root）翻书动画时长与缓动 */
::view-transition-group(root) {
  animation-duration: 0.7s;
  animation-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
}

::view-transition-old(root) {
  animation: book-flip-out 0.7s cubic-bezier(0.4, 0, 0.2, 1) both;
  transform-origin: left center;
}

::view-transition-new(root) {
  animation: book-flip-in 0.7s cubic-bezier(0.4, 0, 0.2, 1) both;
  transform-origin: right center;
}

@keyframes book-flip-out {
  from {
    opacity: 1;
    transform: perspective(1400px) rotateY(0deg) translateX(0);
  }
  to {
    opacity: 0;
    transform: perspective(1400px) rotateY(-8deg) translateX(-3%);
  }
}

@keyframes book-flip-in {
  from {
    opacity: 0;
    transform: perspective(1400px) rotateY(8deg) translateX(3%);
  }
  to {
    opacity: 1;
    transform: perspective(1400px) rotateY(0deg) translateX(0);
  }
}

/* Header 分组：不使用翻书动画，只做极其细微的淡入淡出，绝无旋转/位移 */
::view-transition-group(site-header) {
  animation-duration: 0.25s;
  animation-timing-function: ease-in-out;
}

::view-transition-old(site-header),
::view-transition-new(site-header) {
  /* 覆盖默认的交叉淡出/淡入位移，保证 Header 完全静止 */
  height: 100%;
  transform: none !important;
  mix-blend-mode: normal;
}

::view-transition-old(site-header) {
  animation: header-fade-out 0.25s ease-in-out both;
}

::view-transition-new(site-header) {
  animation: header-fade-in 0.25s ease-in-out both;
}

@keyframes header-fade-out {
  from { opacity: 1; }
  to   { opacity: 0.92; }
}

@keyframes header-fade-in {
  from { opacity: 0.92; }
  to   { opacity: 1; }
}

/* 回滚开关：给 <html> 加上 class="no-view-transition" 即可一键禁用
   （见文末回滚说明），或直接删除本段 CSS 与上面的 meta 标签。 */
html.no-view-transition {
  view-transition-name: none;
}
html.no-view-transition header#top {
  view-transition-name: none;
}
"""

NEW_CLOSE_PATTERN = VIEW_TRANSITION_CSS + CLOSE_PATTERN


def patch_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    report = []

    if OLD_VIEWPORT in text:
        text = text.replace(OLD_VIEWPORT, NEW_VIEWPORT, 1)
        report.append("view-transition meta OK")
    else:
        report.append("!! viewport meta NOT FOUND (skipped)")

    if CLOSE_PATTERN in text:
        text = text.replace(CLOSE_PATTERN, NEW_CLOSE_PATTERN, 1)
        report.append("view-transition CSS OK")
    else:
        report.append("!! </style></head><body> pattern NOT FOUND (skipped)")

    if 'view-transition-name: site-header' in text:
        pass

    backup = path.with_suffix(path.suffix + ".bak2")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    path.write_text(text, encoding="utf-8")
    return " | ".join(report)


def main():
    base = Path(__file__).resolve().parent
    any_found = False
    for name in FILES:
        p = base / name
        if not p.exists():
            print(f"[skip] {name} 不存在")
            continue
        any_found = True
        result = patch_file(p)
        print(f"[ok]   {name}: {result}")

    if not any_found:
        print("未找到任何目标 HTML 文件，请确认脚本与 HTML 文件在同一目录下。")
        sys.exit(1)


if __name__ == "__main__":
    main()
