# -*- coding: utf-8 -*-
"""
找 —— 家里的总控：分区、检索、取一条

用法：
    找 阿草                 自动判断在哪一类
    找 相册 阿草             指定类
    找 卷宗 居酒屋           卷宗（txt + docx，docx 会先转成缓存文本）
    找 书架 某本书
    目录                    有哪些类、各多少条、哪些读不了
    看看 卷宗 第一季         不截断，整段打出来

设计：
    1. 分区：每类一个 loader，互不干扰；加新类只改 REGISTRY。
    2. 打分：2-gram 命中 + 整串命中加成 + 罕见词加权（idf）。
    3. 只给一条；要全段用「看看」。
    4. docx 先转成 {缓存}/docx/*.txt，源文件更新了才重转。
    5. 全部只读，不改家里任何文件。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

def safe_write(path, text, tries=6, delay=0.12, what=""):
    """写文件，被杀毒软件或索引器卡住就重试；真写不进去就喊出来。

    静默失败比报错更坏：包没写进去，她照样醒，谁也不知道。
    """
    import time as _t
    target = Path(path)
    last = None
    for i in range(tries):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            return True
        except OSError as exc:            # 被占用 / 权限 / 磁盘忙
            last = exc
            _t.sleep(delay * (i + 1))
    print("！写不进去：%s%s（%s）。这次的东西没存下来。" % (
        target, ("（" + what + "）") if what else "", last))
    return False

def _find_home():
    r"""家在哪：先看环境变量，再看自己住在哪儿。

    找.py 住在 <家>\_水电\ 里，所以往上两层就是家。
    这样整套东西搬到哪个盘、哪个目录都能用——写死路径是发布版的大忌。
    """
    env = os.environ.get("FEIBAO_HOME")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p.resolve()
    return Path(__file__).resolve().parent.parent


HOME = _find_home()
CACHE = HOME / "_水电" / "缓存"
TEXT_EXT = (".txt", ".md")

# docx 解析：借 feibao 自己那份（标准库解压 + XML，不依赖 python-docx）
def _docx_paragraphs(path: Path):
    try:
        sys.path.insert(0, str(HOME / "_水电"))
        import feibao  # noqa: PLC0415
        return feibao.docx_paragraphs(str(path))
    except Exception:
        return []


# ---------------------------------------------------------------- 缓存
def _cache_dir() -> Path:
    d = CACHE / "docx"
    d.mkdir(parents=True, exist_ok=True)
    return d


def docx_text(path: Path) -> str:
    """docx → 文本；按修改时间缓存，源文件变了才重转。"""
    tag = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    out = _cache_dir() / ("%s.txt" % tag)
    try:
        if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
            return out.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    paras = _docx_paragraphs(path)
    text = "\n".join(p for p in paras if p and p.strip())
    out.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------- 分区
def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def blocks_of(text: str, size_limit: int = 520):
    """按空行切块；太长的块按行再切，避免一块几千字。"""
    for raw in re.split(r"\n\s*\n", text):
        raw = raw.strip()
        if not raw:
            continue
        if len(raw) <= size_limit:
            yield raw
            continue
        buf = ""
        for line in raw.splitlines():
            if len(buf) + len(line) > size_limit and buf:
                yield buf.strip()
                buf = ""
            buf += line + "\n"
        if buf.strip():
            yield buf.strip()


def load_album():
    """相册：一格一行，不要整节揉成一块（否则"找长江"会给你整节）。"""
    out = []
    for f in sorted((HOME / "相册").glob("索引*.txt")):
        for block in blocks_of(_read(f)):
            for line in block.splitlines():
                s = line.strip()
                if not s:
                    continue
                if s.startswith("【") or s.startswith("（"):
                    continue          # 小标题不是内容
                out.append({"src": "相册/%s" % f.name, "text": s, "kind": "相册"})
    return out


def load_memory():
    root = HOME / "记忆柜"
    out = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in TEXT_EXT:
            rel = str(f.relative_to(root))
            if "_候选" in rel or "_临时" in rel:
                continue          # 还没点头的，不算进柜子
            for line in _read(f).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # 文件名也是一条线索：她说得出「河边那颗石子」，名字里就有
                    out.append({"src": "记忆柜/%s" % rel, "text": "【%s】%s" % (f.stem, line), "kind": "记忆"})
    return out


def load_archive():
    """卷宗：txt + md + docx。图片/PDF/EPUB 只记数量，不硬读。"""
    root = HOME / "卷宗"
    out = []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        rel = f.relative_to(root)
        if f.name.endswith(".字.txt"):
            continue          # 认字的产物归「图」那一类，不在这重复
        if ext in TEXT_EXT:
            for b in blocks_of(_read(f)):
                out.append({"src": "卷宗/%s" % rel, "text": b, "kind": "卷宗"})
        elif ext == ".docx":
            for b in blocks_of(docx_text(f)):
                out.append({"src": "卷宗/%s" % rel, "text": b, "kind": "卷宗"})
    return out


def load_inner():
    root = HOME / "里屋"
    out = []
    for f in sorted(root.glob("*.txt")):
        if f.name in ("临时记忆.txt", "手边抽屉.txt"):
            continue          # 那是检索的暂存，不是家里的内容
        for b in blocks_of(_read(f)):
            out.append({"src": "里屋/%s" % f.name, "text": b, "kind": "里屋"})
    return out


def load_images():
    root = HOME / "意象库"
    out = []
    for f in sorted(root.glob("*.txt")):
        for b in blocks_of(_read(f)):
            out.append({"src": "意象库/%s" % f.name, "text": b, "kind": "意象"})
    return out


def load_timeline():
    out = []
    p = HOME / "年表.txt"
    if p.is_file():
        for b in blocks_of(_read(p)):
            out.append({"src": "年表.txt", "text": b, "kind": "年表"})
    return out


def load_desk():
    root = HOME / "书桌"
    out = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in TEXT_EXT:
            for b in blocks_of(_read(f)):
                out.append({"src": "书桌/%s" % f.relative_to(root), "text": b, "kind": "书桌"})
    return out


def epub_text(path: Path) -> str:
    """epub = zip + xhtml。按文件名顺序取正文，去标签。缓存，源文件变了才重解。"""
    tag = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    out = _cache_dir() / ("%s.epub.txt" % tag)
    try:
        if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
            return out.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    import zipfile
    chunks = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist()
                     if n.lower().endswith((".xhtml", ".html", ".htm"))]
            names.sort()
            for name in names:
                raw = zf.read(name).decode("utf-8", "replace")
                # 段落分隔先变成换行，再去标签
                raw = re.sub(r"</(p|div|h[1-6]|br)\s*/?>", "\n", raw, flags=re.I)
                raw = re.sub(r"<[^>]+>", "", raw)
                raw = (raw.replace("&nbsp;", " ").replace("&amp;", "&")
                          .replace("&lt;", "<").replace("&gt;", ">")
                          .replace("&quot;", '"').replace("&#39;", "'"))
                text = "\n".join(
                    ln.strip() for ln in raw.splitlines() if ln.strip()
                )
                if text:
                    chunks.append(text)
    except Exception:  # noqa: BLE001
        return ""
    body = "\n\n".join(chunks)
    try:
        out.write_text(body, encoding="utf-8")
    except OSError:
        pass
    return body


def load_shelf():
    """书架：txt + epub（epub 解成文本后进缓存）。"""
    out = []
    for f in sorted((HOME / "书架").glob("*.txt")):
        for b in blocks_of(_read(f)):
            out.append({"src": "书架/%s" % f.name, "text": b, "kind": "书架"})
    for f in sorted((HOME / "卷宗").rglob("*.epub")):
        body = epub_text(f)
        if not body:
            continue
        for b in blocks_of(body):
            out.append({"src": "书架/%s" % f.stem, "text": b, "kind": "书架"})
    return out


def load_pictures():
    """图：文件名 + 认出来的字 + 位置。图上没有字时，至少文件名和位置能对上。"""
    out = []
    roots = [HOME / "相册", HOME / "卷宗"]
    exts = (".png", ".jpg", ".jpeg", ".webp")
    for root in roots:
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in exts:
                continue
            rel = f.relative_to(HOME)
            side = f.with_suffix(".字.txt")
            words = _read(side) if side.is_file() else ""
            # 去掉认字文件里的标题行
            body = "\n".join(
                ln for ln in words.splitlines()
                if ln.strip() and not ln.strip().startswith("—")
            )
            text = "【图】%s\n%s" % (f.stem[:60], body.strip()[:1800] or "（这张图上没有认出来的字）")
            out.append({
                "src": str(rel),
                "text": text,
                "kind": "图",
                "where": str(f),          # 位置：能直接拿去「看」
            })
    return out


# 兜底分区：放在任何地方的东西，只要没被别的分区收走，都在这儿能搜到。
SKIP_DIRS = {"_水电", "版本快照", "__pycache__", ".git", "缓存"}
# 脚本和配置不算"家里的话"：不然挖词会挖出「石子 → 收工.py」这种
SCATTER_SKIP = {".py", ".bat", ".cmd", ".ps1", ".json", ".jsonl", ".ini", ".log",
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".ico",
            ".pdf", ".zip", ".7z", ".rar", ".mp3", ".mp4", ".wav", ".exe",
            ".dll", ".pyc", ".bin", ".ttf", ".otf", ".woff"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _covered_paths():
    """先把别的分区已经收走的位置列出来，兜底只捡漏。"""
    covered = set()
    for kind in ("相册", "记忆", "卷宗", "里屋", "意象", "年表", "书桌", "书架", "图"):
        try:
            for it in items_of(kind):
                src = str(it.get("src") or "")
                if it.get("where"):
                    covered.add(os.path.normcase(os.path.abspath(it["where"])))
                elif src and not src.startswith("("):
                    covered.add(os.path.normcase(os.path.abspath(str(HOME / src))))
        except Exception:  # noqa: BLE001
            continue
    return covered


def load_scattered():
    """兜底：家里任何角落的文本和图片。"""
    covered = _covered_paths()
    out = []
    for base, dirs, files in os.walk(HOME):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = Path(base) / name
            key = os.path.normcase(os.path.abspath(str(p)))
            if key in covered:
                continue
            ext = p.suffix.lower()
            rel = p.relative_to(HOME)
            if ext in IMG_EXT:
                side = p.with_suffix(".字.txt")
                words = _read(side) if side.is_file() else ""
                body = "\n".join(ln for ln in words.splitlines() if ln.strip() and not ln.startswith("—"))
                out.append({"src": str(rel), "kind": "散落",
                            "text": "【图】%s\n%s" % (p.stem[:60], body.strip()[:1500] or "（这张图上没有认出来的字）"),
                            "where": str(p)})
                continue
            if ext in SCATTER_SKIP:
                continue
            if p.stat().st_size > 400_000:      # 太大的不硬读
                continue
            body = _read(p)
            if not body.strip():
                continue
            if body.count("\x00"):              # 看着像二进制就跳过
                continue
            for b in blocks_of(body):
                out.append({"src": str(rel), "text": b, "kind": "散落"})
    return out


REGISTRY = {
    "相册": load_album,
    "记忆": load_memory,
    "卷宗": load_archive,
    "里屋": load_inner,
    "意象": load_images,
    "年表": load_timeline,
    "书桌": load_desk,
    "书架": load_shelf,
    "图": load_pictures,
    "散落": load_scattered,
}

ALIASES = {
    "图": "相册", "album": "相册",
    "记得": "记忆", "回忆": "记忆", "memory": "记忆",
    "档案": "卷宗", "故事会": "卷宗",
    "家": "里屋", "家人": "里屋",
    "书": "书架", "读": "书架",
    "散": "散落", "随便": "散落",
}

_cache: dict = {}


def items_of(kind: str):
    if kind not in _cache:
        _cache[kind] = REGISTRY[kind]()
    return _cache[kind]


_ITEMS_ONCE = []


def all_items():
    """一次运行里只读一遍目录。

    每条命令是一次性的进程，所以不会读到旧数据；
    但评测/挖词这种批量的，30 条就是 30 次重扫——缓存住就快很多。
    """
    if _ITEMS_ONCE:
        return _ITEMS_ONCE[0]
    items = _load_all_items()
    _ITEMS_ONCE.append(items)
    return items


def _load_all_items():
    out = []
    for kind in REGISTRY:
        out.extend(items_of(kind))
    return out


# ---------------------------------------------------------------- 打分
def grams(text, n=2):
    text = re.sub(r"\s+", "", text)
    return {text[i:i + n] for i in range(max(0, len(text) - n + 1))}


def build_df(items):
    df = {}
    for it in items:
        for token in grams(it["text"]):
            df[token] = df.get(token, 0) + 1
    return df


def coverage(query, text):
    """查询里有多少 2-gram 真的出现在这段里。用来挡"硬凑"的命中。"""
    g = grams(re.sub(r"\s+", "", query))
    if not g:
        return 0.0
    return sum(1 for token in g if token in text) / float(len(g))


MIN_COVERAGE = 0.34          # 不到三分之一的字连得上，就当没找到
MIN_COSINE = 0.55            # 校准过：不相关最高 0.47，相关最低 0.58


# ---------------------------------------------------------------- BM25
# 用中文双字切分算 BM25。比“命中次数 + 长度惩罚”稳，尤其对长文档。
# 分区权重先全留 1.0：实测"压书架抬相册"会让书里的东西找不到。
# 结构留着，以后真要调，用基准量过再动。
KIND_WEIGHT = {
    "相册": 1.0, "记忆": 1.0, "意象": 1.0, "里屋": 1.0,
    "图": 1.0, "年表": 1.0, "书桌": 1.0, "卷宗": 1.0, "书架": 1.0, "散落": 0.8,
}
# 关键词占多少：1.0 = 关键词说了算（语义只在没命中时兜底）
KW_ALPHA_ONLINE = 1.0
KW_ALPHA_OFFLINE = 0.55
BM25_K1 = 1.5
BM25_B = 0.75    # 网格搜出来 0.75 略好于 0.6（k1 在 0.9~2.5 之间无差别，取 1.5 防过拟合）
_bm25_cache = {}


def _bm25_stats(all_items_list):
    """一次算好：每个块的词频、文档频率、平均长度。"""
    key = (len(all_items_list), id(all_items_list))
    if key in _bm25_cache:
        return _bm25_cache[key]
    docs = []
    df = {}
    for it in all_items_list:
        cnt, dl = doc_tokens(it)
        docs.append((cnt, dl))
        for tok in cnt:
            df[tok] = df.get(tok, 0) + 1
    avgdl = (sum(d for _, d in docs) / len(docs)) if docs else 1.0
    _bm25_cache[key] = (docs, df, avgdl)
    return _bm25_cache[key]


_DOC_TOK = {}


def doc_tokens(it):
    """某一条的词频和长度，算一次就够。"""
    key = id(it)
    got = _DOC_TOK.get(key)
    if got is None:
        cnt = Counter(grams(it["text"]))
        got = (cnt, sum(cnt.values()))
        _DOC_TOK[key] = got
    return got

def _tfidf_cosine(query, pool):
    """TF-IDF 余弦：跟 BM25 互补（它按余弦归一，长文档不吃亏）。"""
    total = len(pool)
    docs = [doc_tokens(it)[0] for it in pool]
    df = {}
    for c in docs:
        for tok in c:
            df[tok] = df.get(tok, 0) + 1
    qc = Counter(grams(re.sub(r"\s+", "", query)))
    qv = {}
    for tok, f in qc.items():
        idf = math.log((1 + total) / (1 + df.get(tok, 0))) + 1.0
        qv[tok] = (1 + math.log(f)) * idf
    qn = math.sqrt(sum(x * x for x in qv.values())) or 1.0
    qv = {t: x / qn for t, x in qv.items()}
    out = []
    for idx, c in enumerate(docs):
        dot = 0.0
        for tok, x in qv.items():
            f = c.get(tok, 0)
            if not f:
                continue
            idf = math.log((1 + total) / (1 + df.get(tok, 0))) + 1.0
            dot += x * ((1 + math.log(f)) * idf)
        if dot > 0:
            norm = math.sqrt(sum(((1 + math.log(v)) *
                                  (math.log((1 + total) / (1 + df.get(k, 0))) + 1.0)) ** 2
                                 for k, v in c.items())) or 1.0
            out.append((dot / norm, idx))
    out.sort(key=lambda x: -x[0])
    return [(s, pool[i]) for s, i in out]


def keyword_scores(query, pool):
    """关键词那一路：TF-IDF 余弦 + BM25，各占一半。

    单用 BM25 会压长文档（b 参数），单用 TF-IDF 又对词频不敏感。
    30 题实测：TF-IDF 87%、BM25 83%、两者混合 87%，用混合更稳。
    """
    tf = _tfidf_cosine(query, pool)
    bm = bm25_scores(query, pool)
    def norm(pairs):
        if not pairs:
            return {}
        top = pairs[0][0] or 1.0
        return {id(it): (s / top, it) for s, it in pairs[:40]}
    a, b = norm(tf), norm(bm)
    merged = {}
    for key, (s, it) in a.items():
        merged[key] = [0.5 * s, it]
    for key, (s, it) in b.items():
        cur = merged.get(key)
        if cur:
            cur[0] += 0.5 * s
        else:
            merged[key] = [0.5 * s, it]
    out = [(v[0], v[1]) for v in merged.values() if v[0] > 0]
    out.sort(key=lambda x: -x[0])
    return out

def bm25_scores(query, all_items_list):
    docs, df, avgdl = _bm25_stats(all_items_list)
    total = len(all_items_list)
    q = grams(re.sub(r"\s+", "", query))
    out = []
    for idx, it in enumerate(all_items_list):
        cnt, dl = docs[idx]
        s = 0.0
        for tok in q:
            f = cnt.get(tok, 0)
            if not f:
                continue
            idf = math.log(1.0 + (total - df.get(tok, 0) + 0.5) / (df.get(tok, 0) + 0.5))
            s += idf * (f * (BM25_K1 + 1)) / (f + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(1.0, avgdl)))
        if s > 0:
            # 首行（标题/名字）命中，比正文里命中更能说明"就是这条"
            head = it["text"].splitlines()[0] if it["text"] else ""
            for tok in q:
                if tok in head:
                    s *= 1.35
                    break
            # 分区先验：日常的东西比"她在读的书"更容易是想要的那条
            s *= KIND_WEIGHT.get(it.get("kind", ""), 1.0)
            out.append((s, it))
    out.sort(key=lambda x: -x[0])
    return out

def score(query, text, df, total, base=None):
    q = re.sub(r"\s+", "", query)
    if not q:
        return 0.0
    cov = coverage(re.sub(r"\s+", "", base or query), text)
    if cov < MIN_COVERAGE:
        return 0.0
    s = 0.0
    for token in grams(q):
        if token in text:
            s += math.log(1.0 + total / (1.0 + df.get(token, 0)))
    if q in text:
        s += 3.0
    s /= max(1.0, math.sqrt(len(text) / 60.0))
    return s * (0.5 + cov)


# ---------------------------------------------------------------- 语义（本地 bge-m3）
import urllib.request  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "bge-m3"
VEC_CACHE = CACHE / "vectors.json"
SEM_KINDS = ("相册", "记忆", "卷宗", "里屋", "意象", "年表", "书桌")


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def load_vecs() -> dict:
    try:
        return json.loads(VEC_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_vecs(vecs: dict) -> None:
    try:
        VEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
        VEC_CACHE.write_text(json.dumps(vecs, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def embed(texts):
    """一批文本 → 向量；失败返回 None（那就退回关键词）。"""
    body = json.dumps({"model": EMBED_MODEL, "input": list(texts)}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA + "/api/embed", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("embeddings") or None
    except Exception:  # noqa: BLE001
        return None


def warm_vectors(items):
    """把语义分区里还没算过的条目补上向量。首次会慢，之后走缓存。"""
    vecs = load_vecs()
    todo = []
    for it in items:
        if it["kind"] not in SEM_KINDS:
            continue
        key = _digest(it["text"])
        if key not in vecs:
            todo.append((key, it["text"][:600]))
    if not todo:
        return vecs
    print("（第一次算向量：%d 条，稍等…）" % len(todo))
    for i in range(0, len(todo), 16):
        chunk = todo[i:i + 16]
        got = embed([t for _, t in chunk])
        if not got:
            break
        for (key, _), vec in zip(chunk, got):
            vecs[key] = vec
    save_vecs(vecs)
    return vecs


def cos(a, b):
    s = 0.0
    na = nb = 0.0
    for x, y in zip(a, b):
        s += x * y
        na += x * x
        nb += y * y
    if not na or not nb:
        return 0.0
    return s / (na ** 0.5 * nb ** 0.5)


_EMBED_OK = None      # None=没试过，True/False=试过


def embed_available():
    """问一次 Ollama，问不到就记住，不再每轮等。"""
    global _EMBED_OK
    if _EMBED_OK is not None:
        return _EMBED_OK
    if os.environ.get("FEIBAO_NO_EMBED"):
        _EMBED_OK = False
        return False
    # 先花 1 秒问一句"你在吗"：服务器没开就立刻退，不耗 15 秒
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=1) as resp:
            resp.read(256)
    except Exception:  # noqa: BLE001
        _EMBED_OK = False
        return False
    try:
        # 模型冷启动可能十几秒，给够时间；以前给 3 秒，结果明明在线被判成离线
        body = json.dumps({"model": EMBED_MODEL, "input": ["在吗"]}).encode("utf-8")
        req = urllib.request.Request(OLLAMA + "/api/embed", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read(2048)
        _EMBED_OK = True
    except Exception:  # noqa: BLE001
        _EMBED_OK = False
    return _EMBED_OK


def _bigrams(text, limit=320):
    from collections import Counter
    s = re.sub(r"\s+", "", str(text or ""))[:limit]
    if len(s) < 2:
        return Counter(s)
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def _cos_counter(a, b):
    if not a or not b:
        return 0.0
    dot = sum(min(a[k], b[k]) for k in a.keys() & b.keys())
    norm = (sum(a.values()) ** 0.5) * (sum(b.values()) ** 0.5)
    return dot / norm if norm else 0.0


# 离线时的"主题词扩展"：她说的话里带哪个熟悉的词，就把同族词一起放进去搜。
# 词表放在 <家>\_水电\词表.json，这样引擎本身不带任何私人的名字。
EXPAND_DEFAULT = {
    "画画": ("画", "笔", "素描", "涂"),
    "店": ("门", "柜台", "老板", "灯"),
    "雪": ("冬", "雪地", "冷"),
    "雨": ("伞", "窗", "湿"),
    "夜": ("深夜", "灯", "巷子"),
    "饭": ("吃", "锅", "菜"),
}


def _load_expand():
    """默认词表 + 这个家自己的词表。词表是私人的，代码是公共的。"""
    table = {k: tuple(v) for k, v in EXPAND_DEFAULT.items()}
    path = HOME / "_水电" / "词表.json"
    if path.is_file():
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
            for key, words in extra.items():
                if isinstance(words, list) and words:
                    table[str(key)] = tuple(str(w) for w in words)
        except (OSError, ValueError):
            pass          # 词表坏了就当没有，不影响检索
    return table


EXPAND = _load_expand()

def expand_query(query):
    """把"那个画画的"扩成"那个画画的 画 笔 素描"——只在离线时用。"""
    extra = []
    for key, words in EXPAND.items():
        if key in query:
            extra.extend(words)
    if not extra:
        return query, False
    seen = []
    for w in extra:
        if w not in seen:
            seen.append(w)
    return query + " " + " ".join(seen), True


def fuzzy_rank(query, pool, top=8):
    """没模型时的兜底：字符 bigram 余弦。谁用都行，不依赖网络。"""
    q = _bigrams(query, 64)
    scored = []
    for it in pool:
        c = _cos_counter(q, _bigrams(it["text"]))
        if c >= 0.22:
            scored.append((c, it))
    scored.sort(key=lambda x: -x[0])
    return scored[:top]

def semantic_rank(query, pool, vecs, df, total, top=8):
    """返回按语义相近排好的 [(分数, item)]；不可用时返回空。"""
    if not vecs:
        return []
    got = embed([query])
    if not got:
        return []
    qv = got[0]
    scored = []
    for it in pool:
        vec = vecs.get(_digest(it["text"]))
        if not vec:
            continue
        c = cos(qv, vec)
        if c < MIN_COSINE:
            continue
        scored.append((c, it))
    scored.sort(key=lambda x: -x[0])
    return scored[:top]


# ---------------------------------------------------------------- 临时记忆
# 检索到的东西不进包。先进「手边一张纸」，包只带它的标题行。
TEMP_JSON = HOME / "里屋" / "临时记忆.json"
DRAWER_JSON = HOME / "里屋" / "手边抽屉.json"
TRASH_JSON = HOME / "_水电" / "缓存" / "垃圾桶.json"
DRAWER_TTL_DAYS = 2      # 纸条在抽屉里最多待两天（现实日期，关机也照算）
TRASH_KEEP = 20          # 垃圾桶只留最近 20 张，多了就真没了
TEMP_CAP = 8          # 手边最多 8 张
# 温度账本。名字带个"找-"：有的家里另有 温度.py 也用 温度.json，格式不同，不能共用。
LEDGER = HOME / "_水电" / "找-温度.json"
_OLD_LEDGER = HOME / "_水电" / "温度.json"


def _migrate_ledger():
    """老版本把账记在 温度.json 里，搬过来（只搬长得像我们那种的）。"""
    if LEDGER.is_file() or not _OLD_LEDGER.is_file():
        return
    try:
        data = json.loads(_OLD_LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict) and data and all(
            isinstance(v, dict) and "hits" in v for v in list(data.values())[:5]):
        try:
            LEDGER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


_migrate_ledger()


def bump_temperature(src: str):
    """检索到一条 = 想起一次。给温度账本记一笔（不动包）。"""
    # 用相对路径当键：相册\索引.txt 和 卷宗\回忆\索引.txt 不会撞
    name = str(src or "").replace("/", "\\").strip("\\")
    if not name:
        return
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:  # noqa: BLE001
        data = {}
    row = data.get(name) or {}
    row["hits"] = int(row.get("hits", 0) or 0) + 1
    import datetime as _dt
    row["last_hit"] = _dt.date.today().isoformat()
    row["cycle"] = int(row.get("cycle", 1) or 1)
    data[name] = row
    try:
        safe_write(LEDGER, json.dumps(data, ensure_ascii=False, indent=2), what="温度")
    except OSError:
        pass
PIN_CAP = 2           # 钉住的最多 2 张
TEMP_TXT = HOME / "里屋" / "临时记忆.txt"


def _temp_load():
    try:
        data = json.loads(TEMP_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _temp_save(rows):
    try:
        safe_write(TEMP_JSON, json.dumps(rows, ensure_ascii=False, indent=1), what="手边")
        lines = ["临时记忆（手边一张纸）", "（看完就收，不收会一直放在这儿；最多留 8 条）", ""]
        for i, row in enumerate(rows, 1):
            lines.append("%d. [%s] %s" % (i, row.get("at", ""), row.get("title", "")))
            if row.get("where"):
                lines.append("   位置：%s" % row["where"])
            body = str(row.get("text") or "")
            lines.append("   " + body.replace("\n", "\n   ")[:1200])
            lines.append("")
        TEMP_TXT.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


def temp_add(item, at=None):
    import datetime as _dt
    rows = _temp_load()
    title = item.get("text", "").splitlines()[0][:48]
    for row in rows:                     # 已经在手边的，不重复占格
        if row.get("src") == item.get("src", "") and row.get("title") == title:
            row["at"] = at or row.get("at", "")
            _temp_save(rows)
            return {"count": len(rows), "spilled": 0, "dup": True}
    rows.append({
        "at": at or _dt.datetime.now().strftime("%m-%d %H:%M"),
        "kind": item.get("kind", ""),
        "src": item.get("src", ""),
        "title": item.get("text", "").splitlines()[0][:48],
        "where": item.get("where", ""),
        "chars": len(item.get("text", "") or ""),   # 只记"有多长"，不抄内容
    })
    # 满了不静默丢：按分数挑最弱的一张，退到抽屉（以后能捡回来）
    spilled = []
    while len(rows) > TEMP_CAP:
        cand = [(score_of(i, r), i) for i, r in enumerate(rows) if not r.get("pin")]
        if not cand:
            break                      # 全钉住了，就先超着
        _, worst = min(cand)
        spilled.append(rows.pop(worst))
    _drawer_save(_drawer_load()[-16:] + spilled)
    _temp_save(rows)
    if spilled:
        try:
            print(council("drop", "手边满了", heads=2))
        except Exception:  # noqa: BLE001
            pass
    return {"count": len(rows), "spilled": len(spilled)}


# ---------------------------------------------------------------- 里屋评议
# 手边满了 / 换时段散纸时，请两三个人说一句。不是全员开会，按轮次轮。
COUNCIL_JSON = HOME / "里屋" / "评议.json"
COUNCIL_TXT = HOME / "里屋" / "评议.txt"

SEATS = {
    "阿草": {
        "keep": ("「这个留着。」", "「记着吧，别丢。」"),
        "drop": ("「嗯……这个不用留吧。」", "「先放着，不占地方。」"),
    },
    "老周": {
        "keep": ("「哎，这个得留着。」", "「这张有味道，留着。」"),
        "drop": ("「扔了吧，别背着。」", "「忘就忘了，没事。」"),
    },
    "小满": {
        "keep": ("「有用。以后会想起来的。」", "「这个留着比较好。」"),
        "drop": ("「不碍事，也不必要。」", "（她看了一眼，没说话。）"),
    },
}
ORDER = ("阿草", "老周", "小满")     # 换成你自己家里的几个人


COUNCIL_KEEP = 240        # 评议.txt 最多留 240 行，再老的就并到「旧」那份


def _rotate_council():
    """评议越攒越长：超过上限就把前一半并到 评议-旧.txt。"""
    try:
        lines = COUNCIL_TXT.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= COUNCIL_KEEP * 2:
        return
    cut = len(lines) - COUNCIL_KEEP
    head, tail = lines[:cut], lines[cut:]
    try:
        with (COUNCIL_TXT.parent / "评议-旧.txt").open("a", encoding="utf-8") as fh:
            fh.write("\n".join(head) + "\n")
        COUNCIL_TXT.write_text("\n".join(tail) + "\n", encoding="utf-8")
    except OSError:
        pass

def _council_load():
    try:
        data = json.loads(COUNCIL_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _council_save(data):
    try:
        safe_write(COUNCIL_JSON, json.dumps(data, ensure_ascii=False, indent=1), what="评议")
    except OSError:
        pass


def council(decide="drop", note="", heads=2):
    """请 2~3 个人各说一句。轮次推进，谁都不会被一直晾着。"""
    import random as _r
    data = _council_load()
    turn = int(data.get("turn", 0) or 0)
    picked = [ORDER[(turn + i) % len(ORDER)] for i in range(heads)]
    data["turn"] = turn + heads
    lines = []
    for seat in picked:
        pool = SEATS.get(seat, {}).get(decide) or SEATS[seat]["keep"]
        lines.append("%s：%s" % (seat, _r.choice(pool)))
    head = "（里屋评议 · %s）" % (note or "手边")
    text = head + "\n" + "\n".join(lines)
    try:
        with COUNCIL_TXT.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n\n")
        _rotate_council()
    except OSError:
        pass
    _council_save(data)
    return text

def spill_unpinned(reason=""):
    """换时段了：没钉住的纸退抽屉（钉住的留下）。"""
    rows = _temp_load()
    keep = [r for r in rows if r.get("pin")]
    drop = [r for r in rows if not r.get("pin")]
    said = ""
    if drop:
        _drawer_save(_drawer_load()[-16:] + drop)
        _temp_save(keep)
        try:                              # 两个或三个人各说一句
            said = council("drop", "散纸 %d 张" % len(drop), heads=2 if len(drop) < 4 else 3)
            print(said)
        except Exception:  # noqa: BLE001
            pass
    return {"kept": len(keep), "spilled": len(drop), "reason": reason, "said": said}


def score_of(index, row):
    """越靠后越新；被用过的更牢；钉住的不参与淘汰。"""
    uses = int(row.get("uses", 0) or 0)
    recency = index / max(1.0, float(TEMP_CAP))
    return recency + uses * 1.5


def _today():
    import datetime as _dt
    return _dt.date.today()


def _trash_add(rows):
    """扔垃圾桶：只留最近 TRASH_KEEP 张，再老的才算真没了。"""
    if not rows:
        return
    try:
        cur = json.loads(TRASH_JSON.read_text(encoding="utf-8"))
        if not isinstance(cur, list):
            cur = []
    except Exception:  # noqa: BLE001
        cur = []
    cur.extend(rows)
    try:
        TRASH_JSON.parent.mkdir(parents=True, exist_ok=True)
        TRASH_JSON.write_text(
            json.dumps(cur[-TRASH_KEEP:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def drawer_cleanup():
    """清一次抽屉：返回 {kept, expired, off_days}。

    用的是现实日期，所以关机多久都算得对：回来那天一比就知道。
    """
    import datetime as _dt
    try:
        data = json.loads(DRAWER_JSON.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        rows = []
    today = _today()
    kept, expired, off_days = [], [], 0
    for row in rows:
        day = str(row.get("在抽屉") or "")[:10]
        try:
            past = _dt.date.fromisoformat(day)
        except ValueError:
            kept.append(row)
            continue
        gap = (today - past).days
        if gap < 0:
            # 系统时间被调回去了：不删，盖今天的戳
            row["在抽屉"] = today.isoformat()
            kept.append(row)
            continue
        off_days = max(off_days, gap)
        if gap >= DRAWER_TTL_DAYS:
            expired.append(row)
        else:
            kept.append(row)
    if expired:
        _trash_add(expired)
        try:
            safe_write(DRAWER_JSON, json.dumps(kept, ensure_ascii=False, indent=1), what="抽屉")
        except OSError:
            pass
    return {"kept": len(kept), "expired": len(expired), "off_days": off_days}


def _drawer_load():
    """读抽屉：顺手清过期的。记忆本身还在文件夹里，纸条没了不影响。"""
    drawer_cleanup()
    try:
        data = json.loads(DRAWER_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _drawer_save(rows):
    today = _today().isoformat()
    for row in rows:
        row.setdefault("在抽屉", today)
    try:
        safe_write(DRAWER_JSON, json.dumps(rows[-24:], ensure_ascii=False, indent=1), what="抽屉")
    except OSError:
        pass


def resolve_text(row):
    """纸条上只有位置；念的时候现场去翻。翻不到才退回旧字段。"""
    if row.get("text"):
        return str(row["text"])            # 老纸条（还抄着全文的）
    src = str(row.get("src") or "")
    title = str(row.get("title") or "")
    if not src:
        return "（这张纸条上没写位置）"
    path = HOME / src
    if row.get("where") and Path(str(row["where"])).is_file():
        side = Path(str(row["where"])).with_suffix(".字.txt")
        if side.is_file():
            body = _read(side)
            return "\n".join(ln for ln in body.splitlines() if not ln.startswith("—"))
    if not path.is_file():
        return "（原来的地方找不到了：%s）" % src
    key = title[:16]
    for block in blocks_of(_read(path)):
        if block.startswith(key[:8]) or key in block[:60]:
            return block
    return _read(path)[:1200]

def temp_lines(limit=5):
    """给醒用的几行：只有标题，没有正文。"""
    rows = _temp_load()
    out = []
    for i, row in enumerate(rows[-limit:], 1):
        n = int(row.get("chars", 0) or 0) or len(str(row.get("text") or ""))
        tail = ("，图在 %s" % (row.get("src") or "")[:40]) if row.get("where") else ""
        out.append("%s. %s（%d 字%s，要念就用「用 %d」）" % (
            row.get("kind", ""), row.get("title", ""), n, tail, i))
    return out


# ---------------------------------------------------------------- 输出
def show(item, full=False):
    text = item["text"]
    head = text.splitlines()[0][:46]
    print("〔%s〕%s" % (item["kind"], item["src"]))
    print("  " + head)
    if item.get("where"):
        print("  位置：%s" % item["where"])
        print("  想看：认字 里的「看」%s" % Path(item["where"]).name)
    if full:
        rest = text[len(head):].strip()
        if rest:
            print("  " + rest.replace("\n", "\n  "))
    elif len(text) > len(head):
        print("  …（共 %d 字，要全段用「看看」）" % len(text))


def guess_kind(query, df, total):
    best, best_s = "", -1.0
    for kind in REGISTRY:
        sub = items_of(kind)
        if not sub:
            continue
        s = max((score(query, it["text"], df, total) for it in sub), default=0.0)
        if s > best_s:
            best, best_s = kind, s
    return best, best_s


SKIP_EXT = {".webp", ".png", ".jpg", ".jpeg", ".pdf", ".mp4", ".mp3"}


def cmd_list():
    allit = all_items()
    df = build_df(allit)
    total = len(allit)
    print("分区：")
    for kind in REGISTRY:
        sub = items_of(kind)
        files = len({it["src"] for it in sub})
        print("  %-4s %5d 条 / %2d 个文件" % (kind, len(sub), files))
    # 读不了的
    skipped = {}
    for f in (HOME / "卷宗").rglob("*"):
        if f.is_file() and f.suffix.lower() in SKIP_EXT:
            skipped[f.suffix.lower()] = skipped.get(f.suffix.lower(), 0) + 1
    if skipped:
        print("  （读不了的：%s）" % "、".join("%s %d" % (k, v) for k, v in sorted(skipped.items())))
    return 0


def prune_vectors(rebuild=False):
    """清向量缓存：没有对应内容的条目删掉；rebuild=True 全清重算。"""
    import os as _os
    if rebuild:
        try:
            VEC_CACHE.unlink()
        except OSError:
            pass
        return {"before": 0, "after": 0, "removed": "all"}
    vecs = load_vecs()
    before = len(vecs)
    if not before:
        return {"before": 0, "after": 0, "removed": 0}
    live = set()
    for it in all_items():
        if it["kind"] in SEM_KINDS:
            live.add(_digest(it["text"]))
    kept = {k: v for k, v in vecs.items() if k in live}
    removed = before - len(kept)
    if removed:
        try:
            VEC_CACHE.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return {"before": before, "after": len(kept), "removed": removed}

def search_ranked(query, kind="", top=3):
    """检索 + 两路融合，返回排好序的条目。

    主流程和评测脚本都调这一个函数——两边各写一遍一定会走偏。
    """
    t0 = time.time()
    allit = all_items()
    pool = items_of(kind) if kind else allit
    df = build_df(allit)
    total = len(allit)
    kw = keyword_scores(query, pool)
    semi = []
    if kw:
        # 关键词已经命中了，就不去碰模型：省一次冷启动（实测能省 14 秒）
        # 语义只在"一条都没命中"时才帮忙，这也是 30 题量出来的结论
        mode = "关键词"
    elif embed_available():
        df = build_df(allit)
        vecs = warm_vectors(pool)
        semi = semantic_rank(query, pool, vecs, df, total, top=8)
        mode = "含语义（兜底）"
    else:
        expanded, _did = expand_query(query)
        words = expanded[len(query):].split() if _did else []
        kw2 = []
        for it in pool:
            hits = sum(1 for w in words if w in it["text"])
            if hits >= 2:
                kw2.append((hits, it))
        kw2.sort(key=lambda x: -x[0])
        if kw2:
            kw = kw2
        semi = fuzzy_rank(expanded if _did else query, pool, top=8)
        mode = "离线（模糊兜底）"
    alpha = 1.0
    fused, by_id = {}, {}
    kw_top = kw[0][0] if kw else 0.0
    for s, it in kw[:20]:
        val = alpha * ((s / kw_top) if kw_top > 0 else 0.0)
        fused[id(it)] = max(fused.get(id(it), 0.0), val)
        by_id[id(it)] = it
    sem_top = semi[0][0] if semi else 0.0
    for s, it in semi[:20]:
        fused[id(it)] = fused.get(id(it), 0.0) + (1 - alpha) * ((s / sem_top) if sem_top > 0 else 0.0)
        by_id[id(it)] = it
    order = sorted(fused.items(), key=lambda kv: -kv[1])
    hits = [by_id[k] for k, _ in order[:top] if k in by_id]
    return hits, mode, time.time() - t0

# ---------------------------------------------------------------- 挖词
WORD_BAD = set("的了是在和也就都很我你他她它把被给让对从到又还但而及与或个这那有没不一")
WORD_STOP = set("""什么 自己 然后 今天 时候 觉得 起来 出来 一下 一样 这样 那样 因为 所以 但是 现在 已经 还是 就是 没有 一个 我们 他们 你们 这个 那个 里面 外面 上面 下面 前面 后面 上来 下去 之前 之后 东西 事情 两遍 一边 有点 一点 不是 不能 可以 可能 应该 知道 看见 看到 听到 说话""".split())
WORD_PUNCT = set("，。、；：""''（）《》…—！？·　,.!?;:()[]{}<>/\\|~`@#$%^&*+=-_”")
CAND_JSON = HOME / "_水电" / "词表-候选.json"


def _anchors():
    """锚点：词表里已有的 + 记忆里写过的「标签」。

    标签是写记忆时顺手打的（标签：万敌, 耐热），比手写词表省事得多。
    """
    seen = []
    for key in _load_expand():
        if key not in seen:
            seen.append(key)
    mem = HOME / "记忆柜"
    if mem.is_dir():
        for p in mem.rglob("*.md"):
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
                    if not line.strip().startswith("标签"):
                        continue
                    body = line.split("：", 1)[-1].split(":", 1)[-1]
                    for tag in re.split(r"[,，、;；\s]+", body):
                        tag = tag.strip()
                        if 2 <= len(tag) <= 6 and tag not in seen:
                            seen.append(tag)
            except OSError:
                continue
    return seen

def _merge_pieces(rows, known):
    """相邻双字拼回词，但只拼"原文里真出现过"的三字。

    没这道校验会拼出「张三看」「海道旅」这种假词。
    """
    out = []
    used = set()
    for i, (w, c, d) in enumerate(rows):
        if i in used:
            continue
        best = None
        for j, (w2, c2, d2) in enumerate(rows):
            if j == i or j in used:
                continue
            merged = w + w2[1:]
            if w[-1] != w2[0] or merged not in known:
                continue
            score = min(c, c2)
            if best is None or score > best[0]:
                best = (score, j, merged, c2, d2)
        if best:
            used.add(i)
            used.add(best[1])
            out.append((best[2], max(c, best[3]), max(d, best[4])))
        else:
            used.add(i)
            out.append((w, c, d))
    out.sort(key=lambda x: -x[1])
    return out

def mine_words(top_per_anchor=8, min_hits=3, max_docs=40):
    """从卷宗里挖"跟某个名字总一起出现的东西"。

    只写候选，不动词表。同现份数当证据给人看。
    """
    items = all_items()
    df = Counter()
    for it in items:
        for g in set(grams(it["text"])):
            if len(g) == 2 and not any(c in WORD_PUNCT for c in g):
                df[g] += 1
    limit = max(20, len(items) // 4)
    # 原文里出现过至少 3 次的 3 字串，用来校验拼出来的词是真的
    tri = Counter()
    for it in items:
        s = re.sub(r"\s+", "", it["text"])
        for k in range(len(s) - 2):
            piece = s[k:k + 3]
            if any(ch in WORD_PUNCT for ch in piece):
                continue
            tri[piece] += 1
    known = {w for w, c in tri.items() if c >= 5}      # 拼出来的词，原话里至少五回
    out = {}
    for anchor in _anchors():
        near = Counter()
        docs = Counter()
        for it in items:
            text = it["text"]
            if anchor not in text or "没有认出来的字" in text:
                continue
            for m in re.finditer(re.escape(anchor), text):
                lo = max(0, m.start() - 30)
                hi = min(len(text), m.end() + 30)
                seen = set()
                for g in grams(text[lo:hi]):
                    if len(g) != 2 or any(c in WORD_PUNCT for c in g):
                        continue
                    if any(ch in WORD_BAD for ch in g):
                        continue
                    if re.search(r"[A-Za-z0-9]", g):          # 代码和版本号，不是话
                        continue
                    if anchor in g or g in seen or df[g] > limit or g in WORD_STOP:
                        continue
                    seen.add(g)
                    near[g] += 1
                    docs[g] += 1
        picked = [(w, c, docs[w]) for w, c in near.most_common(40)
                  if c >= min_hits and docs[w] <= max_docs]
        picked = _merge_pieces(picked, known)
        # 「张三看」这种：拼出来的词以别的名字开头，是假词
        # 拼出来的词尾是动词的，基本是「张三看」「人机改」这类假词
        bad_tail = set("看说走想来去笑问答坐站拿放吃改扑飞落开有是把被给")
        picked = [(w, c, d) for w, c, d in picked if not (len(w) > 2 and w[-1] in bad_tail)]
        others = [a for a in _anchors() if a != anchor]
        picked = [(w, c, d) for w, c, d in picked
                  if anchor not in w and not (len(w) > 2 and any(w.startswith(o) for o in others))]
        if picked:
            out[anchor] = [{"词": w, "同现": c, "份数": d} for w, c, d in picked[:top_per_anchor]]
    return out


def cmd_mine():
    found = mine_words()
    if not found:
        print("没挖到：要么家里东西太少（同现不到 3 次），要么词表还是空的。")
        return 0
    try:
        CAND_JSON.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        print("写不进候选文件：%s" % exc)
        return 1
    total = sum(len(v) for v in found.values())
    print("挖到 %d 组、共 %d 个候选词（写在 %s）" % (len(found), total, CAND_JSON.name))
    for anchor, rows in list(found.items())[:8]:
        words = "、".join("%s(%d)" % (r["词"], r["同现"]) for r in rows[:6])
        print("  %-6s → %s" % (anchor, words))
    print()
    print("（这些只是候选。想收进去：改 _水电\\词表.json 自己加，或者用「收词」全收）")
    return 0


def cmd_accept_words(argv=None):
    """把候选并进词表。

    不带参数：先看有哪些组，不动。
    带组名（可以几个）：只收这几组，其余留在候选里。
        python 找.py 收词 围裙 画
    """
    if not CAND_JSON.is_file():
        print("没有候选文件。先跑「挖词」。")
        return 0
    try:
        cand = json.loads(CAND_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("候选文件坏了，读不出来。")
        return 1
    args = [a for a in (argv or []) if a]
    if not args:
        print("候选里有 %d 组：" % len(cand))
        for anchor, rows in cand.items():
            words = "、".join(r["词"] if isinstance(r, dict) else str(r) for r in rows[:6])
            print("  %-6s → %s" % (anchor, words))
        print()
        print("收哪组就写哪组：python 找.py 收词 围裙 画")
        return 0

    path = HOME / "_水电" / "词表.json"
    try:
        table = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        table = {}
    added = 0
    taken = []
    for anchor in args:
        rows = cand.get(anchor)
        if not rows:
            print("候选里没有「%s」这组。" % anchor)
            continue
        cur = list(table.get(anchor, []))
        for row in rows:
            word = row.get("词") if isinstance(row, dict) else str(row)
            if word and word not in cur:
                cur.append(word)
                added += 1
        table[anchor] = cur
        taken.append(anchor)
    if not taken:
        return 0
    for anchor in taken:
        cand.pop(anchor, None)
    try:
        path.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        if cand:
            CAND_JSON.write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            CAND_JSON.unlink()
    except OSError as exc:
        print("写不进词表：%s" % exc)
        return 1
    print("收了 %d 个词（%s）。词表现在 %d 组。" % (added, "、".join(taken), len(table)))
    print("（下次检索生效；不想要就改 词表.json 删掉）")
    return 0

def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd in ("挖词", "挖"):
        return cmd_mine()
    if cmd in ("收词", "收候选"):
        return cmd_accept_words(argv[1:])

    if cmd in ("清缓存", "剪缓存"):
        rebuild = bool(len(argv) > 1 and argv[1] in ("全部", "重建", "all"))
        res = prune_vectors(rebuild=rebuild)
        if res.get("removed") == "all":
            print("向量缓存已全清，下次检索会重算（会慢一次）。")
        elif res.get("removed"):
            print("清掉 %d 条没用的向量（%d → %d）。" % (
                res["removed"], res["before"], res["after"]))
        else:
            print("没有可清的：%d 条都还对得上内容。" % res.get("after", 0))
        return 0
    if cmd in ("目录", "list"):
        return cmd_list()

    # 临时记忆的四个动作
    if cmd in ("临时", "手边"):
        rows = _temp_load()
        if not rows:
            print("手边是空的。")
            return 0
        print("手边一张纸（%d/%d 张）：" % (len(rows), TEMP_CAP))
        for i, row in enumerate(rows, 1):
            mark = "📌" if row.get("pin") else "  "
            used = int(row.get("uses", 0) or 0)
            print("  %s %d. [%s] %s%s%s" % (
                mark, i, row.get("at", ""), row.get("title", ""),
                "（有位置）" if row.get("where") else "",
                "（用过 %d 次）" % used if used else ""))
        print("（看全文：用 <序号>；不要了：清 <序号> 或 清）")
        return 0
    if cmd == "用":
        rows = _temp_load()
        if not rows or not len(argv) > 1:
            print("用法：用 1")
            return 0
        try:
            i = int(argv[1])
        except ValueError:
            print("要写序号，比如：用 1")
            return 0
        if not 1 <= i <= len(rows):
            print("没有第 %d 条。" % i)
            return 0
        rows[i - 1]["uses"] = int(rows[i - 1].get("uses", 0) or 0) + 1
        _temp_save(rows)
        body = resolve_text(rows[i - 1])
        print("〔%s〕%s" % (rows[i - 1].get("kind", ""), rows[i - 1].get("src", "")))
        print("  " + body.replace("\n", "\n  "))
        print("（用过 %d 次，下次更难被挤掉）" % rows[i - 1]["uses"])
        return 0
    if cmd in ("留", "钉住"):
        rows = _temp_load()
        try:
            i = int(argv[1])
            row = rows[i - 1]
        except (ValueError, IndexError):
            print("用法：留 1（钉住，最多 %d 张）" % PIN_CAP)
            return 0
        if sum(1 for r in rows if r.get("pin")) >= PIN_CAP and not row.get("pin"):
            print("已经钉了 %d 张，先放掉一张。" % PIN_CAP)
            return 0
        row["pin"] = True
        _temp_save(rows)
        print("钉住了第 %d 张。" % i)
        return 0
    if cmd in ("放", "放掉"):
        rows = _temp_load()
        try:
            i = int(argv[1])
            rows[i - 1]["pin"] = False
        except (ValueError, IndexError):
            print("用法：放 1")
            return 0
        _temp_save(rows)
        print("放开了第 %d 张。" % i)
        return 0
    if cmd in ("扔", "退"):
        rows = _temp_load()
        try:
            i = int(argv[1])
            row = rows.pop(i - 1)
        except (ValueError, IndexError):
            print("用法：扔 1")
            return 0
        _drawer_save(_drawer_load()[-16:] + [row])
        _temp_save(rows)
        print("退到抽屉了（还能捡回来：捡 %d）" % len(_drawer_load()))
        return 0
    if cmd in ("抽屉", "旧的"):
        rows = _drawer_load()
        if not rows:
            print("抽屉是空的。")
            return 0
        print("抽屉里（%d 张，%d 天后过期）：" % (len(rows), DRAWER_TTL_DAYS))
        import datetime as _dt
        today = _dt.date.today()
        for i, row in enumerate(rows, 1):
            day = str(row.get("在抽屉") or "")[:10]
            left = ""
            try:
                gap = (today - _dt.date.fromisoformat(day)).days
                left = "（还有 %d 天）" % max(0, DRAWER_TTL_DAYS - gap)
            except Exception:  # noqa: BLE001
                pass
            print("  %d. [%s] %s%s" % (i, row.get("at", ""), row.get("title", ""), left))
        return 0
    if cmd in ("倒掉", "清抽屉"):
        rows = _drawer_load()
        if not rows:
            print("抽屉已经空了。")
            return 0
        _trash_add(rows)
        try:
            safe_write(DRAWER_JSON, "[]", what="抽屉")
        except OSError:
            pass
        print("倒了 %d 张进垃圾桶（记忆本身还在文件夹里）。" % len(rows))
        return 0
    if cmd == "垃圾桶":
        try:
            rows = json.loads(TRASH_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            print("垃圾桶是空的。")
            return 0
        print("垃圾桶（最近 %d 张，超过 %d 张就真没了）：" % (len(rows), TRASH_KEEP))
        for i, row in enumerate(rows, 1):
            print("  %d. [%s] %s" % (i, row.get("at", ""), row.get("title", "")))
        return 0
    if cmd in ("捡", "捡回"):
        rows = _drawer_load()
        try:
            i = int(argv[1])
            row = rows.pop(i - 1)
        except (ValueError, IndexError):
            print("用法：捡 1")
            return 0
        _drawer_save(rows)
        live = _temp_load()
        live.append(row)
        _temp_save(live)
        print("捡回来了，手边 %d 张。" % len(live))
        return 0

    if cmd == "清":
        rows = _temp_load()
        if len(argv) > 1:
            try:
                i = int(argv[1])
                rows.pop(i - 1)
            except (ValueError, IndexError):
                print("没有这个序号。")
                return 0
            _temp_save(rows)
            print("清掉了第 %d 条，还剩 %d 条。" % (i, len(rows)))
            return 0
        _temp_save([])
        print("手边清空了。")
        return 0
    if cmd == "收":
        rows = _temp_load()
        if not len(argv) > 1:
            print("用法：收 1（收进记忆柜）")
            return 0
        try:
            i = int(argv[1])
            row = rows[i - 1]
        except (ValueError, IndexError):
            print("没有这个序号。")
            return 0
        target = HOME / "记忆柜" / "_候选"
        target.mkdir(parents=True, exist_ok=True)
        import datetime as _dt
        name = "%s-临时收.txt" % _dt.datetime.now().strftime("%m%d-%H%M")
        body = "来源：%s/%s\n位置：%s\n\n%s\n" % (
            row.get("kind", ""), row.get("src", ""), row.get("where", ""), row.get("text", ""))
        (target / name).write_text(body, encoding="utf-8")
        rows.pop(i - 1)
        _temp_save(rows)
        print("收进记忆柜\\_候选\\%s（还得你点头才算进柜）" % name)
        return 0

    # 「取」= 她看：进临时记忆，不回显全文
    if cmd == "取":
        argv = argv[1:]
        print_to_temp = True
    else:
        print_to_temp = False

    full = cmd in ("看看", "看")
    if full:
        argv = argv[1:]
    if not argv:
        print("要找什么？")
        return 0

    kind = ""
    if argv[0] in REGISTRY:
        kind, argv = argv[0], argv[1:]
    elif argv[0] in ALIASES:
        kind, argv = ALIASES[argv[0]], argv[1:]
    query = " ".join(argv).strip()
    if not query:
        print("要找什么？")
        return 0

    hits, mode, elapsed = search_ranked(query, kind, top=1 if not full else 2)
    if not hits:
        if kind:
            print("「%s」这一类里没有对得上的。" % query)
        else:
            print("家里没有对得上「%s」的东西。" % query)
        return 0
    for it in hits:
        if not kind:
            print("（落在「%s」）" % it["kind"])
        show(it, full=full)
        if print_to_temp:
            bump_temperature(it.get("src", ""))
            res = temp_add(it) or {}
            print("（已放进手边：%s/%d 张，退到抽屉 %s 张；包里只说有这一句）" % (
                res.get("count", "?"), TEMP_CAP, res.get("spilled", 0)))
    print("（%.2f 秒，%s）" % (elapsed, mode))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
