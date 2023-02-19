import shutil
import sys


def check_executable():
    executable_list = ("ffmpeg", "AtomicParsley")
    for i in executable_list:
        if not shutil.which(i):
            raise Exception(f"Error: Failed to execute '{i}'")
    return


def main():
    print("start!")

    try:
        check_executable()

    except Exception as e:
        print(e)
        sys.exit()


if __name__ == "__main__":
    main()
    print("end!")
