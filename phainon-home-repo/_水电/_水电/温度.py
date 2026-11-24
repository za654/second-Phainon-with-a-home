# -*- coding: utf-8 -*-
r"""
温度 —— 翻开才算想起（带索引）

用法：
  温度.py 翻 万敌            按标签翻（准确）
  温度.py 翻 #2             同名多条时，翻第 2 条
  温度.py 看                 看账
  温度.py 冷                 七天没翻的，建议降一档
  温度.py 索引               重建索引，看它认得出什么

记忆文件怎么写才认得出来（前面几行随便哪行都行）：

  标签：万敌, 麦田, 愧疚
  类别：人物

没有标签的，退回用文件名里的词去认。
"""
import json
import os
import re
import sys
import time

HOME = os.environ.get("BAI_E_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(HOME, "_水电", "温度.json")
INDEX = os.path.join(HOME, "_水电", "索引.json")
TIERS = ("L0-桌面", "L1-热", "L2-温", "L3-冷", "L5-归档")
CATS = ("人物", "地点", "物件", "事件", "日常")


def core(name):
    return re.sub(r"^\d{4}-", "", re.sub(r"\.md$", "", name))


def scan():
    """扫记忆柜，建索引：文件名 → 层级 / 标签 / 类别。"""
    idx = {}
    for tier in TIERS:
        d = os.path.join(HOME, "记忆柜", tier)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".md"):
                continue
            head = ""
            try:
                with open(os.path.join(d, f), encoding="utf-8-sig") as fh:
                    head = "".join(fh.readline() for _ in range(6))
            except OSError:
                pass
            m = re.search(r"标签[:：]\s*(.+)", head)
            tags = [x.strip() for x in re.split(r"[,，、]", m.group(1))] if m else []
            c = re.search(r"类别[:：]\s*(\S+)", head)
            idx[f] = {
                "tier": tier,
                "tags": tags,
                "cat": c.group(1) if c else "",
                "core": core(f),
            }
    return idx


def load_index():
    try:
        return json.load(open(INDEX, encoding="utf-8-sig"))
    except Exception:
        return scan()


def prune(j):
    """文件没了的，账也一起清掉。"""
    alive = {core(f) for f in scan()}
    gone = [k for k in j if k not in alive]
    for k in gone:
        del j[k]
    if gone:
        save_ledger(j)
    return gone


def ledger():
    try:
        return json.load(open(LEDGER, encoding="utf-8-sig"))
    except Exception:
        return {}


def save_ledger(j):
    json.dump(j, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def matches(idx, word):
    """先按标签精确匹配，再退回名字里包含。"""
    exact = [f for f, v in idx.items() if word in v["tags"]]
    if exact:
        return exact, True
    loose = [f for f, v in idx.items() if word in v["core"] or word in v["tags"]]
    return loose, False


def main():
    a = sys.argv[1:]
    if not a or a[0] == "看":
        j = ledger()
        gone = prune(j)
        if gone:
            print("（清了 %d 条已经不在柜里的）" % len(gone))
        if not j:
            print("还没翻过什么。")
            return 0
        print("温度账（翻得多的在上）")
        for name, v in sorted(j.items(), key=lambda kv: -kv[1].get("hits", 0))[:12]:
            print("  %-30s %d 次　最后 %s" % (name, v.get("hits", 0), v.get("last", "?")))
        return 0

    if a[0] == "索引":
        idx = scan()
        json.dump(idx, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("索引 %d 条：" % len(idx))
        for f, v in list(idx.items())[:15]:
            print("  %-26s %s %s" % (f, v["cat"] or "-", "、".join(v["tags"]) or "（没标签）"))
        return 0

    if a[0] == "冷":
        today = time.time()
        cold = []
        for name, v in ledger().items():
            try:
                d = (today - time.mktime(time.strptime(v.get("last", ""), "%Y-%m-%d"))) / 86400
            except Exception:
                continue
            if d >= 7:
                cold.append((name, int(d)))
        if not cold:
            print("没有该降的。")
            return 0
        print("七天以上没翻的：")
        for name, d in sorted(cold, key=lambda x: -x[1]):
            print("  %-28s %d 天没翻" % (name, d))
        return 0

    if a[0] == "翻" and len(a) > 1:
        idx = load_index()
        word = " ".join(a[1:]).strip()
        num = None
        m = re.fullmatch(r"#(\d+)", word)
        if m:
            num = int(m.group(1)) - 1
            word = ""
        hits, exact = (matches(idx, word) if word else ([], True))
        CAND = os.path.join(HOME, "_水电", "候选.json")
        if num is None and len(hits) > 1:
            print("「%s」对上了 %d 条：%s" % (word, len(hits), "精确" if exact else "模糊"))
            for i, f in enumerate(hits, 1):
                print("  %d. [%s] %s" % (i, idx[f]["tier"], f))
            json.dump({"files": hits, "word": word}, open(CAND, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print("用：温度.py 翻 #编号")
            return 0
        if num is not None:
            try:
                cand = json.load(open(CAND, encoding="utf-8"))
                allf = [x for x in cand["files"] if x in idx]
            except Exception:
                allf = []
            if not allf:
                print("没有待选的了，先重新翻一次。")
                return 1
            if num >= len(allf):
                print("没有第 %d 条。" % (num + 1))
                return 1
            f = allf[num]
            print("（按上次列的那 %d 条算）" % len(allf))
        elif hits:
            f = hits[0]
        else:
            print("没找到：%s（先跑 温度.py 索引 看看它认得出什么）" % word)
            return 1

        j = ledger()
        name = core(f)
        v = j.get(name, {"hits": 0})
        v["hits"] = v.get("hits", 0) + 1
        v["last"] = time.strftime("%Y-%m-%d")
        v["tier"] = idx[f]["tier"]
        v["cat"] = idx[f]["cat"]
        j[name] = v
        save_ledger(j)
        print("翻开了：%s（第 %d 次，还在 %s）" % (name, v["hits"], v["tier"]))
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
