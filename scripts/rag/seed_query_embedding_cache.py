from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(ROOT / ".env")

from app.services.course_info_service import (  # noqa: E402
    DEFAULT_QUERY_CACHE_KEYWORDS,
    seed_query_embedding_cache,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed cached query embeddings for course keyword vector search."
    )
    parser.add_argument(
        "keywords",
        nargs="*",
        help="Optional keywords. Defaults to the built-in common keyword list.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keywords = args.keywords or DEFAULT_QUERY_CACHE_KEYWORDS
    results = seed_query_embedding_cache(list(keywords))

    created = sum(1 for item in results if not item["cache_hit"])
    reused = sum(1 for item in results if item["cache_hit"])
    print(f"Seeded query embedding cache: created={created}, reused={reused}, total={len(results)}")
    for item in results:
        status = "reused" if item["cache_hit"] else "created"
        print(f"- {item['query']} [{status}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
