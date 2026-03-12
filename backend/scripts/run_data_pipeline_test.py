import requests, time, json, sys

base = 'http://127.0.0.1:8000'
config = {
    "graph_name": "Data_Pipeline_Review",
    "agents": [
        {"name": "DataCollector", "system_prompt": "Collect raw data from sources.", "tools": ["data_api"], "next": "Reviewer"},
        {"name": "Reviewer", "system_prompt": "Review collected data for quality. If not approved, return to DataCollector.", "tools": [], "next": "Processor"},
        {"name": "Processor", "system_prompt": "Process and transform data.", "tools": ["transform_tool"], "next": "FinalReviewer"},
        {"name": "FinalReviewer", "system_prompt": "Approve processed data for storage. If not approved, return to Processor.", "tools": [], "next": "END"}
    ]
}

print('Posting orchestration request...')
r = requests.post(f'{base}/orchestrate_async', json={'config_json': config})
print('POST /orchestrate_async', r.status_code, r.text)
if r.status_code != 200:
    print('Failed to start orchestration')
    sys.exit(1)
run_id = r.json().get('run_id')
print('Run ID:', run_id)

# Poll for status
for i in range(120):
    s = requests.get(f'{base}/status/{run_id}')
    try:
        data = s.json()
    except Exception:
        data = {'status': 'unknown', 'raw': s.text}
    print(f'[{i}] status:', data)
    if data.get('status') in ('completed', 'error'):
        break
    time.sleep(0.2)

print('\nFinal status:', data)
# Fetch STM and LTM
stm_r = requests.get(f'{base}/memory/stm/{run_id}')
ltm_r = requests.get(f'{base}/memory/ltm/{run_id}')
print('\nSTM status:', stm_r.status_code)
if stm_r.status_code == 200:
    print('STM:', json.dumps(stm_r.json(), indent=2))
else:
    print('STM body:', stm_r.text)

print('\nLTM status:', ltm_r.status_code)
if ltm_r.status_code == 200:
    print('LTM:', json.dumps(ltm_r.json(), indent=2))
else:
    print('LTM body:', ltm_r.text)
