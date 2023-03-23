import asyncio
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

import tomllib
import tqdm
from mutagen.mp4 import MP4
from yt_dlp import YoutubeDL

SETTING_FILE = "settings.toml"
INFOMATION_FILE = "info.toml"
MAX_PROCESS = 12
TRACKNUMBER_ORDER_DESCENDING = True


def check_executable() -> bool:
    """
    必要なコマンドが実行可能か確認
    """

    executable_list = ("ffmpeg", "AtomicParsley")
    for i in executable_list:
        if not shutil.which(i):
            raise Exception(f"Error: Failed to execute '{i}'")
    return True


def read_settings(setting_file: str = SETTING_FILE) -> bool:
    """
    設定ファイル（settings.toml）の読み込み
    """

    with open(SETTING_FILE, "rb") as f:
        settings = tomllib.load(f)

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
        """
        __init__()をasyncで回すためのラッパーメソッド
        """
        try:
            self.dir_config = await self.read_dir_config()
            self.url_list = self.dir_config["url_list"]
            self.artist = self.dir_config["artist"]
            self.album = self.dir_config["album"]

            # dlする動画urlのリストを取得
            self.entries_list = await self.fetch_entries()

            # fetch_entries()で取得したurlリストを、全ディレクトリについて集約するシングルトンクラスに登録
            EntriesSingleton(self.entries_list)
        except Exception as e:
            pass

    async def read_dir_config(self) -> dict:  # dict{"artist": str, "album": str, "ulr_list": list[str]}
        """
        self.pathに移動し、設定ファイル（info.toml）を読み取り、辞書型configを返す
        """
        # cd
        os.chdir(self.path)

        # 対象ディレクトリに設定ファイルが存在しない場合、なにもしない
        if not os.path.isfile(INFOMATION_FILE):
            raise FileNotFoundError()

        try:
            with open(INFOMATION_FILE, "rb") as f:
                config = tomllib.load(f)
                # info.toml内の記述が1行でも不正だとここでコケるのに注意

            # 値が存在しない場合
            if len(config["url_list"]) == 0:
                # raise Exception("urlの指定がありません")
                config["url_list"] = []
            if len(config["artist"]) == 0:
                config["artist"] = "unknown"
            if len(config["album"]) == 0:
                config["album"] = "unknown"

        # except tomllib.TomlDecodeError as e:
        except Exception as e:
            print(e)
            print(f"└→  {self.path} の {INFOMATION_FILE} が不正です")
            config = {}
            config["url_list"] = []
            config["artist"] = "unknown"
            config["album"] = "unknown"

        return config

    async def fetch_entries(self) -> list:  # list[dict{"download_dir": str, "url": str, "title": str, ...}]
        """
        与えられたurl（youtubeのプレイリストurl等を想定）をyt-dlpに投げ、取得した動画データ（辞書型）をリストにして返す
        動画データにはyt-dlpで得られた情報に加え、download_dirも追加する
        """
        dir_entries = []
        for url in self.dir_config["url_list"]:
            url_entries = call_ydl_extract_info(url)
            dir_entries.extend(url_entries)

        # download_dir追加
        dir_entries = [{**d, "download_dir": self.path} for d in dir_entries]

        return dir_entries

    async def tagging_m4a(self):
        """
        Use mutagen for tagging
        """

        os.chdir(self.path)
        m4a_list = []
        for filename in os.listdir(os.getcwd()):
            if filename.endswith(".m4a"):
                v = MP4(filename)
                upload_date = v["\xa9day"] if "\xa9day" in v else 0
                m4a_list.append({"filename": filename, "upload_date": upload_date})

        if len(m4a_list) == 0:
            return

        m4a_list_sorted = sorted(m4a_list, key=lambda x: x["upload_date"], reverse=TRACKNUMBER_ORDER_DESCENDING)

        for idx, video in enumerate(m4a_list_sorted):
            audio = MP4(video["filename"])
            audio["\xa9nam"] = ""  # title
            audio["\xa9ART"] = self.artist  # artist
            audio["\xa9alb"] = self.album  # album
            # audio["\xa9gen"] = GENRE  # genre
            audio["trkn"] = [(idx + 1, 0)]  # tracknumber
            audio.save()

        return


def tqdm_wrapper_for_ThreadPoolExecutor(func, iterable):
    """
    ThreadPoolExecutor() の進捗を可視化するためのtqdmのラッパー
    """
    with ThreadPoolExecutor(max_workers=MAX_PROCESS) as executor:
        list(tqdm.tqdm(executor.map(func, iterable), total=len(iterable)))


async def main():
    try:
        # このスクリプトが依存するプログラムの存在チェック
        check_executable()

        # グローバルな設定の読み込み
        settings = read_settings()

        # output_dir以下のディレクトリを列挙
        dir_list = get_all_dirs(settings["output_dir"])

        # dir_executorのリスト作成
        dir_executor_list = []
        for _dir in dir_list:
            dir_executor_list.append(DirExecutor(_dir))

        # コルーチンのリスト作成
        task_list = []
        for dir_executor in dir_executor_list:
            task = asyncio.create_task(dir_executor.async_init())
            task_list.append(task)

        # コルーチンを並行実行（ここでasync defしたコンストラクタを回す）
        await asyncio.gather(*task_list)

        # dlの並行実行
        entries_singleton = EntriesSingleton()
        tqdm_wrapper_for_ThreadPoolExecutor(call_ydl_download_m4a, entries_singleton.entries_list)
        print("download task finished!")

        del task, task_list
        # コルーチンのリスト作成
        task_list = []
        for dir_executor in dir_executor_list:
            task = asyncio.create_task(dir_executor.tagging_m4a())
            task_list.append(task)

        # コルーチンを並行実行（タグ付け）
        await asyncio.gather(*task_list)
        print("tagging task finished!")

    except Exception as e:
        print(e)


if __name__ == "__main__":
    import time

    start_time = time.perf_counter()

    print("start!")
    asyncio.run(main())
    print("end!")

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"elapsed time: {elapsed_time:.3f} seconds")
