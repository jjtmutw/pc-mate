import base64
import json
import logging
import pathlib
import socket
import sys
import time
from typing import Any
from urllib.parse import urlparse

import keyboard
import paho.mqtt.client as mqtt
import pyperclip


if getattr(sys, "frozen", False):
    BASE_DIR = pathlib.Path(sys.executable).resolve().parent
else:
    BASE_DIR = pathlib.Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config.json"
DOWNLOADS_DIR = pathlib.Path.home() / "Downloads"
MINIMIZE_ALL_TRIGGER = "注意老闆來了"
ALLOWED_KEY_COMMANDS = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "pageup": "page up",
    "pagedown": "page down",
}
FILE_TRANSFERS: dict[str, dict[str, Any]] = {}


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
        raise ValueError("MQTT host 為空白，請在 config.json 設定有效的 broker 主機名稱或 IP。")

    if "://" in host:
        parsed = urlparse(host)
        if not parsed.hostname:
            raise ValueError(
                "MQTT host 格式不正確。config.json 的 host 請只填主機名稱或 IP，例如 test.mosquitto.org。"
            )
        return parsed.hostname

    if "/" in host:
        raise ValueError(
            "config.json 的 MQTT host 不要包含 /mqtt 這類路徑，請只填主機名稱或 IP。"
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
    logging.info("觸發最小化所有視窗。")
    keyboard.send("windows+m")


def send_key_command(key_name: str) -> bool:
    normalized_key = ALLOWED_KEY_COMMANDS.get(key_name.lower())
    if not normalized_key:
        logging.warning("收到不支援的按鍵指令：%s", key_name)
        return False

    logging.info("送出按鍵指令：%s", normalized_key)
    keyboard.send(normalized_key)
    return True


def sanitize_filename(filename: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in filename).strip(" .")
    return cleaned or "downloaded_file"


def unique_download_path(filename: str) -> pathlib.Path:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    candidate = DOWNLOADS_DIR / sanitize_filename(filename)
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        alternative = DOWNLOADS_DIR / f"{stem}_{counter}{suffix}"
        if not alternative.exists():
            return alternative
        counter += 1


def start_file_transfer(data: dict[str, Any]) -> None:
    transfer_id = str(data.get("transfer_id", "")).strip()
    if not transfer_id:
        logging.warning("收到缺少 transfer_id 的 file_start。")
        return

    FILE_TRANSFERS[transfer_id] = {
        "name": str(data.get("name", "downloaded_file")).strip() or "downloaded_file",
        "mime_type": str(data.get("mime_type", "application/octet-stream")).strip(),
        "size": int(data.get("size", 0) or 0),
        "total_chunks": int(data.get("total_chunks", 0) or 0),
        "chunks": {},
    }
    logging.info(
        "開始接收檔案：%s，共 %s bytes，%s chunks",
        FILE_TRANSFERS[transfer_id]["name"],
        FILE_TRANSFERS[transfer_id]["size"],
        FILE_TRANSFERS[transfer_id]["total_chunks"],
    )


def store_file_chunk(data: dict[str, Any]) -> None:
    transfer_id = str(data.get("transfer_id", "")).strip()
    transfer = FILE_TRANSFERS.get(transfer_id)
    if not transfer:
        logging.warning("收到未知 transfer_id 的檔案分段：%s", transfer_id)
        return

    try:
        chunk_index = int(data.get("index", -1))
        chunk_data = base64.b64decode(str(data.get("data", "")), validate=True)
    except (ValueError, base64.binascii.Error) as error:
        logging.warning("檔案分段解碼失敗：%s", error)
        return

    transfer["chunks"][chunk_index] = chunk_data
    logging.info(
        "收到檔案分段：%s (%s/%s)",
        transfer["name"],
        chunk_index + 1,
        transfer["total_chunks"],
    )


def finalize_file_transfer(data: dict[str, Any]) -> None:
    transfer_id = str(data.get("transfer_id", "")).strip()
    transfer = FILE_TRANSFERS.pop(transfer_id, None)
    if not transfer:
        logging.warning("收到未知 transfer_id 的 file_end：%s", transfer_id)
        return

    total_chunks = transfer["total_chunks"]
    received_chunks = transfer["chunks"]
    missing_chunks = [index for index in range(total_chunks) if index not in received_chunks]
    if missing_chunks:
        logging.warning("檔案 %s 缺少分段：%s", transfer["name"], missing_chunks)
        return

    file_bytes = b"".join(received_chunks[index] for index in range(total_chunks))
    destination = unique_download_path(transfer["name"])
    destination.write_bytes(file_bytes)
    logging.info("檔案已儲存到：%s", destination)


def parse_payload(payload: bytes, append_enter_default: bool) -> dict[str, Any]:
    raw_text = payload.decode("utf-8", errors="replace").strip()
    if not raw_text:
        return {
            "action": "text",
            "text": "",
            "append_enter": append_enter_default,
        }

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "action": "text",
            "text": raw_text,
            "append_enter": append_enter_default,
        }

    action = str(data.get("action", "text")).strip().lower() or "text"
    data["action"] = action
    data["text"] = str(data.get("text", "")).strip()
    data["key"] = str(data.get("key", "")).strip().lower()
    data["append_enter"] = bool(data.get("append_enter", append_enter_default))
    return data


def on_connect(
    client: mqtt.Client,
    userdata: dict[str, Any],
    flags: dict[str, Any],
    reason_code: int,
    properties: Any = None,
) -> None:
    topic = userdata["topic"]
    logging.info("已連線到 MQTT broker，準備訂閱 topic：%s", topic)
    client.subscribe(topic, qos=1)


def on_message(client: mqtt.Client, userdata: dict[str, Any], message: mqtt.MQTTMessage) -> None:
    paste_hotkey = userdata["paste_hotkey"]
    append_enter_default = userdata["append_enter_default"]
    data = parse_payload(message.payload, append_enter_default)
    action = data["action"]

    if action == "key":
        if not data["key"]:
            logging.warning("收到空白按鍵指令，已略過。")
            return
        send_key_command(data["key"])
        return

    if action == "file_start":
        start_file_transfer(data)
        return

    if action == "file_chunk":
        store_file_chunk(data)
        return

    if action == "file_end":
        finalize_file_transfer(data)
        return

    text = data["text"]
    append_enter = data["append_enter"]

    if not text:
        logging.warning("從 %s 收到空白內容，已略過。", message.topic)
        return

    logging.info("收到文字內容，topic=%s text=%s", message.topic, text)

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
    logging.info("檔案會儲存到：%s", DOWNLOADS_DIR)

    try:
        client.connect(
            host=host,
            port=port,
            keepalive=keepalive,
        )
    except socket.gaierror as error:
        raise SystemExit(
            f"無法解析 MQTT 主機 '{host}'。請檢查 desktop/config.json 的 host 是否正確，原始錯誤：{error}"
        ) from error
    except ConnectionRefusedError as error:
        raise SystemExit(
            f"MQTT broker 拒絕連線：{host}:{port}。請確認 port、TLS 與 broker 設定。"
        ) from error
    except TimeoutError as error:
        raise SystemExit(
            f"連線 MQTT broker {host}:{port} 逾時。請確認網路連線與 broker 狀態。"
        ) from error

    client.loop_forever()


if __name__ == "__main__":
    main()
