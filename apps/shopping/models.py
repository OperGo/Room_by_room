import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ShoppingItemQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)


class ShoppingItem(models.Model):
    """Something to buy. Marking it bought never creates spending by itself."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_items")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_items",
        help_text="Leave empty for shared items used across projects.",
    )
    task = models.ForeignKey("projects.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_items")
    description = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit = models.CharField(max_length=30, blank=True)
    retailer = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    purchased_at = models.DateTimeField(null=True, blank=True)
    purchase_line = models.ForeignKey(
        "costs.PurchaseLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_items"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    objects = ShoppingItemQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="shopping_quantity_positive"),
        ]

    def __str__(self):
        return self.description

    @property
    def is_bought(self):
        return self.purchased_at is not None
