import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_BIN = os.path.join(REPO, "oracle", "espeak-ng", "src", "espeak-ng")
ORACLE_DATA_ROOT = os.path.join(REPO, "oracle", "espeak-ng")


def oracle_available():
    return os.path.isfile(ORACLE_BIN)


@pytest.fixture(scope="session")
def oracle():
    """Run the espeak-ng oracle binary. Skips the test if the binary isn't built."""
    if not oracle_available():
        pytest.skip("espeak-ng oracle binary not built (see test/oracle/gen_oracle.py)")

    def run(text, lang="en", mode="ipa"):
        args = {"ipa": ["--ipa"], "x": ["-x"]}[mode]
        env = dict(os.environ, ESPEAK_DATA_PATH=ORACLE_DATA_ROOT)
        out = subprocess.run(
            [ORACLE_BIN, "-q", "-v", lang, *args],
            input=text, capture_output=True, text=True, env=env, timeout=30,
        )
        return out.stdout.strip()

    return run
