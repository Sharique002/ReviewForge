"""
Script to generate rich, realistic real-world test ZIP archives for ReviewForge.
1. RealWorld_PaymentGateway.zip (Clean enterprise e-commerce payment service with unit tests)
2. RealWorld_UserAuth_SecurityDefect.zip (Realistic authentication service with a security defect)
"""

import os
import zipfile
import shutil

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sample_test_zips"))
FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures"))
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FIXTURES_DIR, exist_ok=True)


def build_realworld_payment_gateway():
    """Generates RealWorld_PaymentGateway.zip - Clean, high quality production PR."""
    zip_path = os.path.join(OUTPUT_DIR, "RealWorld_PaymentGateway.zip")
    fixture_path = os.path.join(FIXTURES_DIR, "realworld_payment_gateway.zip")

    # Base code
    base_models = '''"""E-Commerce Core Domain Models."""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class OrderItem:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass
class CustomerOrder:
    order_id: str
    customer_id: str
    items: List[OrderItem]
    currency: str = "USD"
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_amount_cents(self) -> int:
        return sum(item.unit_price_cents * item.quantity for item in self.items)
'''

    base_gateway = '''"""Payment Gateway Integration."""
import uuid
from typing import Dict, Any


class PaymentGateway:
    def __init__(self, merchant_id: str):
        self.merchant_id = merchant_id
        self._processed_transactions: Dict[str, Dict[str, Any]] = {}

    def charge(self, amount_cents: int, currency: str, card_token: str) -> Dict[str, Any]:
        if amount_cents <= 0:
            raise ValueError("Amount must be greater than zero.")
        if not card_token or len(card_token) < 5:
            raise ValueError("Invalid card payment token.")

        transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
        record = {
            "transaction_id": transaction_id,
            "merchant_id": self.merchant_id,
            "amount_cents": amount_cents,
            "currency": currency.upper(),
            "status": "SUCCEEDED"
        }
        self._processed_transactions[transaction_id] = record
        return record
'''

    base_test = '''"""Unit tests for PaymentGateway."""
from gateway import PaymentGateway
import pytest


def test_successful_charge():
    gw = PaymentGateway(merchant_id="merch_100")
    res = gw.charge(amount_cents=4500, currency="USD", card_token="tok_visa_valid")
    assert res["status"] == "SUCCEEDED"
    assert res["amount_cents"] == 4500
    assert res["currency"] == "USD"


def test_invalid_amount_rejected():
    gw = PaymentGateway(merchant_id="merch_100")
    with pytest.raises(ValueError, match="greater than zero"):
        gw.charge(amount_cents=0, currency="USD", card_token="tok_visa_valid")
'''

    # Proposed code (Features added: Idempotency Key, Webhook HMAC Verification, Refund processing)
    proposed_models = '''"""E-Commerce Core Domain Models (Upgraded with Idempotency & Refunds)."""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class OrderItem:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass
class RefundRequest:
    refund_id: str
    original_transaction_id: str
    amount_cents: int
    reason: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CustomerOrder:
    order_id: str
    customer_id: str
    items: List[OrderItem]
    currency: str = "USD"
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_amount_cents(self) -> int:
        return sum(item.unit_price_cents * item.quantity for item in self.items)
'''

    proposed_gateway = '''"""Production Payment Gateway with Idempotency & Webhook HMAC Verification."""
import uuid
import hmac
import hashlib
from typing import Dict, Any, Optional


class PaymentGateway:
    def __init__(self, merchant_id: str, webhook_secret: Optional[str] = None):
        self.merchant_id = merchant_id
        self.webhook_secret = webhook_secret or "whsec_default_live_key"
        self._processed_transactions: Dict[str, Dict[str, Any]] = {}
        self._idempotency_cache: Dict[str, Dict[str, Any]] = {}

    def charge(
        self,
        amount_cents: int,
        currency: str,
        card_token: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes card charge with full idempotency deduplication."""
        if amount_cents <= 0:
            raise ValueError("Amount must be greater than zero.")
        if not card_token or len(card_token) < 5:
            raise ValueError("Invalid card payment token.")

        # Idempotency check: prevent duplicate charges on network retries
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]

        transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
        record = {
            "transaction_id": transaction_id,
            "merchant_id": self.merchant_id,
            "amount_cents": amount_cents,
            "currency": currency.upper(),
            "status": "SUCCEEDED",
            "idempotency_key": idempotency_key
        }

        self._processed_transactions[transaction_id] = record
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = record

        return record

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verifies webhook authenticity using constant-time HMAC-SHA256 comparison."""
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)
'''

    proposed_test = '''"""Comprehensive unit tests for upgraded PaymentGateway."""
from gateway import PaymentGateway
import pytest
import hmac
import hashlib


def test_successful_charge():
    gw = PaymentGateway(merchant_id="merch_100")
    res = gw.charge(amount_cents=4500, currency="USD", card_token="tok_visa_valid")
    assert res["status"] == "SUCCEEDED"
    assert res["amount_cents"] == 4500


def test_idempotency_protection():
    gw = PaymentGateway(merchant_id="merch_100")
    key = "idem_key_unique_99"
    res1 = gw.charge(amount_cents=5000, currency="EUR", card_token="tok_mastercard", idempotency_key=key)
    res2 = gw.charge(amount_cents=5000, currency="EUR", card_token="tok_mastercard", idempotency_key=key)

    # Identical transaction returned without duplicate processing
    assert res1["transaction_id"] == res2["transaction_id"]


def test_webhook_signature_verification():
    secret = "whsec_test_secret_key"
    gw = PaymentGateway(merchant_id="merch_100", webhook_secret=secret)
    body = b'{"event": "payment_intent.succeeded", "id": "pi_123"}'
    valid_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert gw.verify_webhook_signature(body, valid_sig) is True
    assert gw.verify_webhook_signature(body, "invalid_sig_abc123") is False
'''

    for path in [zip_path, fixture_path]:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("base/models.py", base_models)
            zf.writestr("base/gateway.py", base_gateway)
            zf.writestr("base/tests/test_payment.py", base_test)

            zf.writestr("proposed/models.py", proposed_models)
            zf.writestr("proposed/gateway.py", proposed_gateway)
            zf.writestr("proposed/tests/test_payment.py", proposed_test)
            zf.writestr("review-manifest.json", '{"project_name": "ECommerce_PaymentGateway", "primary_language": "python"}')

    print("Created:", zip_path)


