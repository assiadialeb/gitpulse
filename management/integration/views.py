import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from users.decorators import user_passes_test
from users.views import is_admin
from .models import OSSIndexConfig

logger = logging.getLogger(__name__)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
@csrf_exempt
def save_ossindex_config(request):
    """Save OSS Index configuration"""
    try:
        data = json.loads(request.body)
        api_token = data.get('api_token', '').strip()
        
        if not api_token:
            return JsonResponse({
                'success': False,
                'message': 'API token is required'
            })
        
        # Get or create configuration
        config = OSSIndexConfig.get_config()
        config.api_token = api_token
        config.save()
        
        logger.info("OSS Index configuration saved successfully")
        
        return JsonResponse({
            'success': True,
            'message': 'OSS Index configuration saved successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        })
    except Exception as e:
        logger.error(f"Error saving OSS Index configuration: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error saving configuration: {str(e)}'
        })


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
@csrf_exempt
def test_ossindex_connection(request):
    """Test OSS Index API connection"""
    try:
        config = OSSIndexConfig.get_config()
        
        if not config.api_token:
            return JsonResponse({
                'success': False,
                'message': 'OSS Index API token not configured'
            })
        
        # For now, just verify the token is set
        # In the future, we could make an actual API call to test the connection
        if config.api_token:
            return JsonResponse({
                'success': True,
                'message': 'OSS Index API token is configured'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'OSS Index API token is not configured'
            })
            
    except Exception as e:
        logger.error(f"Error testing OSS Index connection: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error testing connection: {str(e)}'
        }) 