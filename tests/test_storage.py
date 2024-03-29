import os
import gcsfs
from uuid import uuid4
from gcp_tools import Storage


# Utilities which do not depend on Storage class
def create_bucket(bucket_name):
    fs = gcsfs.GCSFileSystem()
    fs.mkdir(f"gs://{bucket_name}", location="europe-west2")


def list_buckets():
    fs = gcsfs.GCSFileSystem()
    fs.invalidate_cache()
    return fs.ls("gs://")


def list_files(bucket_name):
    fs = gcsfs.GCSFileSystem()
    fs.invalidate_cache()
    return fs.ls(f"gs://{bucket_name}")


def create_file(bucket_name, file_name):
    fs = gcsfs.GCSFileSystem()
    fs.invalidate_cache()
    fs.touch(f"gs://{bucket_name}/{file_name}", location="europe-west2")


# Tests for the Storage class
def test_storage_init():
    assert Storage("bucket_name").bucket_name == "bucket_name"
    assert Storage("gs://bucket_name").bucket_name == "bucket_name"
    assert Storage("bucket_name/file").bucket_name == "bucket_name"
    assert Storage("gs://bucket_name/file").bucket_name == "bucket_name"
    assert Storage("gs://bucket_name").path == "gs://bucket_name"
    assert Storage("bucket_name").path == "gs://bucket_name"
    assert Storage("bucket_name/file").path == "gs://bucket_name/file"
    assert Storage("gs://bucket_name/file").path == "gs://bucket_name/file"
    assert Storage(bucket_name="bucket").bucket_name == "bucket"
    assert Storage(bucket_name="bucket").path == "gs://bucket"
    assert Storage().path == "gs://"
    assert Storage().bucket_name is None
    assert Storage("path").fs_prefix == "gs://"
    assert Storage("gs://").ref_type == "project"
    assert Storage("gs://bucket").ref_type == "bucket"
    assert Storage("gs://bucket/file").ref_type == "file"
    assert Storage("gs://bucket").is_bucket
    assert Storage("gs://bucket/file").is_file
    assert Storage("gs://").is_project
    assert Storage("gs://bucket/filepath").base_path == "bucket/filepath"
    assert Storage("gs://bucket/filepath").file_name == "filepath"


