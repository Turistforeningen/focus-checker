import json

with open('/secrets/secrets.json') as f:
    secrets = json.loads(f.read())
