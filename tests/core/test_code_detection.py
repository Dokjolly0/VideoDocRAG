from videodoc.core.utils.code_detection import analyze_ocr_text, is_code_like, normalize_code_text


def test_detects_terminal_command_and_strips_prompt():
    result = analyze_ocr_text("$ npm create vite@latest my-app", ocr_confidence=0.92)
    assert result is not None
    assert result.content_type == "terminal_command"
    assert result.language == "bash"
    assert result.code == "npm create vite@latest my-app"
    assert result.verified is True
    assert result.review_reasons == ()


def test_detects_json_configuration_and_validates_it():
    result = analyze_ocr_text('{"scripts": {"dev": "vite"}}', ocr_confidence=0.95)
    assert result is not None
    assert result.content_type == "configuration"
    assert result.language == "json"
    assert result.validation_status == "valid"
    assert result.verified is True


def test_detects_python_source_and_parse_failure_marks_review():
    result = analyze_ocr_text("def broken(:\n    return 1", ocr_confidence=0.95)
    assert result is not None
    assert result.content_type == "source_code"
    assert result.language == "python"
    assert result.validation_status == "invalid"
    assert result.verified is False
    assert any("Validation failed" in reason for reason in result.review_reasons)


def test_javascript_is_detected_but_not_parser_verified_in_strict_mode():
    result = analyze_ocr_text("const value = items.map((x) => x.id);", ocr_confidence=0.91)
    assert result is not None
    assert result.content_type == "source_code"
    assert result.language == "javascript"
    assert result.validation_status == "not_applicable"
    assert result.verified is False
    assert any("Not verified" in reason for reason in result.review_reasons)


def test_low_ocr_confidence_marks_review():
    result = analyze_ocr_text("npm run dev", ocr_confidence=0.7)
    assert result is not None
    assert result.content_type == "terminal_command"
    assert any("OCR confidence" in reason for reason in result.review_reasons)


def test_plain_text_is_not_code_like():
    result = analyze_ocr_text("In questa lezione configuriamo il progetto")
    assert result is not None
    assert result.content_type == "plain_text"
    assert is_code_like(result.content_type) is False


def test_short_label_stays_ui_label_not_python():
    result = analyze_ocr_text("Username:")
    assert result is not None
    assert result.content_type == "ui_label"
    assert result.language == "other"


def test_normalization_is_stable_for_whitespace():
    assert normalize_code_text("\n  npm run dev  \n\n\n") == "npm run dev"
