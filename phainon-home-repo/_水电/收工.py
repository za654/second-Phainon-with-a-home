# -*- coding: utf-8 -*-
r"""
收工 —— 把这一轮落得下来的那一下，压成一条候选

用法：
  收工.py "他把石子放脚边，又捡回来" 物件 石子,河边
  收工.py 看                 看没有没收的候选
  收工.py 收 文件名           把候选取进 L0（点头）
  收工.py 删 文件名           不要了

规矩：
  · 只写 记忆柜\_候选\，不动 L0
  · 入柜要人点头
  · 一行就够。写多了包会重，写少了温度和点名没得烧。
"""
import os
import sys
import time

HOME = os.environ.get("BAI_E_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAND = os.path.join(HOME, "记忆柜", "_候选")
L0 = os.path.join(HOME, "记忆柜", "L0-桌面")
CATS = ("人物", "地点", "物件", "事件", "日常")


def main():
    a = sys.argv[1:]
    os.makedirs(CAND, exist_ok=True)

    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if a[0] == "看":
        fs = sorted([f for f in os.listdir(CAND) if f.endswith(".md")], reverse=True)
        if not fs:
            print("没有待审的。")
            return 0
        for f in fs:
            head = open(os.path.join(CAND, f), encoding="utf-8-sig").read().strip().splitlines()
            body = [l for l in head if l and not l.startswith(("标签", "类别"))]
            print("  %-30s %s" % (f, body[-1][:40] if body else ""))
        print("\n（收：收工.py 收 文件名 ；删：收工.py 删 文件名）")
        return 0

    if a[0] in ("收", "删") and len(a) > 1:
        name = a[1]
        p = os.path.join(CAND, name)
        if not os.path.exists(p):
            print("没有这个候选：%s" % name)
            return 1
        if a[0] == "删":
            os.remove(p)
            print("删了：%s" % name)
            return 0
        # 收：挪进 L0，日期前缀统一
        text = open(p, encoding="utf-8-sig").read()
        stamp = time.strftime("%m%d")
        dst = os.path.join(L0, "%s-%s" % (stamp, name.split("-", 1)[-1] if "-" in name else name))
        if os.path.exists(dst):
            dst = os.path.join(L0, "%s-%s" % (stamp, time.strftime("%H%M%S") + ".md"))
        os.replace(p, dst)
        print("收进去了：%s" % os.path.basename(dst))
        # 顺手重建索引
        try:
            import subprocess
            subprocess.run([sys.executable, "-X", "utf8",
                            os.path.join(HOME, "_水电", "温度.py"), "索引"],
                           capture_output=True, timeout=60)
        except Exception:
            pass
        return 0

    # 写一条候选
    line = a[0].strip()
    if not line:
        print("什么都没写。")
        return 1
    cat = ""
    tags = ""
    if len(a) > 1:
        if a[1] in CATS:
            cat = a[1]
            if len(a) > 2:
                tags = a[2]
        else:
            tags = a[1]

    stamp = time.strftime("%m%d-%H%M")
    body = "%s\n标签：%s\n类别：%s\n\n%s\n" % (
        "# 候选（待审）" + time.strftime(" %Y-%m-%d %H:%M"), tags, cat, line)
    name = "%s-%s.md" % (stamp, (tags.split(",")[0].strip() if tags else "一笔"))
    name = name.replace("/", "_").replace("\\", "_")
    p = os.path.join(CAND, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    print("候选写好了：%s" % name)
    print("（点头就：收工.py 收 %s）" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
