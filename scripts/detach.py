#!/usr/bin/env python3
"""真正脱离终端的后台启动器：双击 fork + setsid，输出写文件。

用法: python3 detach.py <logfile> -- <cmd> [args...]
"""
import os
import sys


def main() -> int:
    log = sys.argv[1]
    assert sys.argv[2] == "--", "需要 -- 分隔符"
    cmd = sys.argv[3:]

    if os.fork() > 0:
        print(f"detached, log -> {log}")
        return 0
    os.setsid()
    if os.fork() > 0:
        os._exit(0)

    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.execvp(cmd[0], cmd)
    return 1


if __name__ == "__main__":
    sys.exit(main())
