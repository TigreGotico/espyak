import pytest


@pytest.mark.skip(reason="canary: this test skips, to prove the build report says so")
def test_skipped_on_purpose():
    assert False
