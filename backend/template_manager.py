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
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ValidationError

TEMPLATE_DIR = "prompt_templates"
SCHEMA_PATH = "langgraph_workflow.schema.json"

class TemplateVersion(BaseModel):
    name: str
    version: str
    description: Optional[str] = None
    data: Dict[str, Any]

class TemplateManager:
    def __init__(self, template_dir: str = TEMPLATE_DIR, schema_path: str = SCHEMA_PATH):
        self.template_dir = template_dir
        self.schema_path = schema_path
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)
        self.schema = self._load_schema()

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

    def save_template(self, name: str, data: Dict[str, Any], version: Optional[str] = None, description: Optional[str] = None) -> str:
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
        data_to_save = dict(data)
        if description:
            data_to_save["description"] = description
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2)
        return fname

    # Optional: Database integration stub
    def save_to_db(self, template: TemplateVersion):
        # Implement DB save logic here
        pass

    def load_from_db(self, name: str, version: str) -> Optional[TemplateVersion]:
        # Implement DB load logic here
        return None

# Usage example:
# tm = TemplateManager()
# tm.save_template("research_writer", {...}, version="2", description="Updated for new flow")
# templates = tm.list_templates()
# t = tm.get_template("research_writer", version="2")
