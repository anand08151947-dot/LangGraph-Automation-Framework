import json
from pathlib import Path
from typing import List, Dict, Optional

TEMPLATE_FILES = [
    "prompt_templates.json",
    "prompt_templates_advanced.json",
    "prompt_templates_expert.json",
    "prompt_templates_domains.json",
    "prompt_templates_industries.json",
    "prompt_templates_verticals.json",
    "prompt_templates_sectors.json",
    "prompt_templates_areas.json"
]

class TemplateSelector:
    def __init__(self, template_dir: str):
        self.template_dir = Path(template_dir)
        self.templates = self._load_all_templates()

    def _load_all_templates(self) -> List[Dict]:
        all_templates = []
        for file_name in TEMPLATE_FILES:
            file_path = self.template_dir / file_name
            if file_path.exists():
                with open(file_path, "r") as f:
                    try:
                        templates = json.load(f)
                        all_templates.extend(templates)
                    except Exception as e:
                        print(f"Error loading {file_name}: {e}")
        return all_templates

    def find_templates(self, keyword: str) -> List[Dict]:
        keyword_lower = keyword.lower()
        matches = [tpl for tpl in self.templates if keyword_lower in tpl.get("use_case", "").lower() or keyword_lower in tpl.get("description", "").lower()]
        return matches

    def list_all_use_cases(self) -> List[str]:
        return [tpl.get("use_case", "") for tpl in self.templates]

if __name__ == "__main__":
    import sys
    template_dir = Path(__file__).parent
    selector = TemplateSelector(template_dir)
    if len(sys.argv) == 1:
        print("Available use cases:")
        for use_case in selector.list_all_use_cases():
            print(f"- {use_case}")
    elif len(sys.argv) == 2:
        keyword = sys.argv[1]
        matches = selector.find_templates(keyword)
        if matches:
            print(f"Templates matching '{keyword}':")
            for tpl in matches:
                print(json.dumps(tpl, indent=2))
        else:
            print(f"No templates found for '{keyword}'.")
    else:
        print("Usage: python template_selector.py [keyword]")
