import os

import pytest

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def _private_storage(settings, tmp_path):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.STORAGES = {**settings.STORAGES, "private": {
        "BACKEND": "apps.core.storage.PrivateFileSystemStorage", "OPTIONS": {"location": tmp_path / "private"}}}


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="correct-horse-battery")


def sign_in(page, live_server):
    page.goto(f"{live_server.url}/account/sign-in/")
    page.fill("#id_username", "owner")
    page.fill("#id_password", "correct-horse-battery")
    page.click("button[type=submit]")
    page.wait_for_url(f"{live_server.url}/")
