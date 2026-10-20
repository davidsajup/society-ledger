from django.db import connection

from .models import AuditLog


def record(*, society, action, object_type, object_id, actor=None, flat=None, amount=None,
           data=None):
    """Write one audit row. MUST be called inside the transaction of the action it describes.

    That is the whole point: the audit row and the money change commit together or roll back
    together. Written outside a transaction, a crash between the two writes would leave a
    payment with no audit trail (or an audit trail for a payment that never happened), so this
    refuses to run unless a transaction is open.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("audit.record() must be called inside transaction.atomic().")
    return AuditLog.objects.create(
        society=society,
        actor=actor,
        action=action,
        flat=flat,
        object_type=object_type,
        object_id=object_id,
        amount=amount,
        data=data or {},
    )
