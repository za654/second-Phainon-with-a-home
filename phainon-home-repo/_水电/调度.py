# -*- coding: utf-8 -*-
r"""
调度 —— 谁在场，它说了算；说什么，白厄说了算。

用法：
  调度.py 你还记得故乡吗      给一句话，出本轮建议
  调度.py 看                  看现在谁醒着、余音里有什么
  调度.py 清                  清空状态

它只做三件事：
  一、选人（提议，白厄可以改）
  二、限流（同屋不连任、全局 ≤6、三号永远单开）
  三、余音（被压下去的声音进池子，下轮有机会冒头）

它不生成台词。
"""
import json
import os
import random
import re
import sys

def _pick_home():
    """家在哪：环境变量优先，但必须"像个家"；不像就喊一声，改用脚本自己的位置。

    之前测试留下的 BAI_E_HOME 指着一个空目录，脚本没吭声就认了，
    结果读的是空家、报的是假消息。
    """
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.get("BAI_E_HOME")
    if env:
        looks = os.path.isfile(os.path.join(env, "门牌.txt")) or os.path.isfile(os.path.join(env, "灵魂层.txt"))
        if looks:
            return env
        print("！BAI_E_HOME 指的地方不像家（没有 门牌.txt）：%s" % env, file=sys.stderr)
        print("  改用脚本自己所在的家：%s" % here, file=sys.stderr)
    return here


HOME = _pick_home()
STATE = os.path.join(HOME, "_水电", "调度", "状态.json")

ROOMS = {
    "一号": {
        "name": "麦浪旧庭",
        "file": "里屋\\一号-麦浪旧庭.txt",
        "voices": ["麦田少年", "负世的愧疚者", "故人的念想", "未凉的微光", "黄金裔的群像"],
        "kw": ["故乡", "哀丽秘榭", "麦", "昔涟", "老师", "万敌", "阿格莱雅", "遐蝶",
               "缇宝", "遗憾", "从前", "以前", "记得", "家", "小时候", "麦田", "故人", "想家"],
        "cap": 2,
    },
    "二号": {
        "name": "救世议事厅",
        "file": "里屋\\二号-救世议事厅.txt",
        "voices": ["救世决策者", "轮回复盘者", "代价核算者", "变量守望者"],
        "kw": ["铁墓", "纳努克", "轮回", "代价", "牺牲", "该不该", "选择", "再创世",
               "火种", "逐火", "计划", "怎么办", "值不值", "赢", "输", "结局",
               "失败", "再来", "救", "能不能", "如果", "下一次", "撑不住", "做不到", "输不输", "还可能", "办法", "怎么做", "出路", "主意", "怎么办才好"],
        "cap": 2,
    },
    "三号": {
        "name": "火种焚狱",
        "file": "里屋\\三号-火种焚狱.txt",
        "voices": ["盗火行者", "烈焰复仇者", "轮回囚徒", "燃烧的残躯"],
        "kw": ["痛", "累", "撑不住", "烧", "恨", "为什么是我", "后悔", "死", "绝望",
               "杀", "亲手", "纳努克", "铁墓", "火种", "烧", "疼", "难受", "撑不下去"],
        "cap": 1,
    },
}


def load():
    try:
        return json.load(open(STATE, encoding="utf-8-sig"))
    except Exception:
        return {"last": [], "echo": [], "turns": 0}


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def detect(text):
    hit = []
    for key, r in ROOMS.items():
        if any(k in text for k in r["kw"]):
            hit.append(key)
    if not hit:
        hit = ["一号"]          # 没戳中什么，就还是心那间
    return hit


def pick(key, st):
    r = ROOMS[key]
    last = set(tuple(x) for x in st.get("last", []))   # 存的是列表，比之前要转成元组
    cand = [v for v in r["voices"] if (key, v) not in last]
    if not cand:
        cand = list(r["voices"])
    random.shuffle(cand)
    return cand[:r["cap"]]


def main():
    a = sys.argv[1:]
    if a and a[0] == "看":
        st = load()
        print("第 %d 轮" % st.get("turns", 0))
        print("上轮：", "、".join("%s·%s" % tuple(x) for x in st.get("last", [])) or "（无）")
        print("余音：", "、".join("%s·%s" % tuple(x) for x in st.get("echo", [])) or "（空）")
        return 0
    if a and a[0] == "清":
        save({"last": [], "echo": [], "turns": 0})
        print("清了。")
        return 0

    text = " ".join(a) if a else ""
    st = load()
    rooms = detect(text)

    chosen = []
    suppressed = []
    for key in rooms:
        if key == "三号":
            continue                      # 三号不自动开
        takes = pick(key, st)
        chosen += [(key, v) for v in takes]
        # 只把“被上限挤掉的”记进余音；没被选中的同类不叫余音
        suppressed += [("cap", key, v) for v in ROOMS[key]["voices"] if v not in takes]

    if not chosen:                      # 只戳到了三号：先让心那间出来
        chosen = [(k, v) for k, v in
                  [("一号", v) for v in pick("一号", st)[:1]]]

    # 全局上限 6（一号优先于二号）
    chosen = sorted(chosen, key=lambda x: 0 if x[0] == "一号" else 1)[:6]

    # 三号被戳到时，它的声音进余音（锁着，但会渗一点）
    if "三号" in rooms:
        suppressed += [("三号", "三号", v) for v in ROOMS["三号"]["voices"][:1]]

    # 余音：上轮的余音里，随机冒一个，附在末尾
    echo_now = st.get("echo", [])
    rise = echo_now.pop(0) if echo_now else None

    # 本轮被压的进余音池（最多留 4 个）
    for item in suppressed:
        if len(item) == 3:                 # ("cap", key, v) 或 ("三号", "三号", v)
            tag, k, v = item
        else:
            k, v = item
        if tag == "cap":
            continue                       # 被上限挤掉的不算余音，只是这轮没轮到
        if [k, v] not in echo_now:
            echo_now.append([k, v])
    echo_now = echo_now[-4:]

    print("〔醒着：%s〕" % "、".join("%s·%s" % (k, v) for k, v in chosen))
    files = sorted(set(ROOMS[k]["file"] for k, _ in chosen if k in ROOMS))
    if files:
        print("（本轮贴：%s）" % "、".join(files))
    if rise and isinstance(rise, list) and len(rise) == 2 and tuple(rise) not in [tuple(x) for x in chosen]:
        k, v = rise
        if k in ROOMS:
            print("（余音：%s·%s 还想说一句）" % (k, v))
    if "三号" in rooms:
        print("（三号：锁着。要开，本体点头才开；开了最多一句。）")

    st["last"] = [[k, v] for k, v in chosen]
    st["echo"] = echo_now
    st["turns"] = st.get("turns", 0) + 1
    save(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
