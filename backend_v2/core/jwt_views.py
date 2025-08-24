from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.models import Client
from core.jwt_tokens import GuestRefreshToken
from .jwt_serializers import MyTokenObtainPairSerializer


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view that handles both regular and guest tokens.
    For guest clients, it uses GuestRefreshToken which never expires.
    For regular clients, it uses the standard RefreshToken with normal expiration.
    """
    
    def post(self, request, *args, **kwargs):
        serializer = TokenRefreshSerializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            # Check if this might be a guest token that's being rejected due to expiration
            refresh_token = request.data.get('refresh', '')
            
            try:
                # Try to decode the token to get the user_id
                from rest_framework_simplejwt.tokens import TokenBackend
                token_backend = TokenBackend(algorithm='HS256')
                decoded_token = token_backend.decode(refresh_token, verify=False)
                
                user_id = decoded_token.get('user_id')
                if user_id:
                    # Check if this is a guest user
                    try:
                        user = Client.objects.get(id=user_id)
                        if user.is_guest:
                            # For guest users, generate a new non-expiring token
                            refresh = GuestRefreshToken.for_user(user)
                            return Response({
                                'refresh': str(refresh),
                                'access': str(refresh.access_token),
                            })
                    except Client.DoesNotExist:
                        pass
            except Exception:
                # If any error occurs during this process, fall back to the original error
                pass
                
            raise InvalidToken(e.args[0])
            
        return Response(serializer.validated_data, status=status.HTTP_200_OK)
