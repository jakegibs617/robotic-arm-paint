# Mac setup

## 1. Python environment

```bash
cd robot-arm-painter
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 2. Run in mock mode (no hardware)

```bash
painterbot-jog --mock
painterbot-draw-shape --shape square --mock --preview out/square.png
```

## 3. Find the serial port (real hardware)

Plug the controller in over USB, then:

```bash
ls /dev/tty.*
```

Look for one of:

- `/dev/tty.usbserial-XXXX` (FTDI / CH340 style adapters)
- `/dev/tty.usbmodem-XXXX` (native-USB boards, e.g. some Arduinos)

If nothing appears, you may need a USB-serial driver (CH340/CP210x). Record what
you find in [hardware_identification.md](hardware_identification.md).

## 4. Connect

```bash
painterbot-jog --port /dev/tty.usbserial-XXXX -v
```

## Emergency stop / power-off procedure

1. In the jog CLI, type `stop` (freezes the arm at its current pose) or press
   `Ctrl-C` to exit, which closes the serial port.
2. **Cut servo power at the source.** Closing the port does not de-energize the
   servos — keep the arm's power supply switch (or a barrel-jack/inline switch)
   within reach and use it as the true e-stop.
3. Keep hands clear of the workspace while powered. Start every session with
   slow motion (`motion.step_delay_s` high) until limits are verified.
