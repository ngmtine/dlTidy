import shutil
import os
import asyncio
import sys
import configparser
from concurrent.futures import ThreadPoolExecutor
import tqdm

from yt_dlp import YoutubeDL

SETTING_FILE = "settings.ini"
INFOMATION_FILE = "info.ini"
MAX_PROCESS = 12


def check_executable() -> bool:
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


def get_all_dirs(path: str) -> list[str]:
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


def call_ydl_extract_info(url: str) -> list[dict]:
    """
    Use youtube-dl to fetch information from url
    """
    opts = {
        "simulate": True,
        "ignoreerrors": True,
        "quiet": True,
        "extract_flat": True,
    }
    with YoutubeDL(opts) as ydl:
        result = ydl.extract_info(url)
    if result != None:
        return result["entries"]
    else:
        return []


def call_ydl_download_m4a(entry: dict) -> bool:
    """
    Use youtube-dl to download m4a
    """
    videoId = entry["id"]
    output_dir = entry["download_dir"]

    opts = {
        # "simulate": True,
        "ignoreerrors": True,
        "quiet": True,
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "format": "bestaudio[ext=m4a]",
        "download_archive": f"{output_dir}/downloaded.txt",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegMetadata"},  # postprocessors must be written in this order #30101
            {"key": "EmbedThumbnail"},
        ],
    }

    with YoutubeDL(opts) as ydl:
        ydl.download([videoId])

    return


class EntriesSingleton:
    """
    対象となる全てのentriesを集約するためのシングルトンクラス
    """

    _instance = None

    def __init__(self, entries_list=[]):
        self.entries_list.extend(entries_list)

    def __new__(cls, *args, **kwargs):

        if not cls._instance:
            # 初回呼び出し
            cls.entries_list = []
            cls._instance = super().__new__(cls)

        return cls._instance


class DirExecutor:
    def __init__(self, path):
        self.path = path

    async def async_init(self):
        try:
            self.dir_config = await self.read_dir_config()
            self.entries_list = await self.fetch_entries()
            EntriesSingleton(self.entries_list)
        except Exception as e:
            pass

    async def read_dir_config(self) -> dict:  # dict{"artist": str, "album": str, "ulr_list": list[str]}
        """
        self.pathに移動し、設定ファイル（info.ini）を読み取り、辞書型configを返す
        """
        # cd
        os.chdir(self.path)

        # 対象ディレクトリに設定ファイルが存在しない場合、なにもしない
        if not os.path.isfile(INFOMATION_FILE):
            raise FileNotFoundError()

        # ディレクトリ内のinfo.iniの読み込み
        config = {}
        ini = configparser.ConfigParser()
        ini.read(INFOMATION_FILE, encoding="utf-8_sig")
        config["artist"] = ini["env"]["artist"]
        config["album"] = ini["env"]["album"]
        config["url_list"] = ini["env"]["url_list"].replace("\n", "").replace(" ", "").replace("　", "").split(",")

        # 値が存在しない場合
        if len(config["url_list"]) == 0:
            # raise Exception("urlの指定がありません")
            config["url"] = "unknown"
        if len(config["artist"]) == 0:
            config["artist"] = "unknown"
        if len(config["album"]) == 0:
            config["album"] = "unknown"

        return config

    async def fetch_entries(self) -> list:  # list[dict{"download_dir": str, "url": str, "title": str, ...}]
        """
        与えられたurl（youtubeのプレイリストurl等を想定）をyt-dlpに投げ、動画データのリストを取得する
        動画データにはyt-dlpで得られた情報に加え、download_dirも追加する
        """
        dir_entries = []
        for url in self.dir_config["url_list"]:
            url_entries = call_ydl_extract_info(url)
            dir_entries.extend(url_entries)

        # download_dir追加
        dir_entries = [{**d, "download_dir": self.path} for d in dir_entries]

        return dir_entries


def tqdm_wrapper_for_ThreadPoolExecutor(func, iterable):
    """
    ThreadPoolExecutor() の進捗を可視化するためのtqdmのラッパー
    """
    with ThreadPoolExecutor(max_workers=MAX_PROCESS) as executor:
        list(tqdm.tqdm(executor.map(func, iterable), total=len(iterable)))


async def main():
    print("start!")

    try:
        # このスクリプトが依存するプログラムの存在チェック
        check_executable()

        # グローバルな設定の読み込み
        settings = read_settings()

        # output_dir以下のディレクトリを列挙
        dir_list = get_all_dirs(settings["output_dir"])

        # コルーチンのリスト作成
        tasks = []
        for _dir in dir_list:
            dir_executor = DirExecutor(_dir)
            task = asyncio.create_task(dir_executor.async_init())
            tasks.append(task)

        # コルーチンを並行実行
        await asyncio.gather(*tasks)

        # シングルトンインスタンス化
        entries_singleton = EntriesSingleton()

        # dlの並行実行
        tqdm_wrapper_for_ThreadPoolExecutor(call_ydl_download_m4a, entries_singleton.entries_list)

    except Exception as e:
        print(e)
        pass


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()

    asyncio.run(main())
    print("end!")

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"elapsed time: {elapsed_time:.3f} seconds")
