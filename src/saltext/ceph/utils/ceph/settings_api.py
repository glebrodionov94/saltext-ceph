"""Salt-facing composition for Dashboard settings operations."""

from collections.abc import Mapping

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import settings
from saltext.ceph.utils.ceph.errors import ConfigurationError


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _secret(source):
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError("Secret file contains only line separators.")
    return value


def list_(opts, pillar, context, names=None, profile="default"):
    """List Dashboard settings with secret values redacted."""
    return settings.list_(_client(opts, pillar, context, profile), names).as_dict()


def get(opts, pillar, context, name, profile="default"):
    """Return one Dashboard setting with secret values redacted."""
    return settings.get(_client(opts, pillar, context, profile), name).as_dict()


def set_(
    opts,
    pillar,
    context,
    name,
    value=None,
    source=None,
    profile="default",
):
    """Set one option, requiring a local file for credential-like names."""
    secret = settings.is_secret(name)
    if secret:
        if source is None or value is not None:
            raise ConfigurationError("Secret settings require source and do not accept value.")
        value = _secret(source)
    elif source is not None or value is None:
        raise ConfigurationError("Non-secret settings require value and do not accept source.")
    return settings.set_(_client(opts, pillar, context, profile), name, value).as_dict()


def delete(opts, pillar, context, name, profile="default"):
    """Reset one Dashboard setting to its default."""
    return settings.delete(_client(opts, pillar, context, profile), name).as_dict()


def bulk_set(
    opts,
    pillar,
    context,
    values=None,
    secret_sources=None,
    profile="default",
):
    """Set multiple options, sourcing credential-like values from local files."""
    if values is None:
        values = {}
    if secret_sources is None:
        secret_sources = {}
    if not isinstance(values, Mapping) or not isinstance(secret_sources, Mapping):
        raise ConfigurationError("values and secret_sources must be mappings.")
    merged = {}
    for name, value in values.items():
        native = settings.normalize_name(name)
        if settings.is_secret(native):
            raise ConfigurationError("Secret setting names belong in secret_sources.")
        if native in merged:
            raise ConfigurationError("Duplicate setting name.")
        merged.update(settings.normalize_values({native: value}))
    for name, source in secret_sources.items():
        native = settings.normalize_name(name)
        if not settings.is_secret(native):
            raise ConfigurationError("Non-secret setting names belong in values.")
        if native in merged:
            raise ConfigurationError("Duplicate setting name.")
        merged[native] = _secret(source)
    if not merged:
        raise ConfigurationError("At least one setting is required.")
    return settings.bulk_set(_client(opts, pillar, context, profile), merged).as_dict()
