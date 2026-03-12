import requests, json, time
base='http://127.0.0.1:8000'
print('health', requests.get(base+'/health').json())
print('readiness', requests.get(base+'/readiness').json())
print('config', requests.get(base+'/config').json())
print('templates', requests.get(base+'/templates').status_code, requests.get(base+'/templates').json()[:1])
# STM
print('get stm (expect 404)', requests.get(base+'/memory/stm/pytestsession').status_code)
print('save stm', requests.post(base+'/memory/stm/pytestsession', json={'a':1}).json())
print('get stm', requests.get(base+'/memory/stm/pytestsession').json())
# LTM (empty)
print('get ltm (empty)', requests.get(base+'/memory/ltm/pytestsession').json())
# Tools (API key)
headers={'x-api-key':'sk-REPLACE_ME'}
print('tools list', requests.get(base+'/tools', headers=headers).status_code, requests.get(base+'/tools', headers=headers).text)
# English to JSON (manual mode)
print('english_to_json', requests.post(base+'/english_to_json', json={'instructions':'Create a simple workflow'}).json())
# Orchestrate async
r = requests.post(base+'/orchestrate_async', json={'config_json': {'example': 'data'}})
print('orchestrate_async', r.status_code, r.json())
run_id = r.json().get('run_id')
# Wait and check status
time.sleep(1)
print('status', requests.get(base+f'/status/{run_id}').json())
# tools health
print('tools health', requests.get(base+'/tools/health', headers=headers).json())
