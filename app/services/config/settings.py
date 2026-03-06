import argparse
from dataclasses import dataclass

@dataclass
class AppConfig:
    client_name: str
    domain_url: str
    only_categories: str
    max_urls: int

def build_config() -> AppConfig:
    """
    Builds config object with all the nessary data for the program
    """
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--client-name", 
        required=True,
    )

    parser.add_argument(
        "--domain-url",
        required=False,
        help="Root domain URL used to discover sitemaps (e.g. https://example.com)",
    )

    parser.add_argument(
        "--only-categories",
        required=True,
        help="Which audits to perform with lighthouse ['seo', 'seo,performance', 'seo,performance,accessability']"
    )
        
    args = parser.parse_args()

    raw_ids = getattr(args, "audit_ids", None)

    return AppConfig(
        client_name=args.client_name,
        domain_url=domain_url,
        only_categories=args.only_categories,
        max_urls=5,
    )
