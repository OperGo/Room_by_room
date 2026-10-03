from django.core.files.storage import FileSystemStorage, storages


class PrivateFileSystemStorage(FileSystemStorage):
    """Local storage for private files. It has no public base URL on purpose.

    Files are only reachable through owner-checked download views. A private
    object-storage backend can replace this later via ``STORAGES['private']``.
    """

    def __init__(self, **kwargs):
        kwargs["base_url"] = None
        kwargs.setdefault("file_permissions_mode", 0o600)
        kwargs.setdefault("directory_permissions_mode", 0o700)
        super().__init__(**kwargs)

    def url(self, name):  # pragma: no cover - guard against accidental use
        raise NotImplementedError("Private files have no public URL; use the owner-checked download view.")


def private_storage():
    return storages["private"]
