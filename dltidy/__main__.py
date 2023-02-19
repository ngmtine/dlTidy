import shutil
import os
import asyncio
import sys
import configparser


SETTING_FILE = "settings.ini"
INFOMATION_FILE = "info.ini"


def check_executable():
    """
    必要なコマンドが実行可能か確認
    """

    executable_list = ("ffmpeg", "AtomicParsley")
    for i in executable_list:
        if not shutil.which(i):
            raise Exception(f"Error: Failed to execute '{i}'")
    return


def read_settings(setting_file: str = SETTING_FILE) -> bool:
    """
    設定ファイル（settings.ini）の読み込み
    """

    # 設定ファイルの読み込み
    settings = {}
    ini = configparser.ConfigParser()
    ini.read(setting_file, encoding="utf-8_sig")
    settings["output_dir"] = ini["env"]["output_dir"]
    settings["max_concurrency"] = ini["env"]["max_concurrency"]

    return settings


def get_all_dirs(path):
    """
    path（output_dir）以下のディレクトリを列挙
    """

    # チルダでホームディレクトリを表している場合、展開
    path = os.path.expanduser(path)

    # path（output_dir）が存在しない場合
    if not os.path.isdir(path):
        raise FileNotFoundError(f"'{path}'が見つかりません")

    # 列挙
    dir_list = [path]
    for root, dirs, files in os.walk(path):
        for dir in dirs:
            dir_list.append(os.path.join(root, dir))

    return dir_list


async def read_dir_info(path):
    # cd
    os.chdir(path)

    # ディレクトリ内のinfo.iniの読み込み
    info = {}
    ini = configparser.ConfigParser()
    ini.read(INFOMATION_FILE, encoding="utf-8_sig")
    info["artist"] = ini["env"]["artist"]
    info["album"] = ini["env"]["album"]
    info["url_list"] = (
        ini["env"]["url_list"]
        .replace("\n", "")
        .replace(" ", "")
        .replace("　", "")
        .split(",")
    )

    if len(info["url_list"]) == 0:
        raise Exception("urlの指定がありません")

    return info


async def main():
    print("start!")

    try:
        check_executable()
        settings = read_settings()
        dir_list = get_all_dirs(settings["output_dir"])
        print(dir_list)
        for dir in dir_list:
            print(dir)
            await read_dir_info(dir)

    except Exception as e:
        print(e)
        sys.exit()


if __name__ == "__main__":
    # main()
    asyncio.run(main())
    print("end!")
