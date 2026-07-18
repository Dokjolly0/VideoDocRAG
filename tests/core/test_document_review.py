from videodoc.core.models.document_review import DocumentationReviewReport, ReviewIssue


def test_documentation_review_report_roundtrip(tmp_path):
    report = DocumentationReviewReport(
        sections=[],
        issues=[ReviewIssue(severity="warning", check="markdown", section_path="docs/01.md", message="Missing heading.")],
        code_blocks=[],
    )
    path = tmp_path / "review.json"

    report.save(path)
    loaded = DocumentationReviewReport.load(path)

    assert loaded == report
