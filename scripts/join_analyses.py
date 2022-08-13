from itertools import product
import os
import re
import subprocess
import typing as t

import sh

TAVERN_DIR = os.path.join(os.path.dirname((os.path.realpath(__file__))), "..")
OUT_DIR = os.path.join(TAVERN_DIR, "single_files")
os.makedirs(OUT_DIR, exist_ok=True)

# files in following list *appear* to have complete final measures but don't
# actually (e.g., the last measure is 3 beats of 4/4 and the initial ts is 6/8)
ALLOWED_COMPLETE_FINAL = [
    "B066_12_07e_a.krn",
    "B069_08_03b_a.krn",
    "B066_12_07e_b.krn",
    "B069_08_03b_b.krn",
    "B078_05_02b_a.krn",
    "B078_05_02b_b.krn",
    "M613_07_03c_a.krn",
    "M613_07_03c_b.krn",
]

ALLOWED_WRONG_PICKUP_LEN = [
    # last measure of 613_07_03c is 8/4 because of grace notes?
    "M613_07_04d_a.krn",
    "M613_07_04d_b.krn",
]


def get_measure_nums_and_durs(
    humdrum_file,
) -> t.Tuple[t.List[int], t.List[float]]:
    beat_output = subprocess.run(
        ["beat", "-s", humdrum_file], check=True, capture_output=True
    ).stdout.decode()
    measure_durs = list(
        map(float, re.findall(r"^\d+(?:\.\d+)?$", beat_output, re.MULTILINE))
    )
    measure_nums: list = list(
        map(int, re.findall(r"(?<=^=)\d+$", beat_output, re.MULTILINE))
    )
    if len(measure_nums) < len(measure_durs):
        measure_nums.insert(0, measure_nums[0] - 1)
    assert len(measure_nums) == len(measure_durs)
    return measure_nums, measure_durs


def get_sigs(preamble: str) -> t.Dict[str, str]:
    time_sig = re.search(r"^(\*M.*?)\t", preamble, re.MULTILINE).group(1)
    try:
        # key_sigs aren't necessarily at beginning of line
        # also some files seem to omit
        key_sig = re.search(r"[\n\t](\*k.*?)\t", preamble, re.MULTILINE).group(
            1
        )
    except AttributeError:
        key_sig = ""
    try:
        key_annot = re.search(
            r"^(\*[A-Ga-g#-]+:)\t", preamble, re.MULTILINE
        ).group(1)
    except AttributeError:
        key_annot = ""
    return {"time_sig": time_sig, "key_sig": key_sig, "key_annot": key_annot}


def has_pickup_and_incomplete_final_measure(
    measure_durs,
) -> t.Tuple[bool, bool]:
    """This function is heuristic: we just check if the first measure is
    shorter than the second measure, and if the last measure is shorter than
    the penultimate measure. This could fail if there are time-signature
    changes.
    """
    if len(measure_durs) == 1:
        return False, False
    pickup = measure_durs[0] < measure_durs[1]
    if len(measure_durs) == 2:
        return pickup, False
    # Sometimes, the a last incomplete measure is actually *longer* than the
    # previous measure, when time-signature change occurs immediately before
    # (e.g., if prev ts is 2/4, and new ts is 3/4, inc measure could be
    # 3 beats). Thus we check for equality rather than less-than. To be more
    # robust we would have to check the final time signature.
    return pickup, measure_durs[-1] != measure_durs[-2]


def get_n_spines(f_contents) -> int:
    spine_defs = re.findall(r"^\*\*.*$", f_contents, re.MULTILINE)
    assert len(spine_defs) == 1
    spine_defs = spine_defs[0]
    return len(spine_defs.split("\t"))


def get_annotator_files(joined_dir: str, annotator: str) -> str:
    # annotator = ["a", "b"][hash(joined_dir) % 2]
    files = (
        sh.fd(rf".*{annotator}\.krn", joined_dir, _tty_out=False)
        .stdout.decode()
        .strip()
        .split("\n")
    )
    return sorted(files)


def get_outpath_from_joined_dir(joined_dir: str, annotator: str) -> str:
    bits = joined_dir.split(os.path.sep)
    basename = f"{bits[-3]}_{bits[-2]}_annotator={annotator}.krn"
    return os.path.join(OUT_DIR, basename)


def join_files():
    joined = (
        sh.fd("Joined", TAVERN_DIR, _tty_out=False)
        .stdout.decode()
        .strip()
        .split("\n")
    )
    for joined_dir, annotator in product(joined, ("a", "b")):
        files = get_annotator_files(joined_dir, annotator)
        file_contents = [HumdrumContents(f) for f in files]
        accumulator = []
        for i, hcontents in enumerate(file_contents):
            error = None
            if i == 0:
                pass
            else:
                if hcontents.pickup:
                    try:
                        assert prev_hcontents.inc_final
                    except AssertionError:
                        try:
                            assert (
                                os.path.basename(prev_hcontents.humdrum_file)
                                in ALLOWED_COMPLETE_FINAL
                            )
                        except AssertionError:
                            error = "inc_final"
                    try:
                        assert (
                            prev_hcontents.measure_durs[-1]
                            + hcontents.measure_durs[0]
                            # There could be a time signature change either
                            #   after the pickup or before the incomplete measure
                            #   of the previous variation
                            in (
                                prev_hcontents.measure_durs[-2],
                                hcontents.measure_durs[1],
                            )
                        )
                    except:
                        try:
                            assert (
                                os.path.basename(hcontents.humdrum_file)
                                in ALLOWED_WRONG_PICKUP_LEN
                            )
                        except AssertionError:
                            error = "pickup_sum"
                if error is not None:
                    print(f"Error: {error}")
                    print("    Prev: " + prev_hcontents.humdrum_file)
                    print("    Next: " + hcontents.humdrum_file)
            # I think we can be confident that key annotations
            #   only change at the beginning of variations, but it is
            #   faster to just add them to all segments
            hcontents.add_key_annots()
            if i == 0:
                accumulator.append(hcontents.preamble)
            else:
                hcontents.add_first_ts_at_first_measure_line()
            accumulator.append(hcontents.body)
            prev_hcontents = hcontents
        body = "\n".join(accumulator)
        body = close_body(body)
        outpath = get_outpath_from_joined_dir(joined_dir, annotator)
        print(f"Writing {outpath}")
        with open(outpath, "w") as outf:
            outf.write(body)


