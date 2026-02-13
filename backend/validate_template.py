import json, sys
from jsonschema import validate, ValidationError

cfg_path = 'backend/customer_onboarding.json'
schema_path = 'backend/langgraph_workflow.schema.json'

try:
    # Support files with BOM (utf-8-sig) as they may be created by PowerShell
    with open(cfg_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
except Exception as e:
    print('ERROR: failed to parse JSON file:', e)
    sys.exit(2)

# The workflow config may be nested under 'template_json'
config = data.get('template_json', data)

try:
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
except Exception as e:
    print('ERROR: failed to load schema:', e)
    sys.exit(2)

print('Validating config (showing config snippet):')
print(json.dumps(config, indent=2)[:1000])

try:
    validate(instance=config, schema=schema)
    print('\nVALID: template JSON conforms to langgraph_workflow.schema.json')
except ValidationError as e:
    print('\nINVALID: template JSON failed schema validation:')
    print(e)
    sys.exit(1)
