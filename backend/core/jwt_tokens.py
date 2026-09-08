import hashlib

from rest_framework_simplejwt.tokens import RefreshToken

# Имя клейма с отпечатком пароля.
PASSWORD_CLAIM = "pwd"


def password_fingerprint(user):
    """
    Короткий отпечаток текущего хеша пароля.

    Кладётся в токен, чтобы после смены пароля (в том числе через сброс)
    ранее выданные access/refresh переставали работать. simplejwt без
    приложения token_blacklist отзывать токены не умеет, а blacklist потребовал
    бы записи в БД на каждую выдачу токена — здесь это не нужно.

    В токен уходит хеш от хеша, причём усечённый: восстановить из него пароль
    нельзя, а для сравнения «тот же/не тот» этого достаточно.
    """
    raw = user.password or ""
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def issue_tokens(user):
    """
    Единственная точка выдачи токенов, кроме входа по паролю.

    Клейм с отпечатком пароля кладётся всегда — `PasswordAwareJWTAuthentication`
    без него токен не примет. Раньше вход через Telegram выдавал токены без
    клейма (а гостям — ещё и вечные), и аутентификация держала для них
    исключение. Исключения больше нет.
    """
    refresh = RefreshToken.for_user(user)
    refresh[PASSWORD_CLAIM] = password_fingerprint(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}
