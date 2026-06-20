"""AI metadata generation and Shutterstock CSV export for stock photos."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger
from services.ollama_client import OllamaClient

log = get_logger(__name__)

_ollama = OllamaClient()

VALID_CATEGORIES = [
    "Abstract",
    "Animals/Wildlife",
    "Arts",
    "Backgrounds/Textures",
    "Beauty/Fashion",
    "Buildings/Landmarks",
    "Business/Finance",
    "Education",
    "Food and Drink",
    "Healthcare/Medical",
    "Holidays",
    "Industrial",
    "Interiors",
    "Miscellaneous",
    "Nature",
    "Objects",
    "Parks/Outdoor",
    "People",
    "Religion",
    "Science",
    "Signs/Symbols",
    "Sports/Recreation",
    "Technology",
    "Transportation",
    "Vintage",
]

SCENE_TYPES = [
    "landscape",
    "portrait",
    "food",
    "architecture",
    "street",
    "nature_wildlife",
    "abstract_texture",
    "business_lifestyle",
]

_templates_dir = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_templates_dir)))


def _render_prompt(template_name: str, **context) -> str:
    template = _jinja_env.get_template(f"{template_name}.j2")
    rendered = template.render(**context)
    parts = rendered.split("{## USER ##}")
    if len(parts) == 2:
        system_block = parts[0].split("{## SYSTEM ##}")
        system_text = system_block[-1].strip() if len(system_block) > 1 else None
        user_text = parts[1].strip()
        return system_text, user_text
    return None, rendered.strip()


def _validate_metadata(data: dict) -> dict:
    """Validate and clamp metadata to Shutterstock requirements."""
    title = str(data.get("title", "")).strip()
    if len(title) < 5:
        raise ProcessingError(f"Generated title too short ({len(title)} chars): {title!r}")
    if len(title) > 200:
        title = title[:200]

    raw_keywords = data.get("keywords", [])
    if isinstance(raw_keywords, str):
        raw_keywords = [k.strip() for k in raw_keywords.split(",")]
    keywords = [k.lower().strip() for k in raw_keywords if k.strip()]
    if len(keywords) < 7:
        raise ProcessingError(f"Too few keywords generated ({len(keywords)})")
    keywords = keywords[:50]

    raw_categories = data.get("categories", [])
    if isinstance(raw_categories, str):
        raw_categories = [c.strip() for c in raw_categories.split(",")]
    categories = [c for c in raw_categories if c in VALID_CATEGORIES]
    if not categories:
        categories = ["Miscellaneous"]
    categories = categories[:2]

    return {"title": title, "keywords": keywords, "categories": categories}


async def generate_metadata(
    image_path: Path,
    scene_type: str,
    image_description: str | None = None,
) -> dict:
    """Generate Shutterstock-optimized metadata for a single photo via Ollama."""
    log.info("generating_metadata", image=str(image_path), scene_type=scene_type)

    resolution = None
    exif_summary = None
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            resolution = f"{img.width}x{img.height}"
            exif_data = img.getexif()
            if exif_data:
                exif_parts = []
                tag_names = {
                    271: "Make", 272: "Model", 33434: "ExposureTime",
                    33437: "FNumber", 34855: "ISO", 37386: "FocalLength",
                }
                for tag_id, name in tag_names.items():
                    if tag_id in exif_data:
                        exif_parts.append(f"{name}: {exif_data[tag_id]}")
                exif_summary = ", ".join(exif_parts) if exif_parts else None
    except Exception:
        log.debug("exif_extraction_skipped", image=str(image_path))

    system_prompt, user_prompt = _render_prompt(
        "photo_metadata",
        scene_type=scene_type,
        image_description=image_description or f"A {scene_type} photograph",
        resolution=resolution,
        exif_summary=exif_summary,
    )

    settings = get_settings()
    model = settings.stock_photo_model

    try:
        available = await _ollama.list_models()
    except Exception:
        available = []

    if available and model not in available:
        log.warning("configured_model_missing", model=model, available=available)
        model = available[0]

    try:
        response = await _ollama.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt,
        )
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ProcessingError(f"Ollama returned invalid JSON: {exc}") from exc
    except Exception as exc:
        raise ProcessingError(f"Metadata generation failed: {exc}") from exc

    validated = _validate_metadata(data)
    log.info(
        "metadata_generated",
        image=str(image_path),
        title_len=len(validated["title"]),
        keyword_count=len(validated["keywords"]),
    )
    return validated


async def batch_generate_metadata(photos: list[dict]) -> list[dict]:
    """Generate metadata for a batch of photos.

    Each dict in *photos* must contain: image_path, scene_type, output_filename.
    """
    results = []
    for photo in photos:
        image_path = Path(photo["image_path"])
        scene_type = photo.get("scene_type", "landscape")
        description = photo.get("image_description")
        try:
            metadata = await generate_metadata(image_path, scene_type, description)
            metadata["filename"] = photo.get("output_filename", image_path.name)
            results.append(metadata)
        except ProcessingError as exc:
            log.warning("metadata_failed", image=str(image_path), error=str(exc))
            results.append({
                "filename": photo.get("output_filename", image_path.name),
                "title": "",
                "keywords": [],
                "categories": [],
                "error": str(exc),
            })
    return results


def export_shutterstock_csv(photos_metadata: list[dict], output_path: Path) -> Path:
    """Write a Shutterstock-compatible CSV file.

    Columns: Filename, Description, Keywords, Categories
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_path if output_path.suffix == ".csv" else output_path / "shutterstock.csv"
    if csv_path.is_dir():
        csv_path = csv_path / "shutterstock.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Filename", "Description", "Keywords", "Categories"])
        for meta in photos_metadata:
            if meta.get("error"):
                continue
            keywords_str = ",".join(meta.get("keywords", []))
            categories_str = ",".join(meta.get("categories", []))
            writer.writerow([
                meta.get("filename", ""),
                meta.get("title", ""),
                keywords_str,
                categories_str,
            ])

    log.info("csv_exported", path=str(csv_path), photo_count=len(photos_metadata))
    return csv_path


def export_package(
    enhanced_dir: Path,
    photos_metadata: list[dict],
    output_path: Path,
) -> Path:
    """Create a zip package of enhanced JPEGs + Shutterstock CSV for upload."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path = output_path if output_path.suffix == ".zip" else output_path.with_suffix(".zip")

    csv_path = output_path.parent / "shutterstock_metadata.csv"
    export_shutterstock_csv(photos_metadata, csv_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(csv_path, "shutterstock_metadata.csv")

        for meta in photos_metadata:
            if meta.get("error"):
                continue
            filename = meta.get("filename", "")
            image_file = enhanced_dir / filename
            if image_file.exists():
                zf.write(image_file, filename)
            else:
                log.warning("missing_enhanced_file", filename=filename)

    if csv_path.exists():
        csv_path.unlink()

    log.info("package_exported", path=str(zip_path))
    return zip_path
