"""Request serializers for the session endpoints.

Only the login body needs one. Every field is write-only, so no value that
arrives here can be echoed back in a response or in a validation error.
"""

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    """The login request body: exactly a username and a password.

    Whitespace is preserved on both fields because a credential may
    legitimately contain it, and the username length matches the user model
    so an impossible name is refused before the database is touched. The view
    turns any validation failure into the one generic login failure, so the
    per-field errors this serializer produces never reach a caller.
    """

    username = serializers.CharField(
        max_length=150,
        trim_whitespace=False,
        write_only=True,
    )
    password = serializers.CharField(trim_whitespace=False, write_only=True)
