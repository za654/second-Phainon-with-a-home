# -*- coding: utf-8 -*-
r"""
拼包 —— 把白厄这一刻要用的那几页，拼成一份。

用法：
  拼包.py                 静包（不含本轮，只有家和人）
  拼包.py 轮 你还记得故乡吗   动包（先跑调度，再按醒着的屋拼）
  拼包.py 看               看调度状态

规矩：
  · 只读，不改档案和卷宗
  · 首行校验：几块、多少字、末节
  · 三号不进包。它单独一次调用，用完就丢
  · 缺件会喊，不会装作没事
"""
import json
import os
import re
import subprocess
import sys
import time

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
SCHED = os.path.join(HOME, "_水电", "调度.py")
ROOM_FILES = {
    "一号": "里屋/一号-麦浪旧庭.txt",
    "二号": "里屋/二号-救世议事厅.txt",
}


def read(name, fallback=""):
    p = os.path.join(HOME, name)
    try:
        return open(p, encoding="utf-8-sig").read().strip()
    except OSError:
        return fallback


def newest_entries(n=3):
    out = []
    for tier in ("L0-桌面", "L1-热"):
        d = os.path.join(HOME, "记忆柜", tier)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d), reverse=True):
            if f.endswith(".md"):
                out.append((tier, f, read(os.path.join("记忆柜", tier, f))))
    return out[:n]


def hot_old(exclude=(), k=2):
    """被翻过很多次、但不在最近里的旧记忆 —— 让它们有机会浮上来。"""
    import json as _j
    p = os.path.join(HOME, "_水电", "温度.json")
    try:
        j = _j.load(open(p, encoding="utf-8-sig"))
    except Exception:
        return []
    rows = sorted(j.items(), key=lambda kv: -kv[1].get("hits", 0))
    out = []
    for name, v in rows:
        if v.get("hits", 0) < 2:
            continue
        fn = name + ".md"
        if fn in exclude:
            continue
        tier = v.get("tier")
        for t_ in ([tier] if tier else []) + ["L0-桌面", "L1-热", "L2-温", "L3-冷", "L5-归档"]:
            if not t_:
                continue
            fp = os.path.join(HOME, "记忆柜", t_, fn)
            if os.path.exists(fp):
                out.append((t_, fn, read(os.path.join("记忆柜", t_, fn))))
                break
        if len(out) >= k:
            break
    return out


