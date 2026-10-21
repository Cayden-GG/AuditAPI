import sys

import pytest

from app.audit_service.config.settings import AppConfig, build_config


def parse(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["cli", *args])
    return build_config()


def test_required_arguments_with_defaults(monkeypatch):
    config = parse(monkeypatch, "--client-name", "Acme", "--domain-url", "https://example.com")

    assert config == AppConfig(
        client_name="Acme",
        domain_url="https://example.com",
        max_urls=5,
        only_categories="performance,seo",
        audit_id=None,
        output_dir=None,
        log_path=None,
        debug_mode=False,
    )


def test_every_argument(monkeypatch):
    config = parse(
        monkeypatch,
        "--client-name", "Acme Co",
        "--domain-url", "https://example.com",
        "--max-urls", "12",
        "--only-categories", "seo,accessibility",
        "--audit-id", "abc",
        "--output-dir", "out/dir",
        "--log-path", "logs/x.jsonl",
        "--debug-mode",
    )

    assert config == AppConfig("Acme Co", "https://example.com", 12, "seo,accessibility", "abc", "out/dir", "logs/x.jsonl", True)


@pytest.mark.parametrize("args", [["--domain-url", "https://example.com"], ["--client-name", "Acme"], []])
def test_missing_required_arguments_exit(monkeypatch, args):
    with pytest.raises(SystemExit):
        parse(monkeypatch, *args)


def test_max_urls_must_be_a_number(monkeypatch):
    with pytest.raises(SystemExit):
        parse(monkeypatch, "--client-name", "A", "--domain-url", "https://e.com", "--max-urls", "lots")
