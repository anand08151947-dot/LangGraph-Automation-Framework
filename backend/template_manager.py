"""
template_manager.py
Robust template management for LangGraph Automation Framework
Features:
- Load templates from file system (with versioning)
- Validate templates against schema
- List, get, and save templates
- (Optional) Database integration stub
"""

import os
import json
import sqlite3
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ValidationError

TEMPLATE_DIR = "prompt_templates"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schemas", "langgraph_workflow.schema.json")

class TemplateVersion(BaseModel):
    name: str
    version: str
    description: Optional[str] = None
    data: Dict[str, Any]

class TemplateManager:
    def __init__(self, template_dir: str = TEMPLATE_DIR, schema_path: str = SCHEMA_PATH,
                 db_path: str = None):
        self.template_dir = template_dir
        self.schema_path = schema_path
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)
        self.schema = self._load_schema()

        # CFG-3: SQLite DB-backed template storage
        self._db_conn: Optional[sqlite3.Connection] = None
        if db_path:
            self._db_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._db_conn.execute(
                "CREATE TABLE IF NOT EXISTS templates("
                "name TEXT, version TEXT, description TEXT, data TEXT, created_at REAL, "
                "PRIMARY KEY(name, version))"
            )
            self._db_conn.commit()

    def _load_schema(self) -> Dict[str, Any]:
        if not os.path.exists(self.schema_path):
            return {}
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_templates(self) -> List[TemplateVersion]:
        templates = []
        for fname in os.listdir(self.template_dir):
            if fname.endswith(".json"):
                parts = fname[:-5].split("__v")
                name = parts[0]
                version = parts[1] if len(parts) > 1 else "1"
                with open(os.path.join(self.template_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                templates.append(TemplateVersion(name=name, version=version, description=data.get("description"), data=data))
        return templates

    def get_template(self, name: str, version: Optional[str] = None) -> Optional[TemplateVersion]:
        for t in self.list_templates():
            if t.name == name and (version is None or t.version == version):
                return t
        return None

    def save_template(self, name: str, data: Dict[str, Any], version: Optional[str] = None,
                      description: Optional[str] = None, overwrite: bool = False) -> str:
        # Validate against schema
        if self.schema:
            from jsonschema import validate, ValidationError as SchemaValidationError
            try:
                validate(instance=data, schema=self.schema)
            except SchemaValidationError as e:
                raise ValueError(f"Template validation failed: {e}")
        # Versioning
        version = version or "1"
        fname = f"{name}__v{version}.json"
        path = os.path.join(self.template_dir, fname)
        # CFG-4: conflict detection
        if os.path.exists(path) and not overwrite:
            raise ValueError(
                f"Template '{name}' version '{version}' already exists. "
                "Set overwrite=True to replace."
            )
        data_to_save = dict(data)
        if description:
            data_to_save["description"] = description
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2)
        # CFG-3: persist to DB if configured
        tv = TemplateVersion(name=name, version=version, description=description, data=data_to_save)
        self.save_to_db(tv)
        return fname

    # CFG-4: diff two template versions
    def diff_templates(self, name: str, v1: str, v2: str) -> Dict[str, Any]:
        """Compare two versions of a template. Returns {added, removed, modified}."""
        t1 = self.get_template(name, v1)
        t2 = self.get_template(name, v2)
        if t1 is None:
            raise ValueError(f"Template '{name}' version '{v1}' not found")
        if t2 is None:
            raise ValueError(f"Template '{name}' version '{v2}' not found")
        d1, d2 = t1.data, t2.data
        added = {k: d2[k] for k in d2 if k not in d1}
        removed = {k: d1[k] for k in d1 if k not in d2}
        modified = {k: {"from": d1[k], "to": d2[k]} for k in d1 if k in d2 and d1[k] != d2[k]}
        return {"added": added, "removed": removed, "modified": modified}

    # CFG-3: Database integration
    def save_to_db(self, template: TemplateVersion):
        """Persist a template version to SQLite."""
        if self._db_conn is None:
            return
        self._db_conn.execute(
            "INSERT OR REPLACE INTO templates(name, version, description, data, created_at) "
            "VALUES (?,?,?,?,?)",
            (
                template.name,
                template.version,
                template.description or "",
                json.dumps(template.data),
                time.time(),
            ),
        )
        self._db_conn.commit()

    def load_from_db(self, name: str, version: str) -> Optional[TemplateVersion]:
        """Load a specific template version from SQLite."""
        if self._db_conn is None:
            return None
        cur = self._db_conn.execute(
            "SELECT name, version, description, data FROM templates WHERE name=? AND version=?",
            (name, version),
        )
        row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(row[3])
        return TemplateVersion(name=row[0], version=row[1], description=row[2] or None, data=data)

    def list_from_db(self) -> List[TemplateVersion]:
        """Return all templates from SQLite DB."""
        if self._db_conn is None:
            return []
        cur = self._db_conn.execute(
            "SELECT name, version, description, data FROM templates"
        )
        results = []
        for row in cur.fetchall():
            try:
                data = json.loads(row[3])
                results.append(TemplateVersion(name=row[0], version=row[1],
                                               description=row[2] or None, data=data))
            except Exception:
                pass
        return results

# Usage example:
# tm = TemplateManager()
# tm.save_template("research_writer", {...}, version="2", description="Updated for new flow")
# templates = tm.list_templates()
# t = tm.get_template("research_writer", version="2")
