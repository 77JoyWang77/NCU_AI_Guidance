from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cloudinary
import cloudinary.api
import cloudinary.uploader
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload project PDFs under data/raw/projects/104-114 to Cloudinary."
    )
    parser.add_argument(
        "--root",
        default="data/raw/projects/104-114",
        help="Root folder that contains PDFs to upload, relative to the project root unless absolute.",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="Cloudinary base folder. Defaults to CLOUDINARY_PROJECT_FOLDER or ncu-ai-guidance/projects.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing assets with the same public_id.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be uploaded without sending files to Cloudinary.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def configure_cloudinary() -> None:
    cloudinary.config(
        cloud_name=require_env("CLOUDINARY_CLOUD_NAME"),
        api_key=require_env("CLOUDINARY_API_KEY"),
        api_secret=require_env("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def resolve_root_dir(root_arg: str) -> Path:
    root_dir = Path(root_arg)
    if not root_dir.is_absolute():
        root_dir = PROJECT_ROOT / root_dir
    return root_dir.resolve()


def build_public_id(pdf_path: Path, root_dir: Path, folder: str) -> str:
    relative_path = pdf_path.relative_to(root_dir).as_posix()
    return f"{folder.rstrip('/')}/{relative_path}"


def asset_exists(public_id: str) -> bool:
    try:
        cloudinary.api.resource(public_id, resource_type="raw")
        return True
    except Exception:
        return False


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    root_dir = resolve_root_dir(args.root)
    if not root_dir.exists():
        print(f"[ERROR] Folder not found: {root_dir}")
        return 1

    folder = args.folder or os.getenv("CLOUDINARY_PROJECT_FOLDER", "ncu-ai-guidance/projects")
    configure_cloudinary()

    pdf_files = sorted(root_dir.rglob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] No PDF files found under {root_dir}")
        return 1

    print(f"Found {len(pdf_files)} PDF files under {root_dir}")
    print(f"Target Cloudinary folder: {folder}")

    uploaded = 0
    skipped = 0
    failed = 0

    for index, pdf_file in enumerate(pdf_files, start=1):
        public_id = build_public_id(pdf_file, root_dir, folder)
        print(f"[{index}/{len(pdf_files)}] {pdf_file.relative_to(root_dir)}")

        if args.dry_run:
            print(f"  -> DRY RUN public_id: {public_id}")
            continue

        if not args.overwrite and asset_exists(public_id):
            skipped += 1
            print("  -> Skipped (already exists)")
            continue

        try:
            result = cloudinary.uploader.upload(
                str(pdf_file),
                resource_type="raw",
                public_id=public_id,
                overwrite=args.overwrite,
                use_filename=False,
                unique_filename=False,
                invalidate=args.overwrite,
            )
            uploaded += 1
            print(f"  -> Uploaded: {result['secure_url']}")
        except Exception as exc:
            failed += 1
            print(f"  -> Failed: {exc}")

    print("")
    print("Upload summary")
    print(f"Uploaded: {uploaded}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
