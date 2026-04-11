import json
import logging
import pathlib
import socket
import sys
import time
from urllib.parse import urlparse
from typing import Any

import keyboard
import paho.mqtt.client as mqtt
import pyperclip


if getattr(sys, "frozen", False):
    BASE_DIR = pathlib.Path(sys.executable).resolve().parent
else:
    BASE_DIR = pathlib.Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config.json"
MINIMIZE_ALL_TRIGGER = "注意老闆來了"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"找不到設定檔：{CONFIG_PATH}。請先將 config.example.json 複製為 config.json。"
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_host(raw_host: str) -> str:
    host = raw_host.strip()
    if not host:
        raise ValueError("MQTT host is empty. Please set a valid broker hostname or IP in config.json.")
        

    # If the user pasted a URL like ws://broker:8083/mqtt or mqtt://broker,
    # extract only the hostname because paho-mqtt expects host and port separately.
    if "://" in host:
        parsed = urlparse(host)
        if not parsed.hostname:
            raise ValueError(
                "MQTT host 格式不正確。config.json 只需要填主機名稱或 IP，"
                '例如 "test.mosquitto.org" 或 "192.168.1.10"。'
            )
        return parsed.hostname

    if "/" in host:
        raise ValueError(
            "config.json 的 MQTT host 不可包含 /mqtt 這類路徑，"
            "只填主機名稱或 IP 即可。"
        )

    return host


def paste_text(text: str, append_enter: bool, paste_hotkey: str) -> None:
    if not text:
        logging.warning("收到空白文字，略過貼上。")
        return

    pyperclip.copy(text)
    time.sleep(0.05)
    keyboard.send(paste_hotkey)

    if append_enter:
        time.sleep(0.05)
        keyboard.send("enter")


def minimize_all_windows() -> None:
    logging.info("觸發縮小所有視窗。")
    keyboard.send("windows+m")


def parse_payload(payload: bytes, append_enter_default: bool) -> tuple[str, bool]:
    raw_text = payload.decode("utf-8", errors="replace").strip()
    if not raw_text:
        return "", append_enter_default

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text, append_enter_default

    text = str(data.get("text", "")).strip()
    append_enter = bool(data.get("append_enter", append_enter_default))
    return text, append_enter


def on_connect(
    client: mqtt.Client,
    userdata: dict[str, Any],
    flags: dict[str, Any],
    reason_code: int,
    properties: Any = None,
) -> None:
    topic = userdata["topic"]
    logging.info("Connected to MQTT broker. Subscribing to topic: %s", topic)
    logging.info("已連線 MQTT，訂閱主題：%s", topic)
    client.subscribe(topic)


def on_message(client: mqtt.Client, userdata: dict[str, Any], message: mqtt.MQTTMessage) -> None:
    paste_hotkey = userdata["paste_hotkey"]
    append_enter_default = userdata["append_enter_default"]
    text, append_enter = parse_payload(message.payload, append_enter_default)

    if not text:
        logging.warning("主題 %s 收到空白內容。", message.topic)
        return

    logging.info("收到訊息 %s：%s", message.topic, text)

    if MINIMIZE_ALL_TRIGGER in text:
        minimize_all_windows()
        return

    paste_text(text, append_enter, paste_hotkey)


def build_client(config: dict[str, Any]) -> mqtt.Client:
    userdata = {
        "topic": config["topic"],
        "paste_hotkey": config.get("paste_hotkey", "ctrl+v"),
        "append_enter_default": config.get("append_enter_default", True),
    }

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata=userdata)

    username = config.get("username", "")
    password = config.get("password", "")
    if username:
        client.username_pw_set(username, password)

    if config.get("use_tls", False):
        client.tls_set()

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main() -> None:
    config = load_config()
    client = build_client(config)
    host = normalize_host(str(config.get("host", "")))
    port = int(config.get("port", 1883))
    keepalive = int(config.get("keepalive", 60))

    logging.info("桌面貼上監聽器已啟動。")
    logging.info("請先把電腦焦點放到要輸入的欄位。")

    try:
        client.connect(
            host=host,
            port=port,
            keepalive=keepalive,
        )
    except socket.gaierror as error:
        raise SystemExit(
            f"無法解析 MQTT 主機 '{host}'。請檢查 desktop/config.json，將範例主機改成真實 broker 網域或區網 IP。原始錯誤：{error}"
        ) from error
    except ConnectionRefusedError as error:
        raise SystemExit(
            f"MQTT broker 拒絕連線 {host}:{port}。請檢查 port、TLS、帳密，以及 broker 是否開放 TCP MQTT。"
        ) from error
    except TimeoutError as error:
        raise SystemExit(
            f"連線 MQTT broker {host}:{port} 逾時。請檢查網路、防火牆與 broker 位址。"
        ) from error

    client.loop_forever()


if __name__ == "__main__":
    main()