def close_body(body):
    n_spines_at_end = body.rsplit("\n", maxsplit=1)[-1].count("\t") + 1
    return body + "\n" + "\t".join("*-" for _ in range(n_spines_at_end))


class HumdrumContents:
    def __init__(self, humdrum_file):
        self.humdrum_file = humdrum_file
        with open(humdrum_file) as inf:
            f_contents = inf.read()
        self.n_spines = get_n_spines(f_contents)
        self.measure_nums, self.measure_durs = get_measure_nums_and_durs(
            humdrum_file
        )
        self.pickup, self.inc_final = has_pickup_and_incomplete_final_measure(
            self.measure_durs
        )
        # TODO need to fix: kern doesn't need to start with '='
        # in fact I think we want to include everything after the spine declarations
        # then later move the time signature
        self.preamble, remainder = re.split(r"\n(?==)", f_contents, maxsplit=1)
        self.sigs = sigs = get_sigs(self.preamble)
        remainder, self.coda = re.split(r"(?:\*-\t?)+", remainder)
        # in some files spines begin with "=-" and end with "==";
        # we want to strip this out
        remainder = re.sub(r"^(=-\t?)+", "", remainder, re.MULTILINE)
        remainder = re.sub(r"(==\t?)+?", "", remainder)
        self.body = remainder.strip()

    def add_first_ts_at_first_measure_line(self):
        """On all segments except the first, we want to move the ts to just
        *after* the first barline so that the previous measure will
        sum up to the right amount and the segment will have the right ts."""
        m = re.search(r"^=[^-].*\n", self.body, re.MULTILINE)
        n_spines_here = m.group(0).count("\t") + 1
        ts = (
            "\t".join(self.sigs["time_sig"] for _ in range(n_spines_here))
            + "\n"
        )
        self.body = self.body[: m.end()] + ts + self.body[m.end() :]

    def add_key_annots(self):
        self.body = "\n".join(
            [
                "\t".join([self.sigs["key_sig"]] * self.n_spines),
                "\t".join([self.sigs["key_annot"]] * self.n_spines),
                self.body,
            ]
        )


# Tests


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


def test_humdrum_contents():
    files = get_joined_kern_files()
    for f in files:
        try:
            h = HumdrumContents(f)
        except subprocess.CalledProcessError:
            print(f)
            continue


def count_spines():
    """I want to check whether every score has the same number of spines
    throughout, which will greatly simplify the task of joining them.

    Yes! Every score has the same number of spines throughout :)

    (However, some scores have more spines than others.)
    """
    joined = (
        sh.fd("Joined", TAVERN_DIR, _tty_out=False)
        .stdout.decode()
        .strip()
        .split("\n")
    )
    for subdir in joined:
        files = (
            sh.fd(r".*\.krn", subdir, _tty_out=False)
            .stdout.decode()
            .strip()
            .split("\n")
        )
        expected_n_spines = None
        for f in files:
            print(f)
            with open(f) as inf:
                f_contents = inf.read()
                spine_defs = re.findall(r"^\*\*.*$", f_contents, re.MULTILINE)
                assert len(spine_defs) == 1
                spine_defs = spine_defs[0]
                n_spines = len(spine_defs.split("\t"))
                if expected_n_spines is None:
                    expected_n_spines = n_spines
                else:
                    assert n_spines == expected_n_spines


def verify_spine_types():
    """Some spines had "**kern" where they should have had "**harm";
    want to find all such cases."""
    joined = (
        sh.fd("Joined", TAVERN_DIR, _tty_out=False)
        .stdout.decode()
        .strip()
        .split("\n")
    )
    for subdir in joined:
        files = (
            sh.fd(r".*\.krn", subdir, _tty_out=False)
            .stdout.decode()
            .strip()
            .split("\n")
        )
        for f in files:
            with open(f) as inf:
                f_contents = inf.read()

                spine_defs = re.findall(
                    r"^\*\*function\t\*\*harm\t(?:\*\*kern\t?){2,}$",
                    f_contents,
                    re.MULTILINE,
                )
                try:
                    assert len(spine_defs) == 1
                except AssertionError:
                    print(f)


def test_join_files():
    join_files()


if __name__ == "__main__":
    # verify_spine_types()
    test_join_files()
    # test_humdrum_contents()

    # dir_ = "Mozart/K025/Joined/"
    # humdrum_files = [
    #     os.path.join(TAVERN_DIR, dir_, p)
    #     for p in os.listdir(os.path.join(TAVERN_DIR, dir_))
    # ]
    # humdrum_files.sort()
    # for i, f in enumerate(humdrum_files):
    #     print(f)
    #     HumdrumContents(f)
