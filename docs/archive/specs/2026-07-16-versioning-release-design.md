# Versioning and Release Control Design

## Goal

Establish one authoritative SpeedyType version, expose it consistently in the
package, CLI, About dialog, and source release, and document a repeatable
annotated-tag release procedure. The first release under this procedure is
`0.5.1`, built on `2026-07-16` and tagged locally as `v0.5.1` after merge and
final verification.

## Version Source

`speedytype/version.py` remains the single source of release metadata:

```python
VERSION = "0.5.1"
BUILD_DATE = "2026-07-16"
STT_MODEL = "whisper-1"
```

`speedytype/__init__.py` imports `VERSION` and publishes it as `__version__`.
It must not contain a second literal version number. The existing About dialog
and release builder continue importing or loading `speedytype/version.py`, so
all four consumers resolve the same value:

- `speedytype.__version__`
- `speedytype --version`
- tray **About**
- `dist/SpeedyType-<version>` and its source ZIP

## CLI Behavior

The root argument parser adds the standard argparse version action:

```python
parser.add_argument(
    "--version",
    action="version",
    version=f"SpeedyType {VERSION}",
)
```

`speedytype --version` prints exactly `SpeedyType 0.5.1` followed by a newline
and exits `0`. It is handled before subcommand validation and does not load
configuration, resolve Keyring credentials, or require API keys.

## Release Procedure

Add root `RELEASE.md` as the maintained operator checklist. It records this
order:

1. Start from a clean branch based on `master`.
2. Update `VERSION` and `BUILD_DATE` in `speedytype/version.py` only.
3. Update version-specific documentation and release tests.
4. Run the complete pytest suite and Python compilation.
5. Run `python scripts/build_release.py` twice and verify identical hashes.
6. Verify the ZIP checksum, inventory, CLI version, and extracted smoke tests.
7. Commit the release changes and merge them to `master`.
8. On the verified merge commit, create an annotated tag with
   `git tag -a v0.5.1 -m "SpeedyType 0.5.1"`.
9. Push the branch and tag only with explicit operator approval. The documented
   commands are `git push origin master` and `git push origin v0.5.1`; this
   implementation does not execute either push.

The checklist states that tags are immutable release markers. A mistaken tag
must be investigated and deliberately corrected; the workflow must not silently
move or force-update an existing tag.

## Documentation and Release Evidence

Update current version-specific references from `0.5.0` to `0.5.1`, including
the release README checksum examples, builder tests, generated artifact names,
and the source-release evidence in `POC_REPORT.md`. Regenerate the release after
all released source and README changes, then record the exact observed test
count, ZIP byte length, and SHA-256.

The generated release remains ignored under `dist/`; only its reproducible
evidence is tracked. macOS real-device verification remains pending and is not
reclassified by this work.

## Testing

Automated tests verify:

- `speedytype.__version__ == speedytype.version.VERSION == "0.5.1"`;
- `main(["--version"])` exits `0`, prints exactly `SpeedyType 0.5.1`, and does
  not invoke configuration loading;
- the About dialog still displays `VERSION` and `BUILD_DATE`;
- the release builder creates `SpeedyType-0.5.1` and
  `SpeedyType-0.5.1-source.zip`;
- `RELEASE.md` contains the required verification, annotated-tag, and explicit
  push commands;
- the complete suite, compile step, double build, checksum, and extracted
  release smoke checks pass.

After merge, verify the local tag with:

```powershell
git cat-file -t v0.5.1
git rev-list -n 1 v0.5.1
git rev-parse master
```

The first command must print `tag`; the latter two commit IDs must match.

## Completion Criteria

- Every runtime and release version consumer resolves `0.5.1` from
  `speedytype/version.py`.
- `speedytype --version` works without credentials or a subcommand.
- About displays version `0.5.1` and build date `2026-07-16`.
- `RELEASE.md` defines the tested annotated-tag workflow and separates local
  tag creation from remote publication.
- The `0.5.1` source release is rebuilt with matching checksum evidence.
- Local annotated tag `v0.5.1` points to the verified `master` merge commit.
- No branch or tag is pushed without separate user authorization.
