#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量修复 Gen2 Tech 网站导航栏换行/溢出问题。

用法：
    python3 fix_navlinks.py

要求：
    与本脚本放在同一目录下的以下 HTML 文件会被就地修改（自动生成 .bak 备份）：
    about.html, services.html, products.html, products-gallery.html,
    customers.html, certifications.html, contact.html, join-us.html,
    index.html （如果存在也会一并处理，因为它复用同一套 Header 样式）
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
# 1) 桌面端 .navlinks 规则：原始 -> 新
# ---------------------------------------------------------------------------
OLD_NAVLINKS = (
    "  .navlinks{display:flex;gap:26px;font-size:14px;color:var(--text-dim);}\n"
)

NEW_NAVLINKS = (
    "  .navlinks{\n"
    "    display:flex;\n"
    "    flex:1 1 auto;\n"
    "    min-width:0;\n"
    "    flex-wrap:nowrap;\n"
    "    white-space:nowrap;\n"
    "    overflow-x:auto;\n"
    "    overflow-y:hidden;\n"
    "    -webkit-overflow-scrolling:touch;\n"
    "    scrollbar-width:none;\n"
    "    -ms-overflow-style:none;\n"
    "    gap:26px;\n"
    "    font-size:14px;\n"
    "    color:var(--text-dim);\n"
    "  }\n"
    "  .navlinks::-webkit-scrollbar{display:none;}\n"
    "  .navlinks a{flex:0 0 auto;}\n"
)

# ---------------------------------------------------------------------------
# 2) .nav-right：防止被压缩（保持右侧语言切换 + 汉堡按钮宽度固定）
# ---------------------------------------------------------------------------
OLD_NAV_RIGHT = (
    "  .nav-right{display:flex;align-items:center;gap:16px;}\n"
)

NEW_NAV_RIGHT = (
    "  .nav-right{display:flex;align-items:center;gap:16px;flex:none;}\n"
)

# ---------------------------------------------------------------------------
# 3) 移动端 (<=860px) .navlinks 规则：追加"重置"声明，
#    抵消桌面端新增的 overflow-x/white-space/min-width/flex 等属性，
#    确保汉堡菜单展开面板的样式与逻辑完全不变。
# ---------------------------------------------------------------------------
OLD_MOBILE_NAVLINKS = (
    "    .navlinks{\n"
    "      display:none;flex-direction:column;gap:0;\n"
    "      position:absolute;top:100%;left:0;right:0;\n"
    "      background:var(--surface);border-top:1px solid var(--line);\n"
    "      box-shadow:0 16px 32px -18px rgba(32,36,43,0.28);\n"
    "      padding:6px 0;z-index:40;\n"
    "    }\n"
)

NEW_MOBILE_NAVLINKS = (
    "    .navlinks{\n"
    "      display:none;flex-direction:column;gap:0;\n"
    "      position:absolute;top:100%;left:0;right:0;\n"
    "      background:var(--surface);border-top:1px solid var(--line);\n"
    "      box-shadow:0 16px 32px -18px rgba(32,36,43,0.28);\n"
    "      padding:6px 0;z-index:40;\n"
    "      /* 重置桌面端为了防止换行/溢出而新增的属性，\n"
    "         移动端汉堡菜单展开面板的外观与行为保持原样 */\n"
    "      flex:none;min-width:auto;white-space:normal;\n"
    "      overflow-x:visible;overflow-y:visible;\n"
    "    }\n"
)

# ---------------------------------------------------------------------------
# 4)（第二轮修复）桌面端横向滚动容器右侧留白缓冲，避免最后一个链接
#    （及带 active 高亮图标、文字加粗后变宽的链接）紧贴容器右边缘。
# ---------------------------------------------------------------------------
OLD_SCROLLBAR_HIDE = (
    "  .navlinks::-webkit-scrollbar{display:none;}\n"
    "  .navlinks a{flex:0 0 auto;}\n"
)

NEW_SCROLLBAR_HIDE = (
    "  .navlinks::-webkit-scrollbar{display:none;}\n"
    "  .navlinks a{flex:0 0 auto;}\n"
    "  .navlinks::after{content:'';flex:0 0 4px;}\n"
)

# ---------------------------------------------------------------------------
# 5)（第二轮修复）JS：当前页面的 active 链接在横向滚动容器里可能被
#    滚动到可视区域之外（尤其是最后一个 "Join Us" 链接，激活时因为
#    多了图标+加粗而变宽，默认 scrollLeft=0 时其文字尾部会被裁切，
#    表现为只能看到 "Join U"）。在打上 active class 后自动把它滚动
#    进可视范围内。
# ---------------------------------------------------------------------------
OLD_ACTIVE_JS = (
    "    links.forEach(function(link){\n"
    "      var linkFile = (link.getAttribute('href') || '').split('/').pop();\n"
    "      if(linkFile === currentFile){\n"
    "        link.classList.add('active');\n"
    "      }\n"
    "    });\n"
    "  })();\n"
)

NEW_ACTIVE_JS = (
    "    links.forEach(function(link){\n"
    "      var linkFile = (link.getAttribute('href') || '').split('/').pop();\n"
    "      if(linkFile === currentFile){\n"
    "        link.classList.add('active');\n"
    "        // 确保当前页面对应的高亮链接（如加了图标后变宽的 \"Join Us\"）\n"
    "        // 不会被横向滚动容器的默认滚动位置裁掉，自动滚入可视区域\n"
    "        if(typeof link.scrollIntoView === 'function'){\n"
    "          link.scrollIntoView({inline:'nearest', block:'nearest'});\n"
    "        }\n"
    "      }\n"
    "    });\n"
    "  })();\n"
)


def patch_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    report = []

    if OLD_NAVLINKS in text:
        text = text.replace(OLD_NAVLINKS, NEW_NAVLINKS, 1)
        report.append("desktop .navlinks OK")
    else:
        report.append("!! desktop .navlinks NOT FOUND (skipped)")

    if OLD_NAV_RIGHT in text:
        text = text.replace(OLD_NAV_RIGHT, NEW_NAV_RIGHT, 1)
        report.append(".nav-right OK")
    else:
        report.append("!! .nav-right NOT FOUND (skipped)")

    if OLD_MOBILE_NAVLINKS in text:
        text = text.replace(OLD_MOBILE_NAVLINKS, NEW_MOBILE_NAVLINKS, 1)
        report.append("mobile .navlinks OK")
    else:
        report.append("!! mobile .navlinks NOT FOUND (skipped)")

    if OLD_SCROLLBAR_HIDE in text:
        text = text.replace(OLD_SCROLLBAR_HIDE, NEW_SCROLLBAR_HIDE, 1)
        report.append("scroll buffer OK")
    else:
        report.append("!! scroll buffer NOT FOUND (skipped)")

    if OLD_ACTIVE_JS in text:
        text = text.replace(OLD_ACTIVE_JS, NEW_ACTIVE_JS, 1)
        report.append("active scrollIntoView JS OK")
    else:
        report.append("!! active scrollIntoView JS NOT FOUND (skipped)")

    # 备份原文件
    backup = path.with_suffix(path.suffix + ".bak")
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
