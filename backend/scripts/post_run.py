import json, requests
cfg = json.load(open('backend/customer_onboarding.json'))
r = requests.post('http://127.0.0.1:8000/orchestrate_async', json={'config_json': cfg, 'template_name': 'Customer_Onboarding'})
print(r.json())
