# Verification

Use the project virtualenv explicitly. In this workspace, plain `python` may
resolve to a pyenv interpreter without the project dependencies.

## Local Test Suite

```bash
.venv/bin/python -m pytest -q
```

## No-Hardware Smoke Checks

```bash
.venv/bin/python -m painterbot.apps.bringup list-joints
.venv/bin/python -m painterbot.apps.bringup mock-session
.venv/bin/python -m painterbot.apps.calibrate_workspace --dry-run
.venv/bin/python -m painterbot.apps.draw_shape --shape square --dry-run
.venv/bin/python -m painterbot.apps.draw_shape --shape square --preview out/square.png
.venv/bin/python -m painterbot.apps.draw_svg examples/star.svg --dry-run
.venv/bin/python -m painterbot.apps.draw_svg examples/star.svg --preview out/star.png
```

All commands above are hardware-safe. They do not require a serial port and do
not modify real calibration configs.

## Optional Scan Extras

iPhone LiDAR / mesh import work is optional and uses the `scan` extra:

```bash
.venv/bin/python -m pip install -e ".[scan]"
```

Run scan-specific checks only after those extras are installed.
