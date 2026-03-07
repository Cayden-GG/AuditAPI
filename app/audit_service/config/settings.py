import argparse
from dataclasses import dataclass

@dataclass
class AppConfig:
    client_name: str
    domain_url: str
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
        required=True,
        help="Root domain URL used to discover sitemaps (e.g. https://example.com)",
    )

    args = parser.parse_args()

    return AppConfig(
        client_name=args.client_name,
        domain_url=args.domain_url,
        max_urls=5,
    )
