"""Translate transport exceptions into stable Salt exception types."""

from salt.exceptions import CommandExecutionError
from salt.exceptions import SaltInvocationError

from saltext.ceph.utils.ceph.errors import APIError
from saltext.ceph.utils.ceph.errors import CephError
from saltext.ceph.utils.ceph.errors import ConfigurationError


def invoke(function, *args, **kwargs):
    """Call a utility function and expose safe, structured errors to Salt."""
    try:
        return function(*args, **kwargs)
    except ConfigurationError as exc:
        raise SaltInvocationError(str(exc)) from None
    except APIError as exc:
        raise CommandExecutionError(str(exc), info={"status": exc.status}) from None
    except CephError as exc:
        raise CommandExecutionError(str(exc)) from None
