import math

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

_REDACTED = '[REDACTED]'
_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        'password',
        'passwordconfirmation',
        'currentpassword',
        'oldpassword',
        'newpassword',
        'passphrase',
        'secret',
        'clientsecret',
        'secretkey',
        'privatekey',
        'token',
        'accesstoken',
        'refreshtoken',
        'idtoken',
        'apitoken',
        'apikey',
        'authorization',
        'cookie',
        'cookies',
        'sessionid',
        'sessionkey',
        'csrfmiddlewaretoken',
        'pin',
        'parentpin',
        'pinhash',
        'credential',
        'credentials',
    }
)
_INVALID_CONTEXT = 'Context must be a JSON object containing only valid JSON values.'


class AuditEventImmutableError(RuntimeError):
    pass


def _normalise_context_key(key):
    return ''.join(character for character in key.casefold() if character.isalnum())


def _copy_and_sanitise_context(value, *, top_level=True, active_containers=None):
    if active_containers is None:
        active_containers = set()

    if top_level and type(value) is not dict:
        raise ValidationError({'context': _INVALID_CONTEXT})

    if type(value) is dict:
        container_id = id(value)
        if container_id in active_containers:
            raise ValidationError({'context': _INVALID_CONTEXT})
        active_containers.add(container_id)
        try:
            copied = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValidationError({'context': _INVALID_CONTEXT})
                if _normalise_context_key(key) in _SENSITIVE_CONTEXT_KEYS:
                    copied[key] = _REDACTED
                else:
                    copied[key] = _copy_and_sanitise_context(
                        item,
                        top_level=False,
                        active_containers=active_containers,
                    )
            return copied
        finally:
            active_containers.remove(container_id)

    if type(value) is list:
        container_id = id(value)
        if container_id in active_containers:
            raise ValidationError({'context': _INVALID_CONTEXT})
        active_containers.add(container_id)
        try:
            return [
                _copy_and_sanitise_context(
                    item,
                    top_level=False,
                    active_containers=active_containers,
                )
                for item in value
            ]
        finally:
            active_containers.remove(container_id)

    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValidationError({'context': _INVALID_CONTEXT})


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditEventImmutableError('Audit events cannot be updated.')

    def delete(self):
        raise AuditEventImmutableError('Audit events cannot be deleted.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditEventImmutableError('Audit events cannot be updated.')

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        raise AuditEventImmutableError('Audit events cannot be created in bulk.')


AuditEventManager = models.Manager.from_queryset(AuditEventQuerySet)


class AuditEvent(models.Model):
    household = models.ForeignKey(
        'identity.Household',
        on_delete=models.PROTECT,
        related_name='audit_events',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='audit_events',
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    context = models.JSONField(default=dict, blank=True)

    objects = AuditEventManager()

    class Meta:
        ordering = ('-created_at', '-id')
        indexes = [  # noqa: RUF012
            models.Index(
                fields=('household', '-created_at', '-id'),
                name='audit_event_hh_time_id_idx',
            )
        ]

    def clean(self):
        super().clean()
        self.context = _copy_and_sanitise_context(self.context)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditEventImmutableError('Audit events cannot be updated.')
        self.context = _copy_and_sanitise_context(self.context)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditEventImmutableError('Audit events cannot be deleted.')
