from django.db import models


class TenantQuerySet(models.QuerySet):
    """Queryset for models that belong to a society (they have a `society` foreign key).

    Views and services read tenant data ONLY through for_society(). Never use .all() or
    .filter() on a tenant-owned model directly: that is how cross-tenant leaks happen.
    """

    def for_society(self, society):
        return self.filter(society=society)
