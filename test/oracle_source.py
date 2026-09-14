"""Locate the espeak-ng build the fixtures were generated against.

espyak reproduces espeak-ng byte for byte, so every comparison is only as good
as the build it compares to. A build on PATH takes precedence over one in the
tree, so CI can supply it without the checkout carrying a copy.
"""
import functools
import os
import re
import shutil
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_TREE_BIN = os.path.join(REPO, "oracle", "espeak-ng", "src", "espeak-ng")
IN_TREE_DATA = os.path.join(REPO, "oracle", "espeak-ng")

with open(os.path.join(REPO, "test", "oracle", "VERSION")) as f:
    VERSION, COMMIT = f.read().split()[:2]

MISSING = f"""\
No espeak-ng {VERSION} oracle available.

The oracle tests compare espyak's output against espeak-ng byte for byte,
which is the only thing this library promises. Without the binary they cannot
run, and a run that omits them reports success for half a suite, which reads
exactly like a clean result.

Either put espeak-ng {VERSION} on PATH with ESPEAK_DATA_PATH pointing at its
data, or build it in the tree:

    git clone https://github.com/espeak-ng/espeak-ng oracle/espeak-ng
    cd oracle/espeak-ng && git checkout {COMMIT}
    ./autogen.sh && ./configure && make
"""

UNUSABLE = """\
espeak-ng at {path} is not usable as an oracle: {why}.

Every candidate was rejected. A build whose data directory is missing still
reports its version, so the check is a real conversion rather than a version
string alone.
"""


def _rejection(binary, data_root):
    """Return None if this build is a usable oracle, else why it is not."""
    env = dict(os.environ, ESPEAK_DATA_PATH=data_root)
    version = subprocess.run([binary, "--version"], capture_output=True,
                             text=True, env=env, timeout=30).stdout
    found = re.search(r"text-to-speech:\s*(\S+)", version)
    if not found:
        return "it does not report a version"
    if found.group(1) != VERSION:
        return (f"it reports {found.group(1)}, but the fixtures were generated "
                f"against {VERSION}, so a comparison would measure the "
                f"difference between two espeak-ng releases")
    spoken = subprocess.run([binary, "-q", "-v", "en", "--ipa"], input="test",
                            capture_output=True, text=True, env=env, timeout=30)
    if not spoken.stdout.strip():
        return (f"it produces no output for a known word; its data directory "
                f"is probably wrong (ESPEAK_DATA_PATH={data_root!r})")
    return None


@functools.lru_cache(maxsize=None)
def find():
    """Return (binary, data root) for a matching build, or raise RuntimeError."""
    candidates = []
    on_path = shutil.which("espeak-ng")
    if on_path:
        candidates.append((on_path, os.environ.get("ESPEAK_DATA_PATH", "")))
    if os.path.isfile(IN_TREE_BIN):
        candidates.append((IN_TREE_BIN, IN_TREE_DATA))
    if not candidates:
        raise RuntimeError(MISSING)

    problems = []
    for binary, data_root in candidates:
        why = _rejection(binary, data_root)
        if why is None:
            return binary, data_root
        problems.append((binary, why))

    binary, why = problems[0]
    raise RuntimeError(UNUSABLE.format(path=binary, why=why))
