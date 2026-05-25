from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class UsernameOrEmailBackend(ModelBackend):
    """
    Authentication backend that allows users to log in using either their
    username (USER_NAME_FIELD) or their email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        # Try to find by username (case-insensitive)
        user = None
        try:
            user = UserModel.objects.filter(**{f"{UserModel.USERNAME_FIELD}__iexact": username}).first()
        except Exception:
            user = None
        # If not found and input looks like an email, try email lookup
        if user is None and "@" in username:
            try:
                user = UserModel.objects.filter(email__iexact=username).first()
            except Exception:
                user = None
        # As a final fallback, also try email lookup (in case usernames don't contain '@')
        if user is None:
            try:
                user = UserModel.objects.filter(email__iexact=username).first()
            except Exception:
                user = None
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
