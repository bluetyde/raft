"""Skip markers for tests that read measured data sets which are not distributed with the repository
(redistribution permission not confirmed; see THIRD_PARTY_NOTICES.md). The data stay on the maintainer's machine."""
import pathlib
import unittest

_DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


def needs_data(name):
    """Skip when validation/data/<name> is absent."""
    return unittest.skipUnless((_DATA / name).is_dir(), f"validation/data/{name} is not distributed (see THIRD_PARTY_NOTICES.md)")
