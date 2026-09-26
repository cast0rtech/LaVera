"""
Tesla Fleet API Security & Authentication Manager.
Handles OAuth 2.0 token acquisition, proactive token refresh, and
ECDSA NIST P-256 (secp256r1) keypair generation and command signing.
"""

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("lavera.gateway.security")

# Optional cryptography import for ECDSA secp256r1 signing
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class TeslaSecurityManager:
    """
    Manages OAuth2 token lifecycle and cryptographic command signing keys for Tesla Fleet API.
    """

    OAUTH_HOSTS = {
        "na": "https://auth.tesla.com",
        "eu": "https://auth.tesla.com",
        "cn": "https://auth.tesla.cn",
    }

    FLEET_API_HOSTS = {
        "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
        "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
        "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.com",
    }

    def __init__(self, client_id: str = "", client_secret: str = "",
                 refresh_token: str = "", region: str = "eu",
                 private_key_pem: Optional[str] = None):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.refresh_token = refresh_token.strip()
        self.region = region.lower() if region.lower() in ("na", "eu", "cn") else "eu"
        self.private_key_pem = private_key_pem

        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0.0

    @property
    def oauth_base_url(self) -> str:
        return self.OAUTH_HOSTS.get(self.region, "https://auth.tesla.com")

    @property
    def fleet_base_url(self) -> str:
        return self.FLEET_API_HOSTS.get(self.region, "https://fleet-api.prd.eu.vn.cloud.tesla.com")

    def get_valid_access_token(self) -> str:
        """
        Returns a valid access token. Automatically refreshes if token is missing
        or within 300 seconds (5 minutes) of expiring.
        """
        now = time.time()
        if self.access_token and now < (self.token_expires_at - 300):
            return self.access_token

        # Proactively refresh token
        return self.refresh_token_grant()

    def refresh_token_grant(self) -> str:
        """
        Executes standard OAuth2 refresh_token grant flow against Tesla Auth server.
        """
        if not self.refresh_token:
            raise ValueError("No se ha configurado 'refresh_token' de Tesla Fleet API.")
        if not self.client_id:
            raise ValueError("No se ha configurado 'client_id' de Tesla Fleet API.")

        url = f"{self.oauth_base_url}/oauth2/v3/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "LaVera-EV-Hub/1.2",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                new_token = data.get("access_token")
                expires_in = int(data.get("expires_in", 28800))  # Default 8 hours
                new_refresh = data.get("refresh_token")

                if not new_token:
                    raise RuntimeError("Tesla Auth no devolvió access_token en la respuesta.")

                self.access_token = new_token
                self.token_expires_at = time.time() + expires_in
                if new_refresh:
                    self.refresh_token = new_refresh

                logger.info("[Security] Tesla Fleet access token refreshed successfully.")
                return self.access_token
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"Error renovando token Tesla Fleet ({e.code}): {err_body or e.reason}")
        except Exception as e:
            raise RuntimeError(f"Fallo de conexión al renovar token Tesla: {str(e)}")

    def get_partner_token(self, scope: str = "openid vehicle_device_data vehicle_cmds") -> str:
        """
        Executes client_credentials flow for Fleet Partner account access.
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("client_id y client_secret son obligatorios para Partner Token.")

        url = f"{self.oauth_base_url}/oauth2/v3/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": scope,
            "audience": self.fleet_base_url,
        }

        encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 28800))
            self.access_token = token
            self.token_expires_at = time.time() + expires_in
            return token

    # --- Cryptographic Key Pair Management (ECDSA NIST P-256 / secp256r1) ---

    @staticmethod
    def generate_fleet_keypair() -> Tuple[str, str]:
        """
        Generates a new ECDSA NIST P-256 keypair.
        Returns: (private_key_pem, public_key_pem)
        """
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError("Biblioteca 'cryptography' no disponible para generar claves ECDSA.")

        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        return private_pem, public_pem

    def sign_command_payload(self, payload_bytes: bytes) -> bytes:
        """
        Signs arbitrary binary command payload using ECDSA with SHA-256 for Tesla Command Protocol.
        """
        if not self.private_key_pem:
            raise ValueError("No hay clave privada configurada para firmar comandos.")
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError("Biblioteca 'cryptography' requerida para firmar comandos.")

        private_key = serialization.load_pem_private_key(
            self.private_key_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )
        signature = private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
        return signature
