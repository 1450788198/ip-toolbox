"""端到端真机验证：启动应用 → 系统事件点击菜单栏图标 → 面板弹出 → 截屏

这是最接近真实用户操作的验证路径（真实点击状态栏图标）。
运行（在项目根目录）：
  .venv/bin/python tests/e2e_capture.py light docs/v1.1.1/e2e-light.png
注意：会短暂启动一个应用实例，结束后自动退出。
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEME = sys.argv[1] if len(sys.argv) > 1 else "light"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/e2e.png"
os.environ["IP_TOOLBOX_APPEARANCE"] = THEME   # 备用；实际仍写 settings

# 用临时目录做独立数据目录，避免污染用户配置
os.environ["IP_TOOLBOX_DATA_DIR"] = "/tmp/ip-toolbox-e2e"


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def main():
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    os.makedirs("/tmp/ip-toolbox-e2e", exist_ok=True)
    subprocess.run(["caffeinate", "-u", "-t", "3"])

    env = dict(os.environ)
    proc = subprocess.Popen(
        [os.path.join(ROOT, ".venv/bin/python"), "-c",
         "import sys; sys.path.insert(0, %r); "
         "from ui.main_window import run_app; run_app()" % ROOT],
        cwd=ROOT, env=env,
        stdout=open("/tmp/ip-toolbox-e2e/app.log", "w"), stderr=subprocess.STDOUT)
    try:
        time.sleep(5)
        # 找到本进程的状态栏图标（QSystemTrayIcon → menu bar 2）
        pid = proc.pid
        script = f'''
tell application "System Events"
    set p to first process whose unix id is {pid}
    tell p
        set sb to menu bar items of menu bar 2
        if (count of sb) = 0 then return "NO_STATUS_ITEM"
        click item 1 of sb
        return "CLICKED"
    end tell
end tell'''
        r = sh(["osascript", "-e", script], timeout=30)
        print("osascript:", r.stdout.strip() or r.stderr.strip())
        if "CLICKED" not in r.stdout:
            return 1
        time.sleep(1.6)
        full = "/tmp/ip-toolbox-e2e/full.png"
        subprocess.run(["screencapture", "-x", full], check=False)

        from PySide6.QtGui import QImage
        img = QImage(full)
        if img.isNull():
            print("ERROR 读取截图失败（录屏权限？）")
            return 1
        # 全屏截图原样保存（含菜单栏），按宽度等比裁掉下半部分以外的空白
        img.copy(0, 0, img.width(), min(img.height(), 1400)).save(OUT)
        gray = img.convertToFormat(QImage.Format_Grayscale8)
        mx = 0
        for y in range(0, gray.height(), 60):
            for x in range(0, gray.width(), 60):
                mx = max(mx, gray.pixelColor(x, y).red())
        print(f"captured -> {OUT}  size={img.width()}x{img.height()}  亮度峰值={mx}")
        if mx < 20:
            print("WARN 屏幕疑似锁定，此图不可作为交付截图")
            return 1
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
