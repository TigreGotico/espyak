import pytest

pytest.skip("canary: the suite skips, to prove the build report says so", allow_module_level=True)


def test_never_runs():
    assert False
