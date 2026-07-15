# SpeedyType Development Repository

This checkout is the development tree. It intentionally contains tests,
benchmark evidence, recordings, research reports, and local virtual
environments that are not part of a release.

Build the clean source release with:

```text
python scripts/build_release.py
```

The generated folder and ZIP appear under `dist/SpeedyType-VERSION/` and
`dist/SpeedyType-VERSION-source.zip`, where `VERSION` comes from
`speedytype/version.py`. The `dist/` directory is generated and ignored by Git.
End users should follow the README inside the generated bundle.

The release builder uses an explicit allowlist. It excludes tests, benchmark
and recording artifacts, local `.env` and settings files, virtual environments,
caches, Git metadata, and development plans.

Developer verification:

```text
python -m pytest -q
```
