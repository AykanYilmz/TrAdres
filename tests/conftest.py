"""Shared pytest configuration.

Hypothesis profiles: the default runs 100 random examples per property test,
which keeps the suite fast. For a deeper search run:

    HYPOTHESIS_PROFILE=thorough uv run pytest
"""

import os

from hypothesis import settings

settings.register_profile("default", max_examples=100)
settings.register_profile("thorough", max_examples=5000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
