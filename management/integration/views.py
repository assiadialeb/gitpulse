import json
import logging
import uuid
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from users.decorators import user_passes_test
from users.views import is_admin

logger = logging.getLogger(__name__)


def _error_response(user_message: str, exc: Exception = None, status: int = 500):
    """Return a safe JSON error with a correlation id; log full details server-side."""
    error_id = str(uuid.uuid4())
    if exc is not None:
        logger.exception(f"{user_message} [error_id={error_id}]")
    else:
        logger.error(f"{user_message} [error_id={error_id}]")
    return JsonResponse({
        'success': False,
        'message': user_message,
        'error_id': error_id
    }, status=status)

// OSS Index integration removed


// OSS Index integration removed