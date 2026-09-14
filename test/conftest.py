import os
import subprocess

import pytest

from oracle_source import find


def pytest_configure(config):
    """Refuse to run at all without a matching oracle.

    Skipping instead of failing makes an absent oracle indistinguishable from
    a passing comparison in the summary line a reader sees.
    """
    try:
        config.espyak_oracle = find()
    except RuntimeError as problem:
        raise pytest.UsageError(str(problem))


@pytest.fixture(scope="session")
def oracle(pytestconfig):
    """Run the espeak-ng oracle binary."""
    binary, data_root = pytestconfig.espyak_oracle

    def run(text, lang="en", mode="ipa"):
        args = {"ipa": ["--ipa"], "x": ["-x"]}[mode]
        env = dict(os.environ, ESPEAK_DATA_PATH=data_root)
        out = subprocess.run(
            [binary, "-q", "-v", lang, *args],
            input=text, capture_output=True, text=True, env=env, timeout=30,
        )
        return out.stdout.strip()

    return run
