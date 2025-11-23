import json
import copy
from pathlib import Path

import yaml

# ================== CONFIG ==================

# Root of the cloned / downloaded repo
REPO_ROOT = Path("creator-docs")

# Where the language-specific docs live
DOC_ROOT = REPO_ROOT / "content" / "en-us"

# Engine documentation YAMLs (actual API objects)
ENGINE_DOC_ROOT = DOC_ROOT / "reference" / "engine"

# Navigation / reference tree for engine (index)
ENGINE_NAV_ROOT = REPO_ROOT / "content" / "common" / "navigation" / "engine"
REFERENCE_YAML = ENGINE_NAV_ROOT / "reference.yaml"

# Where to dump all per-object JSONs
OUTPUT_ROOT = Path("engine_objects")  # will mirror engine/ structure inside

# Public docs base URL (for linking back if you want)
ENGINE_BASE_URL = "https://create.roblox.com/docs/reference/engine"

# Keys that probably hold "member lists" with `name` fields (we merge by name)
MERGE_LIST_KEYS = {
    "properties",
    "methods",
    "events",
    "callbacks",
    "members",
    "fields",
    "items",
    "parameters",
}

# ================== HELPERS ==================


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_rel_path(p: str) -> str:
    """
    Normalize a 'path' from reference.yaml to a consistent POSIX-style form,
    like 'classes/BasePart.yaml'.
    """
    return str(Path(p).as_posix()).lstrip("./")


def resolve_doc_rel_path(nav_path: str) -> str:
    """
    Convert a path from reference.yaml into a path relative to ENGINE_DOC_ROOT.

    Examples:
      'reference/engine/classes/BasePart.yaml' -> 'classes/BasePart.yaml'
      'en-us/reference/engine/classes/BasePart.yaml' -> 'classes/BasePart.yaml'
      'engine/classes/BasePart.yaml' -> 'classes/BasePart.yaml'
      'classes/BasePart.yaml' -> 'classes/BasePart.yaml'
    """
    p = normalize_rel_path(nav_path)

    prefixes = [
        "reference/engine/",
        "/reference/engine/",
        "en-us/reference/engine/",
        "/en-us/reference/engine/",
        "engine/",
        "/engine/",
    ]

    for prefix in prefixes:
        if p.startswith(prefix):
            return p[len(prefix):]

    return p


def path_to_url(rel_yaml_path: str) -> str:
    """
    Convert a path like 'classes/BasePart.yaml' into the public docs URL.
    """
    slug = rel_yaml_path
    if slug.lower().endswith(".yaml"):
        slug = slug[:-5]
    return ENGINE_BASE_URL.rstrip("/") + "/" + slug.lstrip("/")


def deep_merge(base, child):
    """
    Deep merge two YAML dicts:

      * Dicts: recursively merged (child wins on conflicts).
      * Lists:
          - For MERGE_LIST_KEYS: merge by "name" using deep_merge for each member.
          - For "tags": child overrides base (no inheritance).
          - For everything else: child overrides base (NO concat) – safer for
            metadata like code_samples, inherits, etc.
      * Scalars / mismatched types: child overrides base.
    """
    if not isinstance(base, dict) or not isinstance(child, dict):
        # scalar / list / whatever -> child simply wins
        return copy.deepcopy(child)

    result = copy.deepcopy(base)

    for key, child_val in child.items():
        if key not in result:
            # only in child
            result[key] = copy.deepcopy(child_val)
            continue

        base_val = result[key]

        # ----- dict + dict -----
        if isinstance(base_val, dict) and isinstance(child_val, dict):
            result[key] = deep_merge(base_val, child_val)

        # ----- list + list -----
        elif isinstance(base_val, list) and isinstance(child_val, list):
            # Merge member lists (properties/methods/events/...) by "name"
            if key in MERGE_LIST_KEYS:
                merged = []
                named_items = {}

                # Base items
                for it in base_val:
                    it_copy = copy.deepcopy(it)
                    if isinstance(it_copy, dict) and "name" in it_copy:
                        named_items[it_copy["name"]] = it_copy
                    else:
                        merged.append(it_copy)

                # Child items: override or extend
                for it in child_val:
                    it_copy = copy.deepcopy(it)
                    if isinstance(it_copy, dict) and "name" in it_copy:
                        n = it_copy["name"]
                        if n in named_items:
                            # deep-merge base+child versions of the same member
                            named_items[n] = deep_merge(named_items[n], it_copy)
                        else:
                            named_items[n] = it_copy
                    else:
                        merged.append(it_copy)

                # Deterministic order – you can change sorted() to something else
                for n in sorted(named_items.keys()):
                    merged.append(named_items[n])

                result[key] = merged

            elif key == "tags":
                # DO NOT inherit tags – child completely overrides base
                result[key] = copy.deepcopy(child_val)

            else:
                # Safer default: child overrides base list entirely
                # (avoids weird concatenation of inherits, code_samples, etc.)
                result[key] = copy.deepcopy(child_val)

        # ----- anything else -> child wins -----
        else:
            result[key] = copy.deepcopy(child_val)

    return result


def build_merged_for_entry(entry, name_index, cache):
    """
    Given an object entry (with "data"), recursively merge base classes / types
    into it according to inheritance, and cache the result.

    * Base classes supply defaults.
    * Child overrides scalars and metadata.
    * Special handling for descendants/inherits/tags to avoid nonsense.
    """
    name = entry["name"]

    if name in cache:
        return cache[name]

    # Original data for THIS class
    data = entry["data"] or {}
    # Start with this class as "child"
    merged = copy.deepcopy(data)

    base_names = get_base_names(data)
    ancestors = []

    # Merge each base class into this one (base -> child)
    for base_name in base_names:
        base_entry = name_index.get(base_name)
        if not base_entry:
            continue

        base_merged = build_merged_for_entry(base_entry, name_index, cache)

        # IMPORTANT: base_merged first, then merged (child) second
        merged = deep_merge(base_merged, merged)

        ancestors.append(base_name)
        base_ancestors = base_merged.get("_ancestors", [])
        if isinstance(base_ancestors, list):
            ancestors.extend(base_ancestors)

    # De-duplicate ancestors preserving order
    seen = set()
    deduped = []
    for a in ancestors:
        if a not in seen:
            seen.add(a)
            deduped.append(a)

    merged["_ancestors"] = deduped

    # ---- Special cases where we do NOT want base to bleed in ----

    # 1) name: always the leaf class name
    merged["name"] = data.get("name", entry["name"])

    # 2) inherits: keep the immediate inheritance list from THIS class only
    if "inherits" in data:
        merged["inherits"] = copy.deepcopy(data["inherits"])
    elif "inherits" in merged:
        # if only inherited from base, you *can* keep it, but I’d rather restrict
        # to leaf’s own inherits, so we drop it here
        del merged["inherits"]

    # 3) descendants: only what THIS class defines (if anything)
    if "descendants" in data:
        merged["descendants"] = copy.deepcopy(data["descendants"])
    elif "descendants" in merged:
        del merged["descendants"]

    # 4) tags: already handled in deep_merge (child overrides base), but if
    #    this class has its own tags, ensure we use them
    if "tags" in data:
        merged["tags"] = copy.deepcopy(data["tags"])

    # 5) deprecation_message: child’s message wins; if non-empty in data,
    #    overwrite anything from base
    if "deprecation_message" in data and data["deprecation_message"]:
        merged["deprecation_message"] = data["deprecation_message"]

    cache[name] = merged
    return merged


def get_base_names(obj: dict):
    """
    Try to find inheritance info. Supports several potential keys,
    since we don't know the exact schema in advance.
    """
    names = []
    for key in ("inherits", "extends", "superclass", "superclasses", "bases"):
        if key in obj:
            val = obj[key]
            if isinstance(val, str):
                names.append(val)
            elif isinstance(val, list):
                names.extend(v for v in val if isinstance(v, str))
    return names


# ================== LOAD ALL ENGINE OBJECTS ==================


def load_engine_objects():
    """
    Load all *.yaml files under ENGINE_DOC_ROOT and index them:
      - by name      -> name_index[name]
      - by rel path  -> path_index['classes/BasePart.yaml']
    """
    name_index = {}
    path_index = {}

    for yaml_path in ENGINE_DOC_ROOT.rglob("*.yaml"):
        rel_from_engine = yaml_path.relative_to(ENGINE_DOC_ROOT)
        rel_str = str(rel_from_engine.as_posix())

        data = load_yaml(yaml_path) or {}

        name = data.get("name") or yaml_path.stem
        kind = data.get("type") or data.get("kind")

        entry = {
            "name": name,
            "kind": kind,
            "path": rel_str,
            "data": data,
        }

        # Index by name (last one wins if duplicates)
        name_index[name] = entry

        # Index by path (e.g. 'classes/BasePart.yaml')
        path_index[normalize_rel_path(rel_str)] = entry

    return name_index, path_index


# ================== INHERITANCE MERGING ==================


def build_merged_for_entry(entry, name_index, cache):
    name = entry["name"]
    if name in cache:
        return cache[name]

    data = entry["data"] or {}
    merged = copy.deepcopy(data)

    base_names = get_base_names(data)
    ancestors = []

    for base_name in base_names:
        base_entry = name_index.get(base_name)
        if not base_entry:
            continue

        base_merged = build_merged_for_entry(base_entry, name_index, cache)
        merged = deep_merge(base_merged, merged)

        ancestors.append(base_name)
        base_ancestors = base_merged.get("_ancestors", [])
        if isinstance(base_ancestors, list):
            ancestors.extend(base_ancestors)

    # De-duplicate ancestors preserving order
    seen = set()
    deduped = []
    for a in ancestors:
        if a not in seen:
            seen.add(a)
            deduped.append(a)

    merged["_ancestors"] = deduped

    # ---------- IMPORTANT FIX FOR `descendants` ----------
    # Do NOT inherit descendants from base classes.
    # Keep only the descendants defined on this class itself (if any).
    if "descendants" in data:
        # class defines its own descendants
        from copy import deepcopy
        merged["descendants"] = deepcopy(data["descendants"])
    elif "descendants" in merged:
        # only came from base; drop it
        del merged["descendants"]
    # -----------------------------------------------------

    cache[name] = merged
    return merged


# ================== REFERENCE.YAML WALKER ==================


def iter_reference_objects(node, breadcrumbs=None):
    """
    Generic recursive walker that finds every dict containing a 'path' key.

    Yields dicts with:
      - path: str           (as in reference.yaml)
      - breadcrumbs: list of {id, title, type?}
      - node: the full node dict from reference.yaml
    """
    if breadcrumbs is None:
        breadcrumbs = []

    if isinstance(node, dict):
        # Compute updated breadcrumbs if this node looks like a section/group
        current_breadcrumbs = breadcrumbs
        title = node.get("title") or node.get("label") or node.get("name")
        node_id = node.get("id") or node.get("key")
        node_type = node.get("type")

        meta = {}
        if node_id:
            meta["id"] = node_id
        if title:
            meta["title"] = title
        if node_type:
            meta["type"] = node_type

        if meta:
            current_breadcrumbs = breadcrumbs + [meta]

        # If this node has a 'path', treat it as an object reference
        if "path" in node and isinstance(node["path"], str):
            yield {
                "path": normalize_rel_path(node["path"]),
                "breadcrumbs": current_breadcrumbs,
                "node": copy.deepcopy(node),
            }

        # Recurse into children / sections / etc.
        for _, value in node.items():
            if isinstance(value, (dict, list)):
                for obj in iter_reference_objects(value, current_breadcrumbs):
                    yield obj

    elif isinstance(node, list):
        for item in node:
            for obj in iter_reference_objects(item, breadcrumbs):
                yield obj


def lookup_entry_for_nav_path(raw_nav_path: str, path_index: dict):
    """
    Given a 'path' from reference.yaml, resolve it to an entry in path_index.

    Handles:
      - leading 'reference/engine/', 'en-us/reference/engine/', 'engine/', etc.
      - missing `.yaml` extension (e.g. 'classes/Object' -> 'classes/Object.yaml')
    """
    # Step 1: normalize and strip prefixes
    base_rel = resolve_doc_rel_path(raw_nav_path)

    candidates = []

    # as-is
    candidates.append(base_rel)

    # with .yaml if missing
    if not base_rel.lower().endswith(".yaml"):
        candidates.append(base_rel + ".yaml")

    # normalize and check all candidates
    for cand in candidates:
        key = normalize_rel_path(cand)
        if key in path_index:
            return key, path_index[key]

    return None, None


# ================== MAIN ==================


def main():
    if not REPO_ROOT.exists():
        raise SystemExit(f"Repo root not found: {REPO_ROOT} (adjust REPO_ROOT at top)")

    if not REFERENCE_YAML.exists():
        raise SystemExit(f"reference.yaml not found at: {REFERENCE_YAML}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Engine docs root: {ENGINE_DOC_ROOT}")
    print(f"[INFO] Loading engine objects from disk...")
    name_index, path_index = load_engine_objects()

    print(f"[INFO] Loaded {len(path_index)} engine YAML objects.")

    print(f"[INFO] Loading navigation from {REFERENCE_YAML}")
    ref_data = load_yaml(REFERENCE_YAML) or {}

    print(f"[INFO] Walking reference.yaml to find all objects...")
    nav_objects = list(iter_reference_objects(ref_data))
    print(f"[INFO] Found {len(nav_objects)} object entries in reference.yaml")

    merged_cache = {}
    count_written = 0
    missing = 0

    for obj in nav_objects:
        raw_nav_path = obj["path"]  # path as stored in reference.yaml

        doc_rel_path, entry = lookup_entry_for_nav_path(raw_nav_path, path_index)

        if not entry:
            if missing < 10:
                print(
                    f"[WARN] No YAML file for nav path '{raw_nav_path}' "
                    f"(candidates tried around ENGINE_DOC_ROOT)"
                )
            missing += 1
            continue

        merged_yaml = build_merged_for_entry(entry, name_index, merged_cache)

        record_id = "engine/" + doc_rel_path.removesuffix(".yaml")
        url = path_to_url(doc_rel_path)

        record = {
            "id": record_id,
            "name": entry["name"],
            "kind": entry["kind"],
            "path": doc_rel_path,
            "url": url,
            "breadcrumbs": obj["breadcrumbs"],
            "reference_node": obj["node"],
            "raw_yaml": entry["data"],
            "merged_yaml": merged_yaml,
        }

        out_path = OUTPUT_ROOT / doc_rel_path
        out_path = out_path.with_suffix(".json")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        count_written += 1


    print(f"[DONE] Wrote {count_written} JSON files under {OUTPUT_ROOT}")
    if missing:
        print(f"[WARN] {missing} reference entries had no matching YAML file; see logs above.")


if __name__ == "__main__":
    main()
