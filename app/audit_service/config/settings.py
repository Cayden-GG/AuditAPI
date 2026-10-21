"""
Audit cli config
Parses the command line arguments into the AppConfig used to run an audit
"""
import argparse
from dataclasses import dataclass

@dataclass
class AppConfig:
    client_name: str
    domain_url: str
    max_urls: int
    only_categories: str
    audit_id: str | None = None
    output_dir: str | None = None
    log_path: str | None = None
    debug_mode: bool = False

def build_config() -> AppConfig:
    """
    Builds config object with all the necessary data for the program from the cli arguments

    @Returns:
        audit run config (AppConfig)
    """
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--client-name", 
        required=True,
    )

    parser.add_argument(
        "--domain-url",
        required=True,
        help="Root domain URL used to discover sitemaps (e.g. https://example.com)",
    )
    parser.add_argument(
        "--max-urls",
        required=False,
        type=int,
        default=5,
        help="Maximum number of URLs to audit",
    )
    parser.add_argument(
        "--only-categories",
        required=False,
        default="performance,seo",
        help="Comma-separated Lighthouse categories (e.g. performance,seo,accessibility)",
    )
    parser.add_argument(
        "--audit-id",
        required=False,
        default=None,
        help="Audit ID for correlating logs",
    )
    parser.add_argument(
        "--output-dir",
        required=False,
        default=None,
        help="Override output directory for audit artifacts",
    )
    parser.add_argument(
        "--log-path",
        required=False,
        default=None,
        help="Write structured audit logs to this path",
    )
    parser.add_argument(
        "--debug-mode",
        action="store_true",
        help="Skip paid AI requests (used for testing).",
    )

    args = parser.parse_args()

    return AppConfig(
        client_name=args.client_name,
        domain_url=args.domain_url,
        max_urls=args.max_urls,
        only_categories=args.only_categories,
        audit_id=args.audit_id,
        output_dir=args.output_dir,
        log_path=args.log_path,
        debug_mode=args.debug_mode,
    )
