"""Generate one Web Push VAPID key pair for server environment variables.

Run locally after installing requirements. The private key is printed once and
must be stored only in the deployment environment, never in source control.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_number = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_point = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    print("WEB_PUSH_ENABLED=true")
    print(f"VAPID_PUBLIC_KEY={base64url(public_point)}")
    print(f"VAPID_PRIVATE_KEY={base64url(private_number)}")
    print("VAPID_SUBJECT=mailto:SEU_EMAIL_DE_SUPORTE")
    print("WEB_PUSH_TTL_SECONDS=86400")
    print("WEB_PUSH_TIMEOUT_SECONDS=12")


if __name__ == "__main__":
    main()
