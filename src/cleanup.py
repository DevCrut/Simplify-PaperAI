import shutil
from pathlib import Path

# Folders to delete
CREATOR_DOCS = Path("creator-docs")
ENGINE_OBJECTS = Path("engine_objects")

def delete_folder(path: Path):
    if path.exists() and path.is_dir():
        print(f"[INFO] Deleting folder: {path}")
        shutil.rmtree(path)
        print(f"[OK] Removed: {path}")
    else:
        print(f"[SKIP] Folder not found: {path}")

def main():
    delete_folder(CREATOR_DOCS)
    delete_folder(ENGINE_OBJECTS)

    print("\n[COMPLETE] Cleanup finished.")

if __name__ == "__main__":
    main()
