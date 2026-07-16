# SpeedyType Release Checklist

Release tags are immutable markers of verified `master` commits.
Never move or force-update an existing release tag. Investigate and
deliberately correct a mistaken release instead.

## Prepare the release branch

1. Start from a clean branch based on `master`.
2. Update only the authoritative values in `speedytype/version.py`:

   ```python
   VERSION = "0.5.3"
   BUILD_DATE = "2026-07-16"
   ```

3. Update version-specific release documentation and tests.

## Verify before merge

```powershell
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
$first = (Get-FileHash dist/SpeedyType-0.5.3-source.zip -Algorithm SHA256).Hash
python scripts/build_release.py
$second = (Get-FileHash dist/SpeedyType-0.5.3-source.zip -Algorithm SHA256).Hash
if ($first -ne $second) { throw "Release is not reproducible" }
Get-Content dist/SHA256SUMS.txt
python -m speedytype --version
```

Extract the ZIP in a temporary directory, run Python compilation and
`python -m speedytype --version` from the extracted root, run
`bash -n scripts/setup_mac.sh`, and parse both released PowerShell scripts.

Commit the verified release changes and merge them to `master`.

## Tag the verified master commit

Rerun the complete suite and release build on merged `master`. Confirm that
`v0.5.3` does not already exist, then create and verify the annotated tag:

```powershell
git tag -a v0.5.3 -m "SpeedyType 0.5.3"
git cat-file -t v0.5.3
git rev-list -n 1 v0.5.3
git rev-parse master
```

`git cat-file` must print `tag`; the latter two commit IDs must match.

## Publish only with approval

Do not push a branch or tag until the operator explicitly approves remote
publication. After approval, use:

```powershell
git push origin master
git push origin v0.5.3
```

The local build/tag workflow does not execute either push automatically.
