import os
import sys
from tempfile import mkstemp
import sh
import argparse
import traceback, sys
import typing as t

TAVERN_DIR = os.path.join(os.path.dirname((os.path.realpath(__file__))), "..")
OUT_DIR = os.path.join(TAVERN_DIR, "single_files")


class HumException(Exception):
    pass


def get_joined_kern_files() -> t.List[str]:
    joined = (
        sh.fd("Joined", TAVERN_DIR, _tty_out=False)
        .stdout.decode()
        .strip()
        .split("\n")
    )
    out = []
    for subdir in joined:
        files = (
            sh.fd(r".*\.krn", subdir, _tty_out=False)
            .stdout.decode()
            .strip()
            .split("\n")
        )
        out.extend(files)
    return out


def test_bits(func):
    failures = 0
    for f in sorted(get_joined_kern_files()):
        try:
            func(f)
            print(".", end="", flush=True)
        except sh.ErrorReturnCode_1:
            import traceback, sys

            exc_type, exc_value, exc_traceback = sys.exc_info()
            print("\n" + f)
            print(exc_value.stdout.decode())
            print(exc_value.stderr.decode())
            failures += 1
    print(f"{failures} total failures")


def test_whole(func):
    failures = 0
    for f in sorted(
        [
            os.path.join(OUT_DIR, f)
            for f in os.listdir(OUT_DIR)
            if f.endswith(".krn")
        ]
    ):
        try:
            func(f)
        except sh.ErrorReturnCode_1:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(f)
            print(exc_value.stdout.decode())
            print(exc_value.stderr.decode())
            failures += 1
        except HumException:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(f)
            print(exc_value)
            failures += 1
        except sh.SignalException_SIGSEGV:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(f)
            print("Segmentation fault or similar")
            print(exc_value.stdout.decode())
            print(exc_value.stderr.decode())
            failures += 1
    print(f"{failures} total failures")


# def iter_through(path, f):
#     """This isn't helpful; it will fail at the same line as --whole but take much longer."""
#     with open(path) as inf:
#         data = inf.readlines()
#     contents = []
#     i = 0
#     while not data[i] or data[i][0] in ("*", "!"):
#         contents.append(data[i])
#         i += 1
#     _, temppath = mkstemp(suffix=".krn")
#     while i < len(data):
#         contents.append(data[i])
#         with open(temppath, "w") as outf:
#             outf.write("".join(contents))
#         try:
#             f("-i", "**kern", temppath)
#         except:
#             print(f"failed at line {i + 1}")
#             os.remove(temppath)
#             sys.exit()
#         i += 1
#         print(".", end="", flush=True)
#     os.remove(temppath)


def hum2mid(*args):
    return sh.hum2mid(sh.extractx("-i", "**kern", *args))


def scorext(*args):
    return sh.scorext("-nL", *args)


def verovio(*args):
    # we want to convert the harm spines to kern spines so that they will be
    #   checked for durations as well
    res = sh.verovio(sh.shed(*args, "-e", "s/harm/kern/X"), "-", "-o", "-")
    if res.stderr:
        stderr = res.stderr.decode()
        stderr = stderr.replace("[Message] Converting markup...", "")
        stderr = stderr.replace("[Message] Converting analytical markup...", "")
        stderr = stderr.strip()
        if stderr:
            raise HumException(stderr)
    return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--command",
        type=str,
        choices=("hum2mid", "scorext", "verovio"),
        default="hum2mid",
    )
    parser.add_argument("--whole", action="store_true")
    parser.add_argument("--bits", action="store_true")
    # parser.add_argument("--iter-through")
    args = parser.parse_args()
    f = {"hum2mid": hum2mid, "scorext": scorext, "verovio": verovio}[
        args.command
    ]
    if args.whole:
        test_whole(f)
    if args.bits:
        test_bits(f)
    # if args.iter_through:
    #     iter_through(args.iter_through, f)
