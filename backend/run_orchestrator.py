import json
from backend.orchestrator import Orchestrator
cfg = json.load(open('backend/customer_onboarding.json'))
orch = Orchestrator()
res = orch.run_workflow(cfg, session_id='onboard_manual_run')
print(res)
