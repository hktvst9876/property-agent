"""
tests/conftest.py — keep the test suite hermetic (offline, free, deterministic).

The engines guarantee identical behaviour with no API key (templates + keyword
parser). The tests are written against that offline path. But several modules call
load_dotenv() at import time, so a real key sitting in .env would leak into the
suite and make tests fire real LLM calls — slow, costly, and non-deterministic.

We set the provider keys to empty strings HERE, before any project module is
imported. python-dotenv's load_dotenv() defaults to override=False, so these
empties win over whatever is in .env, and every provider's available() returns
False — forcing the deterministic fallback the tests expect.

To test the live LLM path, run the CLI (e.g. `python main.py simulate ...`), not
pytest.
"""

import os

for _key in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
    os.environ[_key] = ""
