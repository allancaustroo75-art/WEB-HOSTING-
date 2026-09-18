from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any, Dict, Optional


def validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    """
    Validates Telegram WebApp initData according to official docs.
    
    https://core.telegram.org/bots/web_apps#validating-data-received-via-the-mini-app
    
    - Parse init_data as query string
    - Extract hash
    - Sort remaining keys, create data_check_string as key=value joined by \\n
    - secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token)
    - computed_hash = HMAC-SHA256(key=secret_key, msg=data_check_string) hex digest
    - Compare with received hash
    - Check auth_date not too old
    
    Returns parsed user dict if valid, else None.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed_qs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data_dict = dict(parsed_qs)
    except Exception:
        return None

    received_hash = data_dict.pop("hash", None)
    if not received_hash:
        return None

    # Check auth_date
    auth_date_str = data_dict.get("auth_date")
    if auth_date_str:
        try:
            auth_date = int(auth_date_str)
            now = int(time.time())
            if now - auth_date > max_age_seconds:
                return None
        except ValueError:
            return None

    # Build data_check_string
    data_check_arr = []
    for key in sorted(data_dict.keys()):
        data_check_arr.append(f"{key}={data_dict[key]}")
    data_check_string = "\n".join(data_check_arr)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    result: Dict[str, Any] = {"auth_date": auth_date_str}
    for k, v in data_dict.items():
        result[k] = v

    # Parse user object
    user_json = data_dict.get("user")
    if user_json:
        try:
            user_obj = json.loads(user_json)
            result["user"] = user_obj
            result["user_id"] = user_obj.get("id")
            result["username"] = user_obj.get("username")
            result["first_name"] = user_obj.get("first_name")
            result["last_name"] = user_obj.get("last_name")
            result["language_code"] = user_obj.get("language_code")
            result["is_premium"] = user_obj.get("is_premium", False)
            # Photo URL may be present in user object
            result["photo_url"] = user_obj.get("photo_url", "")
        except Exception:
            return None
    else:
        return None

    if "user_id" not in result or not result["user_id"]:
        return None

    return result


def extract_init_data_from_header(authorization: Optional[str], x_telegram_header: Optional[str]) -> Optional[str]:
    """
    Extracts initData from either Authorization: tma <initData> or X-Telegram-Init-Data header
    """
    if x_telegram_header:
        return x_telegram_header.strip()
    if authorization:
        auth = authorization.strip()
        if auth.lower().startswith("tma "):
            return auth[4:].strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if "hash=" in token:
                return token
            return None
        if "hash=" in auth:
            return auth
    return None


def is_owner_user(user_id: int, owner_id: int, admin_ids: set[int]) -> bool:
    """Check if user is owner or admin - server side only"""
    if owner_id and user_id == owner_id:
        return True
    if user_id in admin_ids:
        return True
    return False
