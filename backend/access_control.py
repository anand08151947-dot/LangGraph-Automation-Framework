"""
access_control.py
Basic access control and authentication for API endpoints.
Supports API key, role-based access, and JWT/OAuth stubs.
"""


from fastapi import Request, HTTPException, status, Depends
from typing import List, Optional, Dict
import os
import secrets
import time
import threading
import jwt


class ConfigurationError(RuntimeError):
    """Raised when a required configuration value is missing at startup."""


def _load_jwt_secret(provided: Optional[str]) -> str:
    """Return the JWT secret, preferring the provided value then the env var.
    Raises ConfigurationError if neither is available."""
    secret = provided or os.getenv("JWT_SECRET")
    if not secret:
        raise ConfigurationError(
            "JWT_SECRET environment variable is not set. "
            "Set it to a strong random value before starting the API."
        )
    return secret


class AccessControl:
    def __init__(self, api_keys: Optional[List[str]] = None, jwt_secret: Optional[str] = None, user_roles: Optional[Dict[str, List[str]]] = None):
        self.api_keys = list(api_keys or [])
        self.jwt_secret = _load_jwt_secret(jwt_secret)
        self.user_roles = user_roles or {}  # {username: [roles]}
        # SEC-6: expiring keys during grace period after rotation
        self._expiring_keys: Dict[str, float] = {}
        self._key_lock = threading.Lock()

    def _cleanup_expired_keys(self):
        """Remove expired keys from api_keys and _expiring_keys."""
        now = time.time()
        with self._key_lock:
            expired = [k for k, exp in self._expiring_keys.items() if now > exp]
            for k in expired:
                del self._expiring_keys[k]
                if k in self.api_keys:
                    self.api_keys.remove(k)

    def rotate_api_key(self, old_key: str, grace_seconds: int = 300) -> str:
        """Generate a new API key, keeping old key valid during grace period."""
        new_key = secrets.token_urlsafe(32)
        with self._key_lock:
            self.api_keys.append(new_key)
            self._expiring_keys[old_key] = time.time() + grace_seconds
            if old_key not in self.api_keys:
                self.api_keys.append(old_key)
        return new_key

    def check_api_key(self, request: Request):
        self._cleanup_expired_keys()
        key = request.headers.get("x-api-key")
        if not key or key not in self.api_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key"
            )

    def check_jwt(self, request: Request):
        token = request.headers.get("authorization")
        if not token or not token.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid JWT")
        try:
            payload = jwt.decode(
                token[7:],
                self.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["exp"]},  # SEC-2: enforce expiration claim
            )
            request.state.user = payload.get("sub")
            request.state.roles = payload.get("roles", [])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Expired")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"JWT error: {e}")

    def has_role(self, user: str, role: str) -> bool:
        # Check user/role mapping or JWT roles
        if user in self.user_roles:
            return role in self.user_roles[user]
        return False

    def check_role(self, request: Request, role: str):
        user = getattr(request.state, "user", None)
        roles = getattr(request.state, "roles", [])
        if not user or (role not in roles and not self.has_role(user, role)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User {user} lacks required role: {role}"
            )

# Example usage in FastAPI endpoint:
# from fastapi import Depends, Request
# ac = AccessControl(["sk-...", "test-key"])
# @app.get("/secure-endpoint")
# def secure_endpoint(request: Request, _: None = Depends(ac.check_api_key)):
#     return {"status": "ok"}


# SEC-7: In-memory per-IP rate limiter
class RateLimiter:
    """Simple per-IP rate limiter with lockout support."""

    def __init__(self, max_attempts: int = 10, window_seconds: int = 60,
                 lockout_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._attempts: Dict[str, List[float]] = {}
        self._locked: Dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, ip: str):
        """Raise HTTP 429 if IP is locked out or over the attempt limit."""
        now = time.time()
        with self._lock:
            # Check lockout
            if ip in self._locked:
                if now < self._locked[ip]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Too many attempts. Locked out until {self._locked[ip]:.0f}."
                    )
                else:
                    del self._locked[ip]
                    self._attempts.pop(ip, None)
            # Clean old attempts outside the window
            if ip in self._attempts:
                self._attempts[ip] = [t for t in self._attempts[ip]
                                       if now - t < self.window_seconds]
            # Check rate limit
            attempts = self._attempts.get(ip, [])
            if len(attempts) >= self.max_attempts:
                self._locked[ip] = now + self.lockout_seconds
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )

    def record(self, ip: str):
        """Record an attempt for the given IP."""
        now = time.time()
        with self._lock:
            if ip not in self._attempts:
                self._attempts[ip] = []
            self._attempts[ip].append(now)
