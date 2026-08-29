"""PyInstaller 打包脚本。
用法: uv run build.py
输出: dist/nga-search (macOS/Linux) 或 dist/nga-search.exe (Windows)
"""
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).parent
SEP = ";" if sys.platform == "win32" else ":"


def build():
    src = PROJECT / "src" / "nga_search"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "nga-search",
        "--paths", str(PROJECT / "src"),
        "--add-data", f"{PROJECT / 'web' / 'templates'}{SEP}web/templates",
        "--add-data", f"{PROJECT / 'web' / 'static'}{SEP}web/static",
        "--console",
        "--clean",
        "--distpath", str(PROJECT / "dist"),
        "--workpath", str(PROJECT / "build"),
        "--specpath", str(PROJECT / "build"),
        str(PROJECT / "run.py"),
    ]
    print(f"[BUILD] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT), check=True)
    print("[OK] Build complete, output in dist/")


if __name__ == "__main__":
    build()