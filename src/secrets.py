secrets = {}

# Read secrets from mountpoint in envs where the mount is expected
with open('/secrets/settings.env') as secrets_file:
    for line in secrets_file:
        # Simple env file parsing
        line = line.strip()
        if line.startswith('#') or line == '':
            continue
        key, value = line.split('=', 1)
        secrets[key] = value