def test_storage_ls_glob():
    success = {}
    # Test bucket ls
    bucket_name = f"test_bucket_{uuid4()}"
    create_bucket(bucket_name)
    success[0] = bucket_name + "/" in Storage().ls()
    # Test file ls
    file_name = f"test_file_{uuid4()}"
    create_file(bucket_name, file_name)
    success[1] = f"{bucket_name}/{file_name}" in Storage(bucket_name).ls()
    # Test file ls with path
    success[2] = f"{bucket_name}/{file_name}" in Storage(f"gs://{bucket_name}").ls()

    # Test bucket glob
    success[3] = bucket_name + "/" in Storage().glob()

    # Test file glob
    glob_query = f"{bucket_name}/*"
    success[4] = f"{bucket_name}/{file_name}" in Storage(glob_query).glob()
    success[5] = f"{bucket_name}/{file_name}" in Storage().glob(glob_query)

    # Test subdirectory file glob
    subdirectory = f"subdirectory"
    file_path = f"{bucket_name}/{subdirectory}/{file_name}"
    create_file(bucket_name, f"{subdirectory}/{file_name}")
    glob_query = f"{bucket_name}/*/*"
    print(Storage(glob_query).glob())
    success[6] = file_path in Storage(glob_query).glob()

    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_mkdir():
    success = {}
    # Test bucket mkdir
    bucket_name = f"test_bucket_{uuid4()}"
    Storage(bucket_name).mkdir()
    success[0] = bucket_name + "/" in list_buckets()

    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_create_bucket():
    success = {}
    # Test bucket create
    bucket_name = f"test_bucket_{uuid4()}"
    Storage(bucket_name).create_bucket()
    success[0] = bucket_name + "/" in list_buckets()

    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_create():
    success = {}
    # Test bucket create
    bucket_name = f"test_bucket_{uuid4()}"
    Storage(bucket_name).create()
    success[0] = bucket_name + "/" in list_buckets()

    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_delete():
    success = {}
    # Test bucket delete
    bucket_name = f"test_bucket_{uuid4()}"
    create_bucket(bucket_name)
    success[0] = bucket_name + "/" in list_buckets()
    Storage(bucket_name).delete()
    success[1] = bucket_name + "/" not in list_buckets()

    # Test file delete
    bucket_name = f"test_bucket_{uuid4()}"
    create_bucket(bucket_name)
    file_name = f"test_file_{uuid4()}"
    create_file(bucket_name, file_name)
    print(bucket_name)
    print(list_files(bucket_name))
    success[2] = f"{bucket_name}/{file_name}" in list_files(bucket_name)
    Storage(f"{bucket_name}/{file_name}").delete()
    success[3] = f"{bucket_name}/{file_name}" not in list_files(bucket_name)

    # Test bucket delete with files
    bucket_name = f"test_bucket_{uuid4()}"
    create_bucket(bucket_name)
    file_name = f"test_file_{uuid4()}"
    create_file(bucket_name, file_name)
    success[4] = f"{bucket_name}/{file_name}" in list_files(bucket_name)
    Storage(bucket_name).delete()
    success[5] = bucket_name + "/" not in list_buckets()

    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_upload_download():
    success = {}
    # Test file upload
    bucket_name = f"test_bucket_{uuid4()}"
    create_bucket(bucket_name)
    file_name = f"tests/test_storage.py"
    Storage(f"{bucket_name}/{file_name}").upload(file_name)
    success[0] = f"{bucket_name}/{file_name}" in list_files(bucket_name + "/tests")

    # Test file download
    download_path = f"tests_output/test_storage_download.py"
    Storage(f"{bucket_name}/{file_name}").download(download_path)
    success[1] = os.path.exists(download_path)
    success[2] = os.path.getsize(download_path) == os.path.getsize(file_name)

    Storage(bucket_name).delete()

    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_copy_move():
    success = {}
    # Test file copy
    start_bucket = f"test_bucket_{uuid4()}"
    end_bucket = f"test_bucket_{uuid4()}"
    print(start_bucket)
    print(end_bucket)
    create_bucket(start_bucket)
    create_bucket(end_bucket)
    file_name = f"test_file_{uuid4()}"
    create_file(start_bucket, file_name)

    # Test copy
    Storage(f"{start_bucket}/{file_name}").copy(f"{end_bucket}/{file_name}_copy")
    success[0] = f"{end_bucket}/{file_name}_copy" in list_files(end_bucket)
    success[1] = f"{start_bucket}/{file_name}" in list_files(start_bucket)

    # Test move
    Storage(f"{start_bucket}/{file_name}").move(f"{end_bucket}/{file_name}_move")
    success[2] = f"{end_bucket}/{file_name}_move" in list_files(end_bucket)
    success[3] = f"{start_bucket}/{file_name}" not in list_files(start_bucket)

    failed = [k for k, v in success.items() if not v]

    Storage(start_bucket).delete()
    Storage(end_bucket).delete()
    assert not failed


def test_open():
    success = {}
    # Test file open
    bucket_name = f"test_bucket_{uuid4()}"
    create_bucket(bucket_name)
    file_name = f"test_file_{uuid4()}"
    create_file(bucket_name, file_name)

    with Storage(f"{bucket_name}/{file_name}").open() as f:
        success[0] = f.read() == ""

    failed = [k for k, v in success.items() if not v]

    Storage(bucket_name).delete()
    assert not failed


def test_exists():
    success = {}
    # Test file exists
    bucket_name = f"test_bucket_{uuid4()}"

    success[0] = not Storage(bucket_name).exists()
    create_bucket(bucket_name)
    success[1] = Storage(bucket_name).exists()

    file_name = f"test_file_{uuid4()}"

    success[2] = not Storage(f"{bucket_name}/{file_name}").exists()
    success[3] = not Storage(f"{bucket_name}").exists(file_name)
    create_file(bucket_name, file_name)
    success[4] = Storage(f"{bucket_name}/{file_name}").exists()
    success[5] = Storage(f"{bucket_name}").exists(file_name)

    success[6] = not Storage(f"{bucket_name}/{file_name}_not_exists").exists()
    success[7] = not Storage(f"{bucket_name}").exists(f"{file_name}_not_exists")

    failed = [k for k, v in success.items() if not v]

    Storage(bucket_name).delete()
    assert not failed


def test_suffix_path():
    success = {}
    success[0] = Storage()._suffix_path("file") == "gs://file"
    success[1] = Storage("bucket_name")._suffix_path("file") == "gs://bucket_name/file"
    success[2] = Storage("bucket_name/path")._suffix_path() == "gs://bucket_name/path"

    failed = [k for k, v in success.items() if not v]

    assert not failed
