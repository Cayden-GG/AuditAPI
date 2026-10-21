import sys
from types import SimpleNamespace

import pytest
from google.cloud import storage

from app.gcs.uploader import download_objects, upload_files


class RecordingLogger:
    def __init__(self):
        self.entries = []

    def _record(self, level, message, **context):
        self.entries.append((level, message, context))

    def info(self, message, **context):
        self._record("info", message, **context)

    def warning(self, message, **context):
        self._record("warning", message, **context)

    def exception(self, message, exc, **context):
        self._record("exception", message, **context)

    def messages(self, level):
        return [m for lvl, m, _ in self.entries if lvl == level]


class FakeBlob:
    def __init__(self, name, state):
        self.name = name
        self.state = state

    def upload_from_filename(self, path):
        if self.name in self.state.failing:
            raise RuntimeError("upload failed")
        self.state.uploaded.append((self.name, path))

    def download_to_filename(self, path):
        if self.name in self.state.failing:
            raise RuntimeError("download failed")
        with open(path, "wb") as handle:
            handle.write(f"contents of {self.name}".encode())
        self.state.downloaded.append((self.name, path))


class FakeBucket:
    def __init__(self, name, state):
        self.name = name
        self.state = state

    def blob(self, name):
        return FakeBlob(name, self.state)


@pytest.fixture
def gcs(monkeypatch, tmp_path):
    """Replaces the google storage client. Object names in .failing raise when uploaded or downloaded"""
    state = SimpleNamespace(
        uploaded=[], downloaded=[], failing=set(), credentials=[], buckets=[], client_error=None,
        creds=tmp_path / "creds.json", logger=RecordingLogger(),
    )
    state.creds.write_text("{}")

    class FakeClient:
        @classmethod
        def from_service_account_json(cls, path):
            if state.client_error:
                raise state.client_error
            state.credentials.append(path)
            return cls()

        def bucket(self, name):
            state.buckets.append(name)
            return FakeBucket(name, state)

    monkeypatch.setattr(storage, "Client", FakeClient)
    return state


def upload(gcs, files, prefix="audits/one", bucket="bucket", credentials=None):
    return upload_files(
        file_paths=files,
        bucket_name=bucket,
        prefix=prefix,
        credentials_path=str(gcs.creds) if credentials is None else credentials,
        logger=gcs.logger,
    )


def download(gcs, names, output_dir, bucket="bucket", credentials=None):
    return download_objects(
        object_names=names,
        bucket_name=bucket,
        credentials_path=str(gcs.creds) if credentials is None else credentials,
        output_dir=output_dir,
        logger=gcs.logger,
    )


@pytest.fixture
def files(tmp_path):
    paths = []
    for name in ("a.pdf", "b.pdf"):
        path = tmp_path / name
        path.write_bytes(b"data")
        paths.append(path)
    return paths


# upload_files

def test_upload_files_puts_files_under_the_prefix(gcs, files):
    result = upload(gcs, files)

    assert result == {str(files[0]): "audits/one/a.pdf", str(files[1]): "audits/one/b.pdf"}
    assert [name for name, _ in gcs.uploaded] == ["audits/one/a.pdf", "audits/one/b.pdf"]
    assert gcs.credentials == [str(gcs.creds)]
    assert gcs.buckets == ["bucket"]


@pytest.mark.parametrize("prefix, expected", [("/audits/one/", "audits/one/a.pdf"), ("  ", "a.pdf"), ("", "a.pdf")])
def test_upload_files_cleans_the_prefix(gcs, files, prefix, expected):
    assert upload(gcs, files[:1], prefix=prefix) == {str(files[0]): expected}


def test_upload_files_skips_missing_files(gcs, files, tmp_path):
    result = upload(gcs, [tmp_path / "missing.pdf", files[0]])

    assert list(result) == [str(files[0])]
    assert "GCS upload skipped; file not found." in gcs.logger.messages("warning")


def test_upload_files_keeps_going_after_one_upload_fails(gcs, files):
    gcs.failing.add("audits/one/a.pdf")

    result = upload(gcs, files)

    assert result == {str(files[1]): "audits/one/b.pdf"}
    assert gcs.logger.messages("exception") == ["GCS upload failed."]


@pytest.mark.parametrize(
    "kwargs",
    [{"credentials": ""}, {"bucket": ""}, {"credentials": "/does/not/exist.json"}],
    ids=["no-credentials", "no-bucket", "credentials-file-missing"],
)
def test_upload_files_does_nothing_without_credentials_or_bucket(gcs, files, kwargs):
    assert upload(gcs, files, **kwargs) == {}
    assert gcs.uploaded == []
    assert gcs.logger.messages("warning")


def test_upload_files_returns_nothing_when_the_client_cannot_start(gcs, files):
    gcs.client_error = ValueError("bad credentials")

    assert upload(gcs, files) == {}
    assert gcs.logger.messages("exception") == ["Failed to initialize GCS client."]


def test_upload_files_returns_nothing_when_the_gcs_library_is_missing(gcs, files, monkeypatch):
    import google.cloud

    monkeypatch.delattr(google.cloud, "storage")
    monkeypatch.setitem(sys.modules, "google.cloud.storage", None)

    assert upload(gcs, files) == {}
    assert gcs.logger.messages("exception") == ["GCS client import failed."]


# download_objects

def test_download_objects_saves_files_into_the_output_dir(gcs, tmp_path):
    out = tmp_path / "out" / "nested"

    result = download(gcs, ["audits/one/a.pdf", "audits/one/b.pdf"], out)

    assert result == {"audits/one/a.pdf": str(out / "a.pdf"), "audits/one/b.pdf": str(out / "b.pdf")}
    assert (out / "a.pdf").read_text() == "contents of audits/one/a.pdf"


def test_download_objects_skips_empty_names(gcs, tmp_path):
    result = download(gcs, ["", None, "audits/one/a.pdf"], tmp_path / "out")

    assert list(result) == ["audits/one/a.pdf"]


def test_download_objects_keeps_going_after_one_download_fails(gcs, tmp_path):
    gcs.failing.add("audits/one/a.pdf")

    result = download(gcs, ["audits/one/a.pdf", "audits/one/b.pdf"], tmp_path / "out")

    assert list(result) == ["audits/one/b.pdf"]
    assert gcs.logger.messages("exception") == ["GCS download failed."]


@pytest.mark.parametrize(
    "kwargs",
    [{"credentials": ""}, {"bucket": ""}, {"credentials": "/does/not/exist.json"}],
    ids=["no-credentials", "no-bucket", "credentials-file-missing"],
)
def test_download_objects_does_nothing_without_credentials_or_bucket(gcs, tmp_path, kwargs):
    assert download(gcs, ["audits/one/a.pdf"], tmp_path / "out", **kwargs) == {}
    assert gcs.downloaded == []
    assert not (tmp_path / "out").exists()


def test_download_objects_returns_nothing_when_the_client_cannot_start(gcs, tmp_path):
    gcs.client_error = ValueError("bad credentials")

    assert download(gcs, ["audits/one/a.pdf"], tmp_path / "out") == {}