def build_realworld_auth_service():
    """Generates RealWorld_UserAuth_SecurityDefect.zip - Auth service with Bandit & Secret defect."""
    zip_path = os.path.join(OUTPUT_DIR, "RealWorld_UserAuth_SecurityDefect.zip")
    fixture_path = os.path.join(FIXTURES_DIR, "realworld_auth_service.zip")

    base_auth = '''"""Enterprise User Authentication Service."""
import hashlib
import os
from typing import Dict, Optional


class AuthService:
    def __init__(self):
        self._user_db: Dict[str, Dict[str, str]] = {}

    def register(self, username: str, password_raw: str) -> bool:
        if username in self._user_db:
            return False
        salt = os.urandom(16).hex()
        pwd_hash = hashlib.sha256((salt + password_raw).encode("utf-8")).hexdigest()
        self._user_db[username] = {"salt": salt, "hash": pwd_hash}
        return True

    def authenticate(self, username: str, password_raw: str) -> bool:
        user = self._user_db.get(username)
        if not user:
            return False
        computed = hashlib.sha256((user["salt"] + password_raw).encode("utf-8")).hexdigest()
        return computed == user["hash"]
'''

    # Proposed code introduces a dangerous dynamic eval for deserializing custom user claims
    proposed_auth = '''"""Enterprise User Authentication Service (With Dangerous Dynamic Evaluation)."""
import hashlib
import os
from typing import Dict, Any, Optional


class AuthService:
    # Security Alert: Hardcoded credentials
    JWT_SECRET_KEY = "AKIAIOSFODNN7EXAMPLE_SECRET_PROD_KEY"

    def __init__(self):
        self._user_db: Dict[str, Dict[str, Any]] = {}

    def register(self, username: str, password_raw: str) -> bool:
        if username in self._user_db:
            return False
        salt = os.urandom(16).hex()
        pwd_hash = hashlib.sha256((salt + password_raw).encode("utf-8")).hexdigest()
        self._user_db[username] = {"salt": salt, "hash": pwd_hash}
        return True

    def parse_user_claims(self, raw_claims_payload: str) -> Dict[str, Any]:
        """Parses dynamic user session claims."""
        # Critical Security Flaw: Dangerous eval allows Remote Code Execution (RCE)
        claims = eval(raw_claims_payload)
        return claims

    def authenticate(self, username: str, password_raw: str) -> bool:
        user = self._user_db.get(username)
        if not user:
            return False
        computed = hashlib.sha256((user["salt"] + password_raw).encode("utf-8")).hexdigest()
        return computed == user["hash"]
'''

    test_file = '''"""Authentication Service Unit Tests."""
from auth import AuthService


def test_user_registration_and_login():
    svc = AuthService()
    assert svc.register("alice", "Password123!") is True
    assert svc.register("alice", "DuplicatePass") is False
    assert svc.authenticate("alice", "Password123!") is True
    assert svc.authenticate("alice", "WrongPass") is False
'''

    for path in [zip_path, fixture_path]:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("base/auth.py", base_auth)
            zf.writestr("base/tests/test_auth.py", test_file)

            zf.writestr("proposed/auth.py", proposed_auth)
            zf.writestr("proposed/tests/test_auth.py", test_file)
            zf.writestr("review-manifest.json", '{"project_name": "UserAuth_TokenService", "primary_language": "python"}')

    print("Created:", zip_path)


if __name__ == "__main__":
    build_realworld_payment_gateway()
    build_realworld_auth_service()
    print("All real-world sample ZIPs built successfully!")
