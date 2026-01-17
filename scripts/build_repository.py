#!/usr/bin/env python3
"""
KiCad PCM Repository Builder

This script handles all packaging tasks for the American Embedded KiCad repository:
- Discovers packages in the packages/ directory
- Validates metadata.json files against the PCM schema
- Creates ZIP archives with correct structure
- Calculates SHA-256 hashes and file sizes
- Generates repository.json and packages.json
- Creates resources.zip with all icons

Usage:
    python build_repository.py --base-url <release-url> [--output-dir <dir>]
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

# Optional: jsonschema for validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


class PCMRepositoryBuilder:
    """Builds a KiCad PCM repository from source packages."""

    # Package type to directory structure mapping
    PACKAGE_STRUCTURES = {
        "colortheme": {
            "required_dirs": ["colors"],
            "optional_dirs": ["resources"],
        },
        "library": {
            "required_dirs": [],  # At least one of the optional must exist
            "optional_dirs": ["symbols", "footprints", "3dmodels", "resources"],
        },
        "plugin": {
            "required_dirs": ["plugins"],
            "optional_dirs": ["resources"],
        },
    }

    def __init__(self, repo_root: Path, output_dir: Path, base_url: str, metadata_url: str | None = None):
        self.repo_root = repo_root
        self.output_dir = output_dir
        self.base_url = base_url.rstrip("/")  # URL for package ZIP downloads (GitHub Releases)
        self.metadata_url = (metadata_url or base_url).rstrip("/")  # URL for metadata files (raw GitHub)
        self.releases_dir = output_dir / "releases"
        self.packages_dir = repo_root / "packages"
        self.schema_path = repo_root / "pcm.v1.schema.json"
        self.schema = None

        # Load schema if available
        if self.schema_path.exists():
            with open(self.schema_path) as f:
                self.schema = json.load(f)

    def build(self) -> bool:
        """Build the complete repository. Returns True on success."""
        print("=" * 60)
        print("KiCad PCM Repository Builder")
        print("=" * 60)
        print(f"Repository root: {self.repo_root}")
        print(f"Output directory: {self.output_dir}")
        print(f"Package download URL: {self.base_url}")
        print(f"Metadata URL: {self.metadata_url}")
        print()

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)

        # Discover and process packages
        packages = self.discover_packages()
        if not packages:
            print("ERROR: No packages found!")
            return False

        print(f"Found {len(packages)} package(s)")
        print()

        # Process each package
        processed_packages = []
        resources = []

        for package_path in packages:
            print(f"Processing: {package_path.name}")
            result = self.process_package(package_path)
            if result:
                processed_packages.append(result["metadata"])
                if result.get("icon_path"):
                    resources.append(result["icon_path"])
                print(f"  -> OK: {result['zip_name']}")
            else:
                print(f"  -> FAILED")
            print()

        if not processed_packages:
            print("ERROR: No packages were successfully processed!")
            return False

        # Generate packages.json
        packages_json = {"packages": processed_packages}
        packages_json_path = self.output_dir / "packages.json"
        with open(packages_json_path, "w") as f:
            json.dump(packages_json, f, indent=2)
        packages_sha256 = self.calculate_sha256(packages_json_path)
        print(f"Generated: packages.json (SHA256: {packages_sha256[:16]}...)")

        # Generate resources.zip
        resources_zip_path = self.output_dir / "resources.zip"
        self.create_resources_zip(resources, resources_zip_path)
        resources_sha256 = self.calculate_sha256(resources_zip_path)
        print(f"Generated: resources.zip (SHA256: {resources_sha256[:16]}...)")

        # Generate repository.json
        timestamp = int(time.time())
        timestamp_utc = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(timestamp))

        repository_json = {
            "$schema": "https://go.kicad.org/pcm/schemas/v1",
            "name": "American Embedded KiCad Repository",
            "maintainer": {
                "name": "American Embedded",
                "contact": {
                    "email": "build@amemb.com",
                    "github": "https://github.com/American-Embedded"
                }
            },
            "packages": {
                "url": f"{self.metadata_url}/packages.json",
                "sha256": packages_sha256,
                "update_timestamp": timestamp,
                "update_time_utc": timestamp_utc
            },
            "resources": {
                "url": f"{self.metadata_url}/resources.zip",
                "sha256": resources_sha256,
                "update_timestamp": timestamp,
                "update_time_utc": timestamp_utc
            }
        }

        repository_json_path = self.output_dir / "repository.json"
        with open(repository_json_path, "w") as f:
            json.dump(repository_json, f, indent=2)
        print(f"Generated: repository.json")

        print()
        print("=" * 60)
        print("Build completed successfully!")
        print("=" * 60)
        print()
        print("Output files:")
        print(f"  {repository_json_path}")
        print(f"  {packages_json_path}")
        print(f"  {resources_zip_path}")
        for pkg in processed_packages:
            zip_name = f"{pkg['identifier']}-{pkg['versions'][0]['version']}.zip"
            print(f"  {self.releases_dir / zip_name}")

        return True

    def discover_packages(self) -> list[Path]:
        """Find all packages in the packages directory."""
        packages = []

        if not self.packages_dir.exists():
            return packages

        # Walk through packages directory looking for metadata.json files
        for category_dir in self.packages_dir.iterdir():
            if not category_dir.is_dir():
                continue

            for package_dir in category_dir.iterdir():
                if not package_dir.is_dir():
                    continue

                metadata_path = package_dir / "metadata.json"
                if metadata_path.exists():
                    packages.append(package_dir)

        return sorted(packages)

    def process_package(self, package_path: Path) -> dict[str, Any] | None:
        """Process a single package. Returns package info or None on failure."""
        metadata_path = package_path / "metadata.json"

        # Load and validate metadata
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  ERROR: Invalid JSON in metadata.json: {e}")
            return None

        # Validate against schema if available
        if self.schema and HAS_JSONSCHEMA:
            try:
                # Create a validator with the full schema for reference resolution
                from jsonschema import Draft7Validator, RefResolver
                resolver = RefResolver.from_schema(self.schema)
                package_def = self.schema.get("definitions", {}).get("Package", {})
                validator = Draft7Validator(package_def, resolver=resolver)
                errors = list(validator.iter_errors(metadata))
                if errors:
                    for error in errors[:3]:  # Show first 3 errors
                        print(f"  ERROR: {error.message}")
                    return None
            except Exception as e:
                print(f"  WARNING: Schema validation skipped: {e}")
                # Continue without validation

        # Get package info
        identifier = metadata.get("identifier", "")
        pkg_type = metadata.get("type", "")
        versions = metadata.get("versions", [])

        if not identifier or not pkg_type or not versions:
            print(f"  ERROR: Missing required fields (identifier, type, or versions)")
            return None

        version = versions[0].get("version", "1.0.0")
        zip_name = f"{identifier}-{version}.zip"
        zip_path = self.releases_dir / zip_name

        # Create the ZIP archive
        icon_path = self.create_package_zip(package_path, zip_path, pkg_type)

        # Calculate sizes and hash
        download_size = zip_path.stat().st_size
        download_sha256 = self.calculate_sha256(zip_path)
        install_size = self.calculate_install_size(zip_path)

        # Update metadata with download info for repository
        repo_metadata = metadata.copy()
        repo_metadata["versions"] = []
        for ver in metadata["versions"]:
            ver_copy = ver.copy()
            ver_copy["download_url"] = f"{self.base_url}/{zip_name}"
            ver_copy["download_sha256"] = download_sha256
            ver_copy["download_size"] = download_size
            ver_copy["install_size"] = install_size
            repo_metadata["versions"].append(ver_copy)

        return {
            "metadata": repo_metadata,
            "zip_name": zip_name,
            "zip_path": zip_path,
            "icon_path": icon_path,
        }

    def create_package_zip(self, package_path: Path, zip_path: Path, pkg_type: str) -> Path | None:
        """Create a ZIP archive for the package. Returns icon path if found."""
        icon_path = None

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in package_path.iterdir():
                if item.name == "metadata.json":
                    # Add metadata.json at root
                    zf.write(item, "metadata.json")
                elif item.is_dir():
                    # Add directory contents
                    for file in item.rglob("*"):
                        if file.is_file():
                            arcname = str(file.relative_to(package_path))
                            zf.write(file, arcname)

                            # Track icon for resources.zip
                            if item.name == "resources" and file.name == "icon.png":
                                icon_path = file

        return icon_path

    def create_resources_zip(self, icon_paths: list[Path], zip_path: Path):
        """Create resources.zip containing all package icons."""
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for icon_path in icon_paths:
                if icon_path and icon_path.exists():
                    # Get the package identifier from the path
                    # Path structure: packages/<type>/<package-name>/resources/icon.png
                    package_dir = icon_path.parent.parent
                    metadata_path = package_dir / "metadata.json"
                    if metadata_path.exists():
                        with open(metadata_path) as f:
                            metadata = json.load(f)
                        identifier = metadata.get("identifier", package_dir.name)
                        # Icon path in resources.zip: <identifier>/icon.png
                        arcname = f"{identifier}/icon.png"
                        zf.write(icon_path, arcname)

    def calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def calculate_install_size(self, zip_path: Path) -> int:
        """Calculate uncompressed size of a ZIP archive."""
        total = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                total += info.file_size
        return total


def create_placeholder_icons(repo_root: Path):
    """Create placeholder icons for packages that don't have them."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("WARNING: Pillow not installed, skipping icon generation")
        print("         Install with: pip install Pillow")
        return

    packages_dir = repo_root / "packages"

    # Theme colors
    theme_colors = {
        "american-embedded-dark": {"bg": (30, 30, 30), "accent": (224, 122, 95)},
        "american-embedded-light": {"bg": (245, 245, 245), "accent": (191, 10, 48)},
    }

    for category_dir in packages_dir.iterdir():
        if not category_dir.is_dir():
            continue

        for package_dir in category_dir.iterdir():
            if not package_dir.is_dir():
                continue

            resources_dir = package_dir / "resources"
            icon_path = resources_dir / "icon.png"

            if icon_path.exists():
                continue

            # Create resources directory if needed
            resources_dir.mkdir(parents=True, exist_ok=True)

            # Get colors for this package
            colors = theme_colors.get(package_dir.name, {"bg": (128, 128, 128), "accent": (200, 200, 200)})

            # Create 64x64 icon
            img = Image.new("RGB", (64, 64), colors["bg"])
            draw = ImageDraw.Draw(img)

            # Draw a simple design - diagonal stripe
            for i in range(-64, 65, 4):
                draw.line([(i, 0), (i + 64, 64)], fill=colors["accent"], width=2)

            # Draw border
            draw.rectangle([0, 0, 63, 63], outline=colors["accent"], width=2)

            img.save(icon_path, "PNG")
            print(f"Created placeholder icon: {icon_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Build KiCad PCM repository from source packages"
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL for package ZIP downloads (e.g., GitHub Releases URL)"
    )
    parser.add_argument(
        "--metadata-url",
        help="Base URL for metadata files (packages.json, resources.zip). "
             "If not specified, uses --base-url. Use raw.githubusercontent.com URL for stable access."
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory for generated files (default: output)"
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory)"
    )
    parser.add_argument(
        "--create-icons",
        action="store_true",
        help="Create placeholder icons for packages missing them"
    )

    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve()

    # Create placeholder icons if requested
    if args.create_icons:
        create_placeholder_icons(repo_root)

    # Build repository
    builder = PCMRepositoryBuilder(repo_root, output_dir, args.base_url, args.metadata_url)
    success = builder.build()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
