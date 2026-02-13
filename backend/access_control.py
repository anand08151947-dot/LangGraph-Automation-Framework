"""
access_control.py
Basic access control and authentication for API endpoints.
Supports API key, role-based access, and JWT/OAuth stubs.
"""


from fastapi import Request, HTTPException, status, Depends
from typing import List, Optional, Dict
import os
import jwt


class AccessControl:
    def __init__(self, api_keys: Optional[List[str]] = None, jwt_secret: Optional[str] = None, user_roles: Optional[Dict[str, List[str]]] = None):
        self.api_keys = api_keys or []
        self.jwt_secret = jwt_secret or os.getenv("JWT_SECRET", "secret")
        self.user_roles = user_roles or {}  # {username: [roles]}

    def check_api_key(self, request: Request):
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
            payload = jwt.decode(token[7:], self.jwt_secret, algorithms=["HS256"])
            request.state.user = payload.get("sub")
            request.state.roles = payload.get("roles", [])
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
