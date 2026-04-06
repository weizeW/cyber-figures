#!/usr/bin/env python3
"""
Terminal Danmaku - 终端弹幕效果
用法: python3 danmaku.py "弹幕1" "弹幕2" "弹幕3"
"""

import sys
import os
import time
import random
import threading
import shutil

# ANSI colors
COLORS = [
    "\033[97m",   # white
    "\033[93m",   # yellow
    "\033[96m",   # cyan
    "\033[91m",   # red
    "\033[92m",   # green
    "\033[95m",   # magenta
]
BOLD = "\033[1m"
RESET = "\033[0m"

def get_terminal_size():
    cols, rows = shutil.get_terminal_size((80, 24))
    return cols, rows

def move_cursor(row, col):
    sys.stdout.write(f"\033[{row};{col}H")

def save_cursor():
    sys.stdout.write("\033[s")

def restore_cursor():
    sys.stdout.write("\033[u")

def hide_cursor():
    sys.stdout.write("\033[?25l")

def show_cursor():
    sys.stdout.write("\033[?25h")

def fly_danmaku(text, row, speed, color):
    cols, _ = get_terminal_size()
    display_text = f"{BOLD}{color}{text}{RESET}"
    text_len = len(text)

    for col in range(cols, -text_len - 1, -2):
        save_cursor()
        move_cursor(row, max(1, col))
        if col >= 1:
            # Clear previous position
            sys.stdout.write(" " * (text_len + 2))
            move_cursor(row, max(1, col))
            sys.stdout.write(display_text)
        sys.stdout.flush()
        restore_cursor()
        sys.stdout.flush()
        time.sleep(speed)

    # Clean up the line
    save_cursor()
    move_cursor(row, 1)
    sys.stdout.write(" " * (cols - 1))
    restore_cursor()
    sys.stdout.flush()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 danmaku.py '弹幕1' '弹幕2' ...")
        sys.exit(1)

    messages = sys.argv[1:]
    cols, rows = get_terminal_size()

    # Use top portion of terminal for danmaku
    available_rows = list(range(1, min(rows - 2, 8)))

    hide_cursor()

    try:
        threads = []
        for i, msg in enumerate(messages):
            row = random.choice(available_rows)
            color = random.choice(COLORS)
            speed = random.uniform(0.02, 0.05)
            delay = i * 0.8  # stagger start times

            def delayed_fly(m=msg, r=row, s=speed, c=color, d=delay):
                time.sleep(d)
                fly_danmaku(m, r, s, c)

            t = threading.Thread(target=delayed_fly, daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

    finally:
        show_cursor()
        sys.stdout.write("\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
