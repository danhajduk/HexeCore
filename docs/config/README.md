# Configuration Docs

Status: Implemented

- [environment.md](./environment.md) is generated from [core-env-registry.json](./core-env-registry.json).

Update workflow:

```bash
python tools/check_env_registry.py --write-docs
python tools/check_env_registry.py --check-docs
```
