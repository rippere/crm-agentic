from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_key(request) -> str:  # type: ignore[no-untyped-def]
    """Use authenticated user_id when available, else fall back to client IP."""
    user = getattr(request.state, "user", None)
    if user is not None:
        return str(getattr(user, "id", get_remote_address(request)))
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_key)
