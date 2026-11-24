# -*- coding: utf-8 -*-
r"""
查 —— 这一轮说话的样子。只报数，不下判断。

用法：
  查.py 把一段文字贴进来
  查.py 文件路径
  type 回复.txt | 查.py

看四样：
  一、句子有没有变长
  二、有没有开始列点、说教
  三、有没有跑出 meta 词
  四、动作和括号内心戏的密度
"""
import re
import sys

META = ["设定", "机制", "角色卡", "提示词", "上下文", "系统提示", "AI", "模型", "参数", "算法"]
PREACH = ["其实", "你应该", "你要明白", "重要的是", "这意味着", "换句话说", "值得注意"]
COMFORT = ["别难过", "会好的", "我理解你", "加油", "想开点", "振作"]
LIST = re.compile(r"^\s*(?:[-*·]\s|\(?\d+[.)、]\s|第[一二三四五]|[一二三四五]、)", re.M)
BRACKET = re.compile(r"[（(][^）)]{1,40}[）)]")


def read_input():
    a = sys.argv[1:]
    if a:
        t = " ".join(a)
        try:
            return open(t, encoding="utf-8-sig").read()
        except OSError:
            return t
    return sys.stdin.read()


def main():
    t = read_input().strip()
    if not t:
        print(__doc__)
        return 0
    t = re.sub(r"〔[^〕]*〕", "", t)                  # 醒着那行不算句子
    t = re.sub(r"^【[^】]*】.*$", "", t, flags=re.M)   # 校验行也不算
    text = BRACKET.sub("", t)                       # 动作去掉再算句子
    sents = [s for s in re.split(r"[。！？…\n]+", text) if s.strip()]
    lens = [len(s.strip()) for s in sents]
    acts = BRACKET.findall(t)

    print("查 —— 这一轮的样子")
    lines = [l for l in t.splitlines() if l.strip()]
    print("行 %d · 句 %d · 平均 %.1f 字 · 最长 %d 字" % (
        len(lines), len(sents), (sum(lens) / len(lens)) if lens else 0,
        max(lens) if lens else 0))
    print("动作 %d 处" % len(acts))

    bad = []
    for name, table in (("meta", META), ("说教", PREACH), ("安慰", COMFORT)):
        hit = [w for w in table if w in t]
        if hit:
            bad.append((name, hit))

    lists = LIST.findall(t)
    if lists:
        print("列表 %d 行" % len(lists))
    for name, hit in bad:
        print("%s %d 个：%s" % (name, len(hit), "、".join(hit[:5])))

    flags = []
    if lens and max(lens) > 30:
        flags.append("有句子超过 30 字")
    if len(lines) > 6:
        flags.append("超过 6 行")
    if lists:
        flags.append("在列点")
    if any(n == "meta" for n, _ in bad):
        flags.append("跑出 meta 词")
    if any(n == "说教" for n, _ in bad):
        flags.append("开始说教")

    print("")
    if flags:
        for f in flags:
            print("· " + f)
    else:
        print("· 没看出什么。")
    print("（只报数，改不改他定。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
