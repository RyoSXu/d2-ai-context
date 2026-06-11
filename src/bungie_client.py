from __future__ import annotations

from typing import Any

import requests

from .config import Settings, require_api_key


class BungieApiError(RuntimeError):
    pass


class BungieClient:
    def __init__(self, settings: Settings, access_token: str | None = None) -> None:
        require_api_key(settings)
        self.settings = settings
        self.access_token = access_token
        self.session = requests.Session()

    def _headers(self, auth: bool = False) -> dict[str, str]:
        headers = {"X-API-Key": self.settings.api_key}
        if auth:
            if not self.access_token:
                raise BungieApiError("需要 OAuth access_token，但当前没有可用 token。")
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request(self, method: str, path: str, *, auth: bool = False, **kwargs: Any) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.settings.api_root}{path}"
        try:
            response = self.session.request(method, url, headers=self._headers(auth=auth), timeout=60, **kwargs)
        except requests.RequestException as exc:
            raise BungieApiError(f"Bungie API 请求失败：{exc}") from exc

        if response.status_code >= 400:
            message = self._extract_error(response)
            raise BungieApiError(f"HTTP {response.status_code}: {message}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise BungieApiError(f"HTTP {response.status_code}: 响应不是 JSON。") from exc

        error_code = payload.get("ErrorCode", 1)
        if error_code not in (1, "1"):
            status = payload.get("ErrorStatus", "Unknown")
            message = payload.get("Message", "")
            raise BungieApiError(f"Bungie ErrorCode {error_code} ({status}): {message}")
        return payload

    def get_response(self, path: str, *, auth: bool = False, **kwargs: Any) -> Any:
        return self.request("GET", path, auth=auth, **kwargs).get("Response")

    @staticmethod
    def _extract_error(response: requests.Response) -> str:
        try:
            payload = response.json()
            return payload.get("Message") or payload.get("ErrorStatus") or response.text[:500]
        except ValueError:
            return response.text[:500]

