import sys
import os

# Ensure backend/ directory is available for imports like `import template_manager`
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# SEC-1: Provide a test-only JWT secret so AccessControl doesn't raise ConfigurationError
# during test collection. This value is only used in the test environment.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-do-not-use-in-production")
