"""pytest configuration — anyio backend pro async tests."""
import os
import sys

# Make src importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