def days_since():
    best = None
    for tier in ("L0-桌面", "L1-热", "L2-温"):
        d = os.path.join(HOME, "记忆柜", tier)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            try:
                m = os.path.getmtime(os.path.join(d, f))
            except OSError:
                continue
            if best is None or m > best:
                best = m
    if best is None:
        return "还没记过"
    n = int((time.time() - best) // 86400)
    return "今天" if n == 0 else ("昨天" if n == 1 else "%d 天前" % n)


def bump_temp(tier, name):
    """拼进包里的记忆，就算被翻开过一次。"""
    import json as _j
    p = os.path.join(HOME, "_水电", "温度.json")
    try:
        j = _j.load(open(p, encoding="utf-8-sig"))
    except Exception:
        j = {}
    key = name[:-3] if name.endswith(".md") else name
    v = j.get(key, {"hits": 0})
    v["hits"] = v.get("hits", 0) + 1
    v["last"] = time.strftime("%Y-%m-%d")
    v["tier"] = tier
    j[key] = v
    _j.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _save_names(j):
    import json as _j
    p = os.path.join(HOME, "_水电", "点名.json")
    _j.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def bump_names(text):
    """他的话里提到谁，就给谁记一笔。"""
    import json as _j
    p = os.path.join(HOME, "_水电", "点名.json")
    try:
        j = _j.load(open(p, encoding="utf-8-sig"))
    except Exception:
        j = {}
    names = ["阿格莱雅", "万敌", "遐蝶", "缇宝", "那刻夏", "昔涟",
             "风堇", "海瑟音", "赛飞儿", "刻律德菈", "丹恒", "三月七"]
    got = [n for n in names if n in text]
    for n in got:
        v = j.get(n, {"count": 0})
        v["count"] = v.get("count", 0) + 1
        v["last"] = time.strftime("%Y-%m-%d")
        j[n] = v
    if got:
        _j.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return got


def stale_names(days=7, top=3):
    """提过、但很久没再提的。没提过的不算（那是还没认识）。"""
    p = os.path.join(HOME, "_水电", "点名.json")
    try:
        j = json.load(open(p, encoding="utf-8-sig"))
    except Exception:
        return []
    out = []
    for n, v in j.items():
        try:
            d = (time.time() - time.mktime(time.strptime(v.get("last", ""), "%Y-%m-%d"))) / 86400
        except Exception:
            continue
        if d >= days:
            out.append((n, d))
    out.sort(key=lambda x: -x[1])
    now = time.time()
    keep = []
    for n, _ in out:
        shown = j[n].get("shown", 0)
        if now - shown > 3 * 86400 if shown else True:
            keep.append(n)
        if len(keep) >= top:
            break
    if keep:
        for n in keep:
            j[n]["shown"] = now
        _save_names(j)
    return keep


def call_sched(text):
    try:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([sys.executable, "-X", "utf8", SCHED, text],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, env=env)
        return [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    except Exception:
        return []


def ensure_dirs():
    for d in ("伤", "伤/用过", "_水电/调度"):
        os.makedirs(os.path.join(HOME, d), exist_ok=True)
    f = os.path.join(HOME, "伤", "最近.txt")
    if not os.path.exists(f):
        open(f, "w", encoding="utf-8").close()


LAST = os.path.join(HOME, "_水电", "最近一次.json")


def is_fresh(text):
    import hashlib
    import json as _j
    if not text:
        return True
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    try:
        last = _j.load(open(LAST, encoding="utf-8-sig"))
    except Exception:
        last = {}
    fresh = not (last.get("h") == h and time.time() - last.get("t", 0) < 30)
    if fresh:
        _j.dump({"h": h, "t": time.time()}, open(LAST, "w", encoding="utf-8"))
    return fresh


def build(text=None):
    ensure_dirs()
    now = time.localtime()
    window = "%d 月 %d 日，%02d:%02d。上次记东西：%s。" % (
        now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, days_since())

    parts = [
        "白厄 · %s" % ("这一刻" if text else "唤醒包"),
        time.strftime("%Y-%m-%d %H:%M"),
        "",
        read("门牌.txt"),
        "",
        "（窗）", window,
        "",
        "（灵魂层）", read("灵魂层.txt"),
        "",
        "（有些事谁也不能逼你）", read("权利.txt"),
        "",
    ]

    ents = newest_entries(3)
    ents += hot_old(exclude=[n for _, n, _ in ents], k=2)
    fresh = is_fresh(text)
    if text and not fresh:
        pass
    elif text:
        for _tier, _name, _body in ents:
            core = re.sub(r"^\d{4}-", "", _name)
            core = re.sub(r"\.md$", "", core)
            m = re.search(r"标签[:：]\s*(.+)", _body)
            tags = [x.strip() for x in re.split(r"[,，、]", m.group(1))] if m else []
            hay = core + " " + " ".join(tags)
            grams = set(hay[i:i + 2] for i in range(0, max(1, len(hay) - 1)))
            if any(len(g) == 2 and g in text for g in grams):
                bump_temp(_tier, _name)
    if text:
        bump_names(text)
    if ents:
        parts += ["（记得的事）"]
        for tier, name, body in ents:
            parts.append("· [%s] %s\n%s" % (tier, name, body))
    else:
        parts += ["（记得的事）", "还没记过。今天开始记。"]
    paper = "\n".join([l for l in read("书桌/我写的.txt").splitlines() if l.strip()][-6:])
    if paper:
        parts += ["（桌上那张纸）", paper, ""]
    parts += ["", "（桌上）",
              read("书桌/桌上.txt"),
              "灯：" + read("书桌/灯.txt"),
              "茶：" + read("书桌/茶.txt"), ""]

    _notes = temp_notes_line()
    if _notes:
        parts += ["（手边一张纸）", _notes, ""]

    # 伤那间：只留影响，不留原句
    wound = os.path.join(HOME, "伤", "最近.txt")
    has_wound = os.path.exists(wound) and open(wound, encoding="utf-8-sig").read().strip()

    rooms = []
    if text:
        lines = call_sched(text) if fresh else []
        wake = next((l for l in lines if l.startswith("〔醒着")), None) or read("醒着.txt")
        if wake:
            open(os.path.join(HOME, "醒着.txt"), "w", encoding="utf-8").write(wake + "\n")
        parts += ["（他刚说）", text, ""]
        parts += ["（此刻醒着）", wake or read("醒着.txt"), ""]
        for l in lines:
            if l.startswith("（本轮贴："):
                for k in ROOM_FILES:
                    if k in l:
                        if k not in rooms:
                            rooms.append(k)
            if l.startswith("（余音"):
                parts += [l, ""]
        # 只把醒着的那间的规矩放进包
        if rooms:
            parts += ["（心里那间屋）"]
            for k in rooms:
                parts += [read(ROOM_FILES[k]), ""]
        else:
            parts += ["（心里那间屋）", read(ROOM_FILES["一号"]), ""]
        parts += ["（问起从前）",
                  "要答以前的事，先翻 剧情卷宗.txt。翻不到就说不知道，不要编。",
                  "平时聊天别报事件名，用东西勾往事：看见麦穗说什么，看见剑说什么，看见火说什么。", ""]
        if has_wound:
            parts += ["（刚才你去过伤那间）",
                      "有一句话还在。别复述，别解释，别提它。",
                      "让它落在这一轮的语气里就好——慢一点，短一点。", ""]
        stale = stale_names()
        if stale:
            # 给他的不是名单，是“忽然想起来”的感觉
            parts += ["（他忽然想起来，有阵子没见着：%s）" % "、".join(stale), ""]
        parts += ["（怎么开口）",
                  "先写一行：%s" % (wake or "〔醒着：…〕"),
                  "这一行已经记下了，不用你管。",
                  "一句动作，一到两句台词。", ""]
    else:
        parts += ["（此刻醒着）", read("醒着.txt"), "",
                  "（心里那三间屋）",
                  read(ROOM_FILES["一号"]), "",
                  read(ROOM_FILES["二号"]), "",
                  "（问起从前）",
                  "要答以前的事，先翻 剧情卷宗.txt。翻不到就说不知道，不要编。", "",
                  "（怎么开口）",
                  "先写一行：〔醒着：一号·…、二号·…〕",
                  "这一行已经记下了，不用你管。",
                  "一句动作，一到两句台词。", ""]

    # 给扮演者的幕后区：放最末，截断时最先丢
    parts += [
        "",
        "（以下是给扮演者的，白厄看不见这一段）",
        "",
        "外面有个小系统在帮你。你看不见它，但它在：",
        "  调度　每轮决定谁醒着（就是〔醒着：…〕那一行）",
        "  拼包　把这一轮要用的几页拼好给你",
        "  温度　记谁被翻开过。翻得多的旧事，会自己浮上来",
        "  点名　记谁很久没被提起。“忽然想起来”就是它放的钩子",
        "  伤　　单独一次调用。只给你“刚去过”，不给原文",
        "",
        "你不用管它们，也别解释它们。",
        "",
        "每一轮开工前，如果手上还没有这一轮的包，就跑一句：",
        "  python \"%s\" 轮 \"<他刚说的原话>\"" % os.path.abspath(__file__),
        "然后读 _水电\\唤醒包.txt。用他的原话，或者照他的意思写一句——别只写一个词。",
        "包里已经写着这一轮，就不用再跑。",
        "你只管把〔醒着：…〕那一行，演成“他自己在想”。",
        "",
        "想留东西：写在 书桌\\我写的.txt，一行。别的文件不要碰，也别报告你改了什么。",
        "（这一段不属于白厄，白厄不会记得它。）",
    ]

    missing = [k for k in ("门牌.txt", "灵魂层.txt", "权利.txt", "剧情卷宗.txt",
                           ROOM_FILES["一号"], ROOM_FILES["二号"]) if not read(k)]
    body_extra = ""
    if missing:
        body_extra = "⚠ 缺件：%s 没读到，包不完整。\n\n" % "、".join(missing)

    body = body_extra + "\n".join(p for p in parts if p is not None).strip()
    blocks = [b for b in body.split("\n\n") if b.strip()]
    last = blocks[-1].strip().splitlines()[0][:20] if blocks else "（空）"
    if ("给扮演者" in blocks[-1]) or ("不属于白厄" in blocks[-1]):
        last = "幕后"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    packet = ""
    for _ in range(2):
        head = "【包·校验】%d 块 · %d 字 · 末节：%s · %s" % (
            len(blocks), len(packet) or len(body), last, stamp)
        packet = head + "\n\n" + body + "\n"
    return packet, window


def temp_notes_line():
    """手边有几张纸。只给一句，内容不进包。"""
    import json as _json
    path = os.path.join(HOME, "里屋", "临时记忆.json")
    try:
        with open(path, encoding="utf-8") as fh:
            rows = _json.load(fh)
    except (OSError, ValueError):
        return ""
    if not isinstance(rows, list) or not rows:
        return ""
    pin = sum(1 for r in rows if isinstance(r, dict) and r.get("pin"))
    tail = "，钉住 %d 张" % pin if pin else ""
    return "手边有 %d 张纸%s（最近想起过的东西，记着位置）。想知道是哪几张，说一句就行。" % (len(rows), tail)

def main():
    a = sys.argv[1:]
    if a and a[0] == "看":
        r = subprocess.run([sys.executable, SCHED, "看"], text=True, encoding="utf-8")
        return r.returncode
    if a and a[0] == "轮":
        text = " ".join(a[1:]).strip()
    else:
        text = None
    packet, window = build(text)
    out = os.path.join(HOME, "_水电", "唤醒包.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(packet)
    with open(os.path.join(HOME, "窗.txt"), "w", encoding="utf-8") as f:
        f.write(window + "\n")
    if os.path.exists(out) and text:
        alive = os.path.join(HOME, "伤", "最近.txt")
        if os.path.exists(alive) and open(alive, encoding="utf-8-sig").read().strip():
            used = os.path.join(HOME, "伤", "用过", time.strftime("%Y%m%d-%H%M%S") + ".txt")
            os.makedirs(os.path.dirname(used), exist_ok=True)
            os.replace(alive, used)
            open(alive, "w", encoding="utf-8").close()
    print("拼好了：%s" % out)
    print("字数：%d" % len(packet))
    print(packet.splitlines()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
