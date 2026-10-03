import io

from django.core.files import File
from django.core.files.storage import FileSystemStorage, Storage, storages
from django.utils.deconstruct import deconstructible


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


@deconstructible
class DatabaseStorage(Storage):
    """Private storage backed by the ``StoredFile`` table. No public URLs."""

    def _model(self):
        from apps.core.models import StoredFile

        return StoredFile

    def _open(self, name, mode="rb"):
        row = self._model().objects.filter(name=name).only("content").first()
        if row is None:
            raise FileNotFoundError(name)
        return File(io.BytesIO(bytes(row.content)), name=name)

    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        if isinstance(data, str):
            data = data.encode()
        self._model().objects.create(name=name, content=data, size=len(data))
        return name

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        row = self._model().objects.filter(name=name).only("size").first()
        if row is None:
            raise FileNotFoundError(name)
        return row.size

    def listdir(self, path):
        prefix = path.rstrip("/") + "/" if path else ""
        names = self._model().objects.filter(name__startswith=prefix).values_list("name", flat=True)
        dirs, files = set(), []
        for name in names:
            rest = name[len(prefix):]
            if "/" in rest:
                dirs.add(rest.split("/", 1)[0])
            else:
                files.append(rest)
        return sorted(dirs), sorted(files)

    def url(self, name):  # pragma: no cover - guard against accidental use
        raise NotImplementedError("Private files have no public URL; use the owner-checked download view.")


def private_storage():
    return storages["private"]
