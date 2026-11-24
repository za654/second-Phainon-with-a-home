# -*- coding: utf-8 -*-
r"""
备份 —— 把整个家打成一个包

用法：
  备份.py          打一份，放 E:\白厄备份\
  备份.py 看       看最近几份

不背：__pycache__、_水电 里的编译缓存
留最近 10 份，多的自己删。
"""
import os
import sys
import time
import zipfile

HOME = os.environ.get("BAI_E_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("BAI_E_BACKUP") or os.path.join(HOME, "_备份")
SKIP_DIR = {"__pycache__", "_备份", "_python"}


def main():
    a = sys.argv[1:]
    os.makedirs(OUT, exist_ok=True)
    if a and a[0] == "看":
        fs = sorted([f for f in os.listdir(OUT) if f.endswith(".zip")], reverse=True)
        if not fs:
            print("还没备份过。")
            return 0
        for f in fs[:6]:
            p = os.path.join(OUT, f)
            print("%s　%.1f MB" % (f, os.path.getsize(p) / 1048576))
        return 0

    name = "白厄-%s.zip" % time.strftime("%Y%m%d-%H%M")
    path = os.path.join(OUT, name)
    n = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(HOME):
            dirs[:] = [d for d in dirs if d not in SKIP_DIR]
            for f in files:
                if f.endswith(".pyc"):
                    continue
                p = os.path.join(root, f)
                try:
                    z.write(p, os.path.relpath(p, HOME))
                    n += 1
                except OSError:
                    pass
    print("备好了：%s" % path)
    print("文件 %d 个，%.2f MB" % (n, os.path.getsize(path) / 1048576))

    fs = sorted([f for f in os.listdir(OUT) if f.endswith(".zip")], reverse=True)
    for old in fs[10:]:
        try:
            os.remove(os.path.join(OUT, old))
            print("删掉旧的：%s" % old)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
