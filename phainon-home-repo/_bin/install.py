# -*- coding: utf-8 -*-
r"""
安家 —— 查 Python、定路径、试跑一次

用法：
  python _水电\安家.py

只做三件事，别的都不改。
"""
import os
import subprocess
import sys

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # _bin 的上一层


def main():
    print("=" * 42)
    print("    安家 —— 白厄的家")
    print("=" * 42)
    print()
    print("这个脚本只做三件事：查 Python、定路径、试跑一次。")
    print()

    v = sys.version_info
    if v < (3, 9):
        print("  你的 Python 是 %d.%d，要 3.9 以上。" % (v[0], v[1]))
        print("  去 python.org 装一个新的。")
        return 1
    print("[1/3] Python %d.%d.%d，可以。" % v[:3], flush=True)

    print()
    print("[2/3] 家放在哪？")
    print("  直接回车 = 就放在现在这个文件夹：")
    print("  " + HOME)
    try:
        ans = input("  路径：").strip().strip('"')
    except EOFError:
        ans = ""
    home = ans or HOME
    if not os.path.isdir(home):
        print("  这个目录不存在：%s" % home)
        return 1
    print("  用：%s" % home, flush=True)

    print()
    print("[3/3] 设环境变量 BAI_E_HOME")
    if os.name == "nt":
        try:
            subprocess.run(["setx", "BAI_E_HOME", home],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            print("  设好了（新开的窗口才认它，本窗口下面直接用）。")
        except Exception:
            print("  没设成，不要紧——脚本会按自己所在的目录找家。")
    else:
        print("  非 Windows，请自己加一行：")
        print("  export BAI_E_HOME=\"%s\"" % home)

    print()
    print("试跑一次 ...", flush=True)
    env = dict(os.environ)
    env["BAI_E_HOME"] = home
    r = subprocess.run([sys.executable, "-X", "utf8",
                        os.path.join(home, "_水电", "拼包.py"), "轮", "你好。"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(r.stdout or "")
    sys.stdout.flush()
    if r.returncode != 0:
        print()
        print("试跑没成。把上面的报错贴给能看代码的人。")
        return 1

    print()
    print("=" * 42)
    print("    安好了。")
    print("=" * 42)
    print()
    print("以后每一轮，跑这一句：")
    print('  python "%s" 轮 "<他刚说的话>"' % os.path.join(home, "_水电", "拼包.py"))
    print()
    print("然后把 _水电\\唤醒包.txt 整个贴进对话。")
    print("（如果你用的是带工具的 AI，这句可以直接交给它。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
