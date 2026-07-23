from pathlib import Path
import re

import scripts.build_release as build_release


ROOT = Path(__file__).resolve().parent.parent
CANONICAL = {
    "docs/README.md",
    "docs/active/README.md",
    "docs/current/PRODUCT.md",
    "docs/current/STATUS.md",
    "docs/current/user/README.md",
    "docs/current/user/MAC_SETUP.md",
    "docs/current/engineering/ARCHITECTURE.md",
    "docs/current/engineering/DECISIONS.md",
    "docs/current/engineering/KNOWN_LIMITATIONS.md",
    "docs/current/engineering/RELEASE.md",
    "docs/archive/README.md",
}
ALLOWED_ROOT_MARKDOWN = {
    "README.md",
    "real_voice_script.md",
    "real_voice_script_round2.md",
}
LINK_RE = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def test_canonical_documents_exist_and_legacy_trees_are_absent():
    assert all((ROOT / path).is_file() for path in CANONICAL)
    assert not (ROOT / "docs" / "log").exists()
    assert {path.name for path in ROOT.glob("*.md")} == ALLOWED_ROOT_MARKDOWN


def test_legacy_documentation_trees_are_absent():
    assert not (ROOT / "docs" / "superpowers").exists()
    assert not (ROOT / "docs" / "log").exists()


def test_active_work_uses_the_documented_lifecycle():
    active_root = ROOT / "docs" / "active"
    active_files = {
        path.relative_to(active_root).as_posix()
        for path in active_root.rglob("*.md")
    }
    assert "README.md" in active_files
    assert all(
        path == "README.md" or path.startswith(("specs/", "plans/"))
        for path in active_files
    )
    lifecycle = (active_root / "README.md").read_text(encoding="utf-8")
    assert "docs/active/specs/" in lifecycle
    assert "docs/active/plans/" in lifecycle
    assert "docs/current/" in lifecycle
    assert "docs/archive/" in lifecycle


def test_current_document_relative_links_resolve():
    for document in (ROOT / "docs" / "current").rglob("*.md"):
        for target in LINK_RE.findall(document.read_text(encoding="utf-8")):
            clean_target = target.split("#", 1)[0]
            if (
                not clean_target
                or "://" in clean_target
                or clean_target.startswith("mailto:")
            ):
                continue
            assert (document.parent / clean_target).resolve().exists(), (
                f"broken link in {document.relative_to(ROOT)}: {target}"
            )


def test_documentation_hub_links_every_canonical_destination():
    hub = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for path in sorted(CANONICAL - {"docs/README.md"}):
        relative = Path(path).relative_to("docs").as_posix()
        assert f"]({relative})" in hub


def test_current_status_records_only_macos_hardware_gate():
    current = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "docs" / "current").rglob("*.md")
    )
    status = (ROOT / "docs" / "current" / "STATUS.md").read_text(
        encoding="utf-8"
    )
    assert "0.5.7" in status
    assert "2026-07-20" in status
    assert "0.5.7" in status
    assert "macOS is the only hardware release gate" in current
    assert "No 24- or 25-minute real recording is required" in current
    assert "Windows Toggle real-device gate is pending" not in current
    assert "≥24-minute" not in current


def test_release_excludes_internal_documentation(tmp_path):
    result = build_release.build_release(ROOT, tmp_path / "dist")
    released = {
        path.relative_to(result.release_dir).as_posix()
        for path in result.release_dir.rglob("*")
        if path.is_file()
    }
    assert {"README.md", "MAC_SETUP.md", "KNOWN_LIMITATIONS.md"} <= released
    assert not any(path.startswith("docs/") for path in released)
    assert not any("archive" in path.lower() for path in released)
