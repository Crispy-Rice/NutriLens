from app.core.logging import redact


def test_redacts_dashscope_style_api_key():
    assert "sk-abc123def456ghi" not in redact("key=sk-abc123def456ghi")


def test_redacts_labelled_api_key_assignment():
    out = redact('{"api_key": "some-long-opaque-value"}')
    assert "some-long-opaque-value" not in out
    assert "<REDACTED>" in out


def test_redacts_authorization_header():
    out = redact("Authorization: Bearer abcdef123456")
    assert "abcdef123456" not in out


def test_redacts_inline_base64_image():
    out = redact("payload data:image/jpeg;base64," + "A" * 400)
    assert "AAAA" not in out


def test_redacts_bare_base64_blob():
    out = redact("blob=" + "QUJD" * 100)
    assert "QUJDQUJD" not in out


def test_redacts_image_data_passed_through_log_args():
    """The real leak path: a format string plus the payload as an argument."""
    out = redact("img=data:image/jpeg;base64,%s")
    assert out.startswith("img=data:image/")


def test_leaves_ordinary_text_alone():
    text = "识别完成 dish=番茄炒蛋 confidence=0.82 elapsed=1.4s"
    assert redact(text) == text
