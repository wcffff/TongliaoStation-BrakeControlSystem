import os
import subprocess
import shutil


def build_executable():
    """构建可执行文件"""
    exe_name = f"main.exe"
    print(f"正在构建 {exe_name}...")

    # 构建命令
    cmd = [
        "pyinstaller",
        "--onefile",
        "--clean",
        "--windowed",
        "--icon=./uis/images/icon.ico",
        "--distpath=./dist",
        "--add-data", "data/media;data/media",
        "main.py",
    ]
    print("运行的命令：", cmd)
    # 执行构建命令
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    if result.returncode == 0:
        print(f"成功构建 {exe_name}")
        # 将生成的可执行文件移动到根目录
        dist_path = os.path.join("dist", exe_name)
        if os.path.exists(dist_path):
            shutil.move(dist_path, exe_name)
            print(f"已将 {exe_name} 移动到当前目录")
    else:
        print(f"构建 {exe_name} 失败:")
        print(result.stderr)


def clean_build_files():
    """清理构建过程中生成的临时文件"""
    folders_to_remove = ["build", "dist", "__pycache__"]
    file_to_remove = "main.spec"

    for folder in folders_to_remove:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"已删除文件夹: {folder}")

    if os.path.exists(file_to_remove):
        os.remove(file_to_remove)
        print(f"已删除文件: {file_to_remove}")


if __name__ == "__main__":
    # 确保构建目录存在
    if not os.path.exists("dist"):
        os.makedirs("dist")

    build_executable()

    # 清理构建文件
    clean_build_files()

    print("构建完成！")
