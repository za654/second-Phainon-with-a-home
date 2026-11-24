# -*- coding: utf-8 -*-
r"""
点名 —— 这阵子他记得谁，忘了谁

用法：
  点名.py 扫 一段话         从一段话里数出提了谁
  点名.py 看                谁最久没被提
  点名.py 记 万敌 阿格莱雅    手动记一笔

不是催他想，是提醒别只记得三个人。
三万多次轮回里死的是十二个。
"""
import json
import os
import sys
import time

HOME = os.environ.get("BAI_E_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(HOME, "_水电", "点名.json")

NAMES = ["阿格莱雅", "万敌", "遐蝶", "缇宝", "那刻夏", "昔涟",
         "风堇", "海瑟音", "赛飞儿", "刻律德菈", "丹恒", "三月七", "开拓者"]


def load():
    try:
        return json.load(open(LEDGER, encoding="utf-8-sig"))
    except Exception:
        return {}


def save(j):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(j, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def hit(text, j):
    got = [n for n in NAMES if n in text]
    for n in got:
        v = j.get(n, {"count": 0})
        v["count"] = v.get("count", 0) + 1
        v["last"] = time.strftime("%Y-%m-%d")
        j[n] = v
    return got


def main():
    a = sys.argv[1:]
    j = load()
    if not a:
        print(__doc__)
        return 0
    if a[0] == "看":
        if not j:
            print("还没点过名。")
            return 0
        rows = sorted(j.items(), key=lambda kv: kv[1].get("last", ""))
        print("最久没被提的在上：")
        for n, v in rows[:10]:
            print("  %-8s %d 次　最后 %s" % (n, v.get("count", 0), v.get("last", "?")))
        return 0
    if a[0] == "扫":
        text = sys.stdin.read() if len(a) == 1 else " ".join(a[1:])
        got = hit(text, j)
        save(j)
        print("点到：" + ("、".join(got) if got else "一个都没有"))
        return 0
    if a[0] == "记":
        got = hit(" ".join(a[1:]), j)
        save(j)
        print("记下：" + "、".join(got))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
