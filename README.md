# pc-mate

This is a standalone project for turning phone speech or scanned code content into pasted text on a computer:

1. A phone browser performs speech recognition or scans a QR / barcode.
2. The recognized text is published to MQTT over WebSocket.
3. A Python program on the computer subscribes to the MQTT topic.
4. When a message arrives, the program copies the text to the clipboard and pastes it into the currently focused cursor position.

## Why this design

This avoids ESP32 hardware and also works better for Chinese text, because the desktop helper pastes Unicode text through the clipboard instead of simulating only ASCII key presses.

## Folder layout

- `web/`: mobile web page for speech recognition, QR/barcode scanning, and MQTT publishing
- `desktop/`: Python listener that subscribes to MQTT and pastes incoming text

## Tested target workflow

- Phone: Android Chrome or Edge
- Computer: Windows
- MQTT broker: any broker that supports
  - WebSocket for the web page
  - normal MQTT TCP for the Python client

## Example setup

- WebSocket URL for phone: `wss://broker.emqx.io:8084/mqtt`
- TCP host for desktop: `broker.emqx.io`
- TCP port for desktop: `1883`
- Topic: `$user/input`

## Python dependencies

Install these packages in your Python environment:

- `paho-mqtt`
- `pyperclip`
- `keyboard`

Example:

```powershell
pip install -r requirements.txt
```

## Important notes

- The desktop program pastes into whatever window currently has focus.
- Test in Notepad first.
- On Windows, `Ctrl+V` paste is used by default.
- If the received text contains `注意老闆來了`, the desktop helper will minimize all windows with `Win+M` instead of pasting the text.
- Some browsers require HTTPS for speech recognition features.
- Camera-based QR/barcode scanning also needs camera permission, and usually works best on mobile Chrome or Edge over HTTPS.

## Quick start

1. Create `desktop/config.json` and fill in your MQTT broker, topic, and credentials.
2. Run the desktop helper:

```powershell
python listener.py
```

3. Serve the `web/` folder from a local HTTPS host.
4. Open the page on your phone.
5. Enter the same broker and topic settings if needed.
6. Connect MQTT.
7. Use speech recognition or QR/barcode scanning.
8. Focus any text field on the computer, then send text from the phone.

## Usage guide

1. Download and unzip `pc-mate-listener.zip` on the computer, then run `pc-mate-listener`.
2. Configure MQTT settings on the computer. The topic must match the phone side.
3. Open the web page on your phone:
   `https://jjtmutw.github.io/web/pc-mate/web/`
4. In `Step 1`, enter your own `$user` name, for example `alice`.
5. The web page will automatically generate the topic:
   `alice/input`
6. The desktop listener must use the same topic, for example:
   `alice/input`
7. After `Connect MQTT` succeeds, you can start using the system.
8. Use `Step 2` for speech input, or `Step 3` to scan QR Code / Barcode.
9. The content will appear in `Step 4`. Confirm it, then press send.
10. When the desktop listener receives the message, it will automatically paste the text into the current cursor position.

## Multi-user usage

- Each user should use a different `$user`.
- Example:
  - `alice` -> `alice/input`
  - `bob` -> `bob/input`
  - `cashier1` -> `cashier1/input`
- This prevents users from interfering with each other.

## Security reminder

Anyone who can publish to your configured MQTT topic can cause text to be pasted on your computer. Use authentication and a private topic.
