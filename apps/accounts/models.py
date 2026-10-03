from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """The app owner. There is no public signup; accounts are created by command."""

    is_demo = models.BooleanField(
        default=False, help_text="Disposable demonstration account populated by the seed command."
    )
