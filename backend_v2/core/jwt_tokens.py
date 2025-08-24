from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken


class GuestRefreshToken(RefreshToken):
    """
    Custom refresh token for guest clients that never expires.
    """
    
    @property
    def lifetime(self):
        """
        Return a very large lifetime for guest tokens (100 years).
        This effectively makes the token never expire.
        """
        return timedelta(days=36500)  # ~100 years
    
    @classmethod
    def for_user(cls, user):
        """
        Create a refresh token for the given user.
        If the user is a guest, return a GuestRefreshToken.
        Otherwise, return a standard RefreshToken.
        """
        if user.is_guest:
            # For guest users, use the non-expiring token
            token = cls()
            token["user_id"] = user.id
            
            # Add custom claims
            token["is_guest"] = True
            
            return token
        else:
            # For regular users, use the standard token with normal expiration
            return RefreshToken.for_user(user)
