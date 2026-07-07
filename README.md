![CI](https://github.com/home-assistant-libs/iotawattpy/actions/workflows/ci.yml/badge.svg)

# iotawattpy
 Python interface for the IoTaWatt device

## Releasing

Releases are published to [PyPI](https://pypi.org/project/ha-iotawattpy/)
automatically when a GitHub release is published:

1. Bump the version on `main`: `uv version <new-version>` (updates
   `pyproject.toml` and `uv.lock`), then commit the change.
2. Create a GitHub release with a `v<new-version>` tag (e.g. `v0.2.1`).
3. The release workflow builds the package and uploads it to PyPI using
   trusted publishing. It fails if the tag does not match the project
   version.
