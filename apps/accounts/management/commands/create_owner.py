import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the real (empty) owner account. There is no public signup."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", default="")

    def handle(self, username, email, **options):
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User {username!r} already exists.")
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("Passwords did not match.")
        user = User(username=username, email=email)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Created owner account {username!r} with no data."))
