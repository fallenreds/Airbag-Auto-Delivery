from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import Client


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get('X-Api-Key')
        if not api_key:
            return None

        key = api_key

        try:
            client = Client.objects.get(api_key=key)
        except Client.DoesNotExist:
            raise AuthenticationFailed('Invalid API Key')

        return (client, None)
