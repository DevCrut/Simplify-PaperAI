import os
import io
import zipfile
from pathlib import Path

import requests
import shutil

import docaggregate
import indexgenerator
import cleanup
# ----------------- CONFIG -----------------

APP_ENV = os.getenv("APP_ENV", "dev")  # dev / prod / ci

REPO_ZIP_URL = os.getenv(
    "PAPER_REPO_ZIP_URL",
    "https://github.com/Roblox/creator-docs/archive/refs/heads/main.zip",
)

# Base data dir (inside Docker you can map a volume here, e.g. /data)
DATA_DIR = Path(os.getenv("PAPER_DATA_DIR", "."))

LOCAL_REPO_DIR = Path(os.getenv("PAPER_LOCAL_REPO_DIR", "creator-docs"))

ENGINE_REF_SUBPATH = Path(
    os.getenv("PAPER_ENGINE_REF_SUBPATH", "content/en-us/reference/engine")
)

ENGINE_INDEX_FILE = DATA_DIR / os.getenv("PAPER_ENGINE_INDEX_FILE", "engine_index.jsonl")
ENGINE_PROPERTIES_DIR = DATA_DIR / os.getenv(
    "PAPER_ENGINE_PROPERTIES_FILE", "engine_properties_index.jsonl"
)

ENGINE_BASE_URL = os.getenv(
    "PAPER_ENGINE_BASE_URL",
    "https://create.roblox.com/docs/reference/engine",
)

# behavior flags
NON_INTERACTIVE = os.getenv("PAPER_NON_INTERACTIVE", "0") == "1"
FORCE_REBUILD = os.getenv("PAPER_FORCE_REBUILD", "0") == "1"
SKIP_DOWNLOAD = os.getenv("PAPER_SKIP_DOWNLOAD", "0") == "1"

# ------------------------------------------


def download_and_extract_repo(zip_url: str, dest_dir: Path) -> Path:
    """
    Downloads the GitHub repo as a ZIP and extracts it to dest_dir.
    If dest_dir already exists, it skips downloading.
    Returns the path to the extracted repo root.
    """
    if dest_dir.exists():
        print(f"[INFO] {dest_dir} already exists, skipping download.")
        return dest_dir

    print(f"[INFO] Downloading repo ZIP from {zip_url} ...")
    resp = requests.get(zip_url, stream=True)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # GitHub puts everything under a top-level folder like creator-docs-main/
        top_level = zf.namelist()[0].split("/")[0]
        print(f"[INFO] Extracting ZIP (top folder: {top_level}) ...")
        zf.extractall(".")

    extracted_root = Path(top_level)

    # Optionally rename to a stable folder name
    if extracted_root != dest_dir:
        print(f"[INFO] Renaming {extracted_root} -> {dest_dir}")
        extracted_root.rename(dest_dir)

    return dest_dir


def yaml_to_text(data) -> str:
    """
    Flatten a nested YAML structure into human-readable text.
    This isn’t perfect, but it gives you a decent text blob
    you can embed with your RAG system.
    """
    lines = []

    def rec(node, indent=0):
        pad = "  " * indent

        if isinstance(node, dict):
            for k, v in node.items():
                if v is None:
                    continue
                if isinstance(v, (dict, list)):
                    lines.append(f"{pad}{k}:")
                    rec(v, indent + 1)
                else:
                    lines.append(f"{pad}{k}: {v}")
        elif isinstance(node, list):
            for item in node:
                rec(item, indent)
        else:
            lines.append(f"{pad}{node}")

    rec(data)
    return "\n".join(lines)


def path_to_engine_url(rel_yaml_path: Path) -> str:
    """
    Convert a YAML path like classes/BasePart.yaml into
    https://create.roblox.com/docs/reference/engine/classes/BasePart
    """
    slug = rel_yaml_path.with_suffix("")  # drop .yaml
    slug_str = str(slug).replace(os.sep, "/")
    return ENGINE_BASE_URL.rstrip("/") + "/" + slug_str.lstrip("/")

def ask_yes_no(prompt: str, default: bool = False) -> bool:
    if default:
        suffix = " [Y/n]: "
    else:
        suffix = " [y/N]: "

    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")

def delete_file(path: Path, label: str = "file"):
    try:
        path.unlink(missing_ok=True)  # no error if it doesn't exist
        print(f"[OK] Removed {label}: {path}")
    except IsADirectoryError:
        # In case it's accidentally a folder, remove it too
        shutil.rmtree(path, ignore_errors=True)
        print(f"[OK] Removed directory {label}: {path}")
    except PermissionError as e:
        print(f"[WARN] No permission to delete {label}: {path} ({e})")

def dataset_exists() -> bool:
    return ENGINE_PROPERTIES_DIR.exists() or ENGINE_INDEX_FILE.exists()


def main():
    print("Booting Paper Assistant...")
    skip_rebuild = False

    if dataset_exists():
        print("Existing dataset detected:")
        print(f" - {ENGINE_INDEX_FILE}")
        print(f" - {ENGINE_PROPERTIES_DIR}")

        if FORCE_REBUILD:
            print("[CFG] FORCE_REBUILD=1 → will rebuild dataset.")
            rebuild = True
        elif NON_INTERACTIVE:
            print("[CFG] NON_INTERACTIVE=1 → will NOT rebuild (using existing).")
            rebuild = False
        else:
            rebuild = ask_yes_no("Rebuild dataset?", default=False)

        if not rebuild:
            print("Skipping rebuild. Using existing dataset.")
            skip_rebuild = True
        else:
            print("Rebuilding dataset...")
            delete_file(ENGINE_INDEX_FILE, "engine index")
            delete_file(ENGINE_PROPERTIES_DIR, "engine properties")

    if not skip_rebuild:
        if SKIP_DOWNLOAD:
            print("[CFG] SKIP_DOWNLOAD=1 → assuming repo already present at", LOCAL_REPO_DIR)
        else:
            download_and_extract_repo(REPO_ZIP_URL, LOCAL_REPO_DIR)

        docaggregate.main()
        indexgenerator.main()
        cleanup.main()


if __name__ == "__main__":
    main()
