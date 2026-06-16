# -*- coding: utf-8 -*-
"""
BeyondTrust Password Safe oturum (session) ve HTTP istemcisi.

Tek bir `BeyondTrustSession` nesnesi:
  * SignAppin ile authenticate olur, ASP.NET_SessionId cookie'sini saklar,
  * sonraki tüm isteklerde bu cookie'yi otomatik ekler,
  * get / post / delete için ortak hata yönetimi + tekrar deneme sağlar.

Referans projedeki "session id'yi global env'e koy" yaklaşımının aksine, durum
nesnenin içinde tutulur; bu test edilebilir ve birden çok oturuma açıktır.
"""

from __future__ import annotations

import warnings
from typing import Any, Optional

import requests
from urllib3.exceptions import InsecureRequestWarning

from common.logging_setup import get_logger

log = get_logger("bt.session")


class BeyondTrustError(Exception):
    """BeyondTrust REST katmanı genel hatası."""


class AuthenticationError(BeyondTrustError):
    """Kimlik doğrulama başarısız."""


class BeyondTrustSession:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        runas_user: str,
        verify_ssl: bool = False,
        timeout: int = 30,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.runas_user = runas_user
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries

        self._http = requests.Session()
        self._http.verify = verify_ssl
        self.session_id: Optional[str] = None

        if not verify_ssl:
            # Test ortamında self-signed sertifika uyarılarını bastır.
            warnings.simplefilter("ignore", InsecureRequestWarning)

    # ------------------------------------------------------------------ #
    @property
    def _auth_header(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"PS-Auth key={self.api_key}; runas={self.runas_user};",
        }

    @property
    def _cookie_header(self) -> dict:
        if not self.session_id:
            raise AuthenticationError(
                "Oturum açılmadı. Önce authenticate() çağrılmalı."
            )
        return {"Cookie": f"ASP.NET_SessionId={self.session_id}"}

    # ------------------------------------------------------------------ #
    def authenticate(self) -> str:
        """SignAppin -> ASP.NET_SessionId döndürür ve saklar."""
        url = f"{self.base_url}/Auth/SignAppin"
        log.info("BeyondTrust authenticate: %s (runas=%s)", url, self.runas_user)
        try:
            resp = self._http.post(
                url, headers=self._auth_header, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise AuthenticationError(f"SignAppin isteği başarısız: {exc}") from exc

        session_id = resp.cookies.get("ASP.NET_SessionId") or self._http.cookies.get(
            "ASP.NET_SessionId"
        )
        if not session_id:
            raise AuthenticationError(
                "ASP.NET_SessionId cookie alınamadı. Yanıt: " + resp.text[:200]
            )
        self.session_id = session_id
        try:
            who = resp.json()
            log.info(
                "Authentication başarılı. Kullanıcı=%s, UserId=%s, SessionId=%s",
                who.get("UserName"),
                who.get("UserId"),
                session_id,
            )
        except Exception:
            log.info("Authentication başarılı. SessionId=%s", session_id)
        return session_id

    def sign_out(self) -> None:
        """Oturumu kapatır (best-effort)."""
        if not self.session_id:
            return
        try:
            self._http.post(
                f"{self.base_url}/Auth/Signout",
                headers=self._cookie_header,
                timeout=self.timeout,
            )
            log.debug("Oturum kapatıldı (Signout).")
        except requests.RequestException as exc:
            log.debug("Signout başarısız (önemsiz): %s", exc)
        finally:
            self.session_id = None

    # ------------------------------------------------------------------ #
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = dict(self._cookie_header)
        if method in ("POST", "PUT", "PATCH"):
            headers["Content-Type"] = "application/json"
        headers.update(kwargs.pop("headers", {}) or {})

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 2):
            try:
                log.debug("HTTP %s %s (deneme %d)", method, url, attempt)
                resp = self._http.request(
                    method, url, headers=headers, timeout=self.timeout, **kwargs
                )
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                log.warning(
                    "HTTP %s %s hata (deneme %d/%d): %s",
                    method,
                    url,
                    attempt,
                    self.max_retries + 1,
                    exc,
                )
        raise BeyondTrustError(
            f"{method} {url} {self.max_retries + 1} denemede başarısız: {last_exc}"
        )

    def get(self, path: str, **kwargs) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, json: Any = None, data: Any = None, **kwargs) -> requests.Response:
        return self._request("POST", path, json=json, data=data, **kwargs)

    def put(self, path: str, json: Any = None, data: Any = None, **kwargs) -> requests.Response:
        return self._request("PUT", path, json=json, data=data, **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        return self._request("DELETE", path, **kwargs)
