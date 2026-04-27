# Contributing to Recallo

## Local development

```bash
git clone https://github.com/TianqBu/recallo.git
cd recallo
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest
ruff check recallo tests
```

The CI matrix runs ubuntu/windows/macos × Python 3.11/3.12. `pytest` skips
the sqlite-vec tests gracefully when the local sqlite3 lacks loadable-extension
support (notably actions/setup-python on macOS arm64).

## Releasing to PyPI

The maintainer flow:

1. **Bump the version** in `pyproject.toml` (`[project] version = "0.1.1"`).
2. **Commit** the bump (`git commit -am "release: v0.1.1"`).
3. **Tag** it (`git tag v0.1.1`).
4. **Push** (`git push && git push --tags`).
5. The `Publish to PyPI` workflow builds, runs `twine check`, smoke-installs
   the wheel, then uploads.

### One-time setup

- Create a project-scoped API token at <https://pypi.org/manage/account/token/>.
- Add it as a repository secret named `PYPI_API_TOKEN` (Settings → Secrets and
  variables → Actions).
- Add a GitHub Environment called `pypi` if you want a manual approval gate
  before each upload (Settings → Environments).
- Optional: repeat with TestPyPI for dry runs (`TEST_PYPI_API_TOKEN`,
  environment `testpypi`).

### Dry-running a release

`Actions → Publish to PyPI → Run workflow → testpypi`. This builds + uploads to
TestPyPI without touching production.

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            recallo
```

## Style

- Ruff is the linter (config in `pyproject.toml`). 100-column lines.
- Tests live next to the module they exercise (`tests/test_<module>.py`).
- New deps need an entry in `pyproject.toml` AND `THIRD_PARTY_LICENSES.md` AND
  `NOTICE` if they're not BSD/MIT/Apache.
- Privacy-sensitive code paths must add a test in `tests/test_safety.py` or
  `tests/test_cortex.py` (URL/key scrubbing already lives there).
