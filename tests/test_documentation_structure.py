from pathlib import Path
import re

import scripts.build_release as build_release


ROOT = Path(__file__).resolve().parent.parent
CANONICAL = {
    "docs/README.md",
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


def test_only_active_migration_docs_remain_in_superpowers():
    active = ROOT / "docs" / "superpowers"
    assert {
        path.relative_to(active).as_posix()
        for path in active.rglob("*.md")
    } == {
        "plans/2026-07-18-documentation-information-architecture.md",
        "specs/2026-07-18-documentation-information-architecture-design.md",
    }


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
    assert "0.5.3" in status
    assert "2026-07-16" in status
    assert "0.5.4" in status
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
