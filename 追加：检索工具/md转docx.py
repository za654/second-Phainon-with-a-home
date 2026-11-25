# -*- coding: utf-8 -*-
"""把仓库里的 md 转成 docx（标题 / 段落 / 表格 / 代码块 / 引用 / 列表）。

用法：
    python md转docx.py            转同目录所有 md（README 除外）
    python md转docx.py 模板         转指定目录
    python md转docx.py -r          连子目录一起转
    python md转docx.py 找东西      只转一篇

依赖：python-docx（pip install python-docx）
改完 md 跑一次就行，别手改 docx——下次再生成会被覆盖。
"""
import os
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor


def set_cn(run, name="宋体"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def add_code(doc, lines):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(12)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run("\n".join(lines))
    set_cn(r, "等线")
    r.font.size = Pt(9.5)


def add_table(doc, rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x or "-") for x in c)]
    if not cells:
        return
    n = max(len(r) for r in cells)
    t = doc.add_table(rows=0, cols=n)
    t.style = "Table Grid"
    for row in cells:
        cs = t.add_row().cells
        for i in range(n):
            cs[i].text = row[i] if i < len(row) else ""
            for p in cs[i].paragraphs:
                for r in p.runs:
                    set_cn(r)
                    r.font.size = Pt(10)


def md_to_docx(src, dst, title=None):
    lines = open(src, encoding="utf-8").read().splitlines()
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "宋体"
    st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i].rstrip())
                i += 1
            add_code(doc, buf)
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            add_table(doc, rows)
            continue

        if not line.strip():
            i += 1
            continue

        if line.startswith("# "):
            p = doc.add_paragraph()
            r = p.add_run(line[2:].strip())
            r.bold = True
            r.font.size = Pt(18)
            set_cn(r)
            i += 1
            continue

        if line.startswith("## "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            r = p.add_run(line[3:].strip())
            r.bold = True
            r.font.size = Pt(14)
            set_cn(r)
            i += 1
            continue

        if line.startswith("### "):
            p = doc.add_paragraph()
            r = p.add_run(line[4:].strip())
            r.bold = True
            r.font.size = Pt(12)
            set_cn(r)
            i += 1
            continue

        if line.strip() == "---":
            p = doc.add_paragraph()
            r = p.add_run("—" * 20)
            r.font.color.rgb = RGBColor(0xBB, 0xBB, 0xBB)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue

        if line.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            txt = line.lstrip("> ").strip()
            add_runs(p, txt)      # 引用里也可能有 **加粗** 和 `代码`
            for r in p.runs:
                r.italic = True
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\[\s?\]\s*", line):
            p = doc.add_paragraph(style="List Bullet")
            txt = re.sub(r"^\s*[-*]\s+", "", line)
            txt = re.sub(r"^\s*\[\s?\]\s*", "", txt)
            add_runs(p, txt)
            i += 1
            continue

        p = doc.add_paragraph()
        add_runs(p, line.strip())
        i += 1

    doc.save(dst)
    return dst


def add_runs(p, text):
    """处理 **加粗** 和 `代码`。"""
    parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2])
            r.bold = True
            set_cn(r)
        elif part.startswith("`") and part.endswith("`"):
            r = p.add_run(part[1:-1])
            set_cn(r, "等线")
            r.font.size = Pt(10)
        else:
            r = p.add_run(part)
            set_cn(r)


SKIP = {"README.md"}          # README 不用转，首页直接读 md


def collect_md(base, recursive=False, skip_readme=True):
    """找出要转的 md。默认只扫这一层；-r 连子目录一起。"""
    found = []
    if recursive:
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.endswith(".md") and not (skip_readme and fn in SKIP):
                    found.append(os.path.join(root, fn[:-3]))
    else:
        for fn in sorted(os.listdir(base)):
            if fn.endswith(".md") and not (skip_readme and fn in SKIP):
                found.append(os.path.join(base, fn[:-3]))
    return found


def convert_all(base=None, only=None, recursive=False):
    """把 md 转成 docx。

    默认只转脚本自己所在的那一层（README 除外）：
        python md转docx.py                 这一层
        python md转docx.py 模板             指定目录
        python md转docx.py -r              这一层 + 所有子目录
        python md转docx.py 找东西           只转这一篇
    """
    default_base = os.path.dirname(os.path.abspath(__file__))
    base = base or default_base
    items = []
    for path in collect_md(base, recursive=recursive,
                         skip_readme=(os.path.abspath(base) == default_base)):
        stem = os.path.basename(path)
        if only and stem not in only:
            continue
        items.append((path, stem))
    if not items:
        print("这个目录里没有可转的 md。")
        return 0
    for path, stem in items:
        try:
            md_to_docx(path + ".md", path + ".docx")
            print("生成:", os.path.relpath(path + ".docx", base))
        except Exception as exc:      # noqa: BLE001
            print("跳过 %s：%s" % (stem, exc))
    return 0


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    recursive = "-r" in args or "--recursive" in args
    args = [a for a in args if a not in ("-r", "--recursive")]
    dirs = [a for a in args if os.path.isdir(a)]
    names = [a for a in args if not os.path.isdir(a)]
    sys.exit(convert_all(base=dirs[0] if dirs else None,
                         only=set(names) or None,
                         recursive=recursive))