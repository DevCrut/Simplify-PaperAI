import json
from pathlib import Path

ENGINE_OBJECTS_ROOT = Path("engine_objects")
OUTPUT_GENERAL_INDEX = Path("engine_index.jsonl")
OUTPUT_PROPERTY_INDEX = Path("engine_properties_index.jsonl")

# mapping of merged_yaml keys -> entry_kind
MEMBER_GROUPS = {
    "properties": "property",
    "methods": "method",
    "events": "event",
    "callbacks": "callback",
    "items": "enum_item",
    "fields": "field",
    "members": "library_member",
    "functions": "function",
    "constructors": "constructor",
}

def main():
    if not ENGINE_OBJECTS_ROOT.exists():
        raise SystemExit("engine_objects folder not found")

    general_f = OUTPUT_GENERAL_INDEX.open("w", encoding="utf-8")
    prop_f = OUTPUT_PROPERTY_INDEX.open("w", encoding="utf-8")

    total_general = 0
    total_props = 0

    for json_path in ENGINE_OBJECTS_ROOT.rglob("*.json"):
        rel_path = json_path.relative_to(ENGINE_OBJECTS_ROOT)

        data = json.loads(json_path.read_text("utf-8"))

        class_id = data.get("id")
        merged = data.get("merged_yaml", {})
        if not merged:
            continue

        name = merged.get("name")
        obj_type = merged.get("type", merged.get("kind", "")).lower()

        base_url = data.get("url")
        breadcrumbs = data.get("breadcrumbs", [])

        # ---------------- OVERVIEW ENTRY ----------------
        overview_kind = f"{obj_type}_overview"

        class_entry = {
            "id": f"{class_id}#overview",
            "entry_kind": overview_kind,
            "object_type": obj_type,
            "name": name,
            "source_id": class_id,
            "json_path": str(rel_path),
            "url": base_url,
            "breadcrumbs": breadcrumbs,
            "tags": merged.get("tags", []),
            "deprecated": bool(merged.get("deprecation_message")),
        }

        general_f.write(json.dumps(class_entry, ensure_ascii=False) + "\n")
        total_general += 1

        # ---------------- MEMBER ENTRIES ----------------
        for key, kind in MEMBER_GROUPS.items():
            members = merged.get(key, []) or []

            for m in members:
                if not isinstance(m, dict):
                    continue
                member_name = m.get("name")
                if not member_name:
                    continue

                entry_id = f"{class_id}#{kind}:{member_name}"

                entry = {
                    "id": entry_id,
                    "entry_kind": kind,
                    "object_type": obj_type,
                    "name": member_name,
                    "group": key,
                    "parent": name,
                    "source_id": class_id,
                    "json_path": str(rel_path),
                    "url": base_url,
                    "anchor_hint": member_name,
                    "tags": m.get("tags", []),
                    "deprecated": bool(m.get("deprecation_message")),
                }

                general_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                total_general += 1

                if kind == "property":
                    prop_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    total_props += 1

    general_f.close()
    prop_f.close()

    print(f"[DONE] Wrote {total_general} entries to {OUTPUT_GENERAL_INDEX}")
    print(f"[DONE] Wrote {total_props} property entries to {OUTPUT_PROPERTY_INDEX}")

if __name__ == "__main__":
    main()
