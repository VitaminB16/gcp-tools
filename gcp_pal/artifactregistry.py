import os
from gcp_pal.utils import ModuleHandler, ClientHandler, log, get_auth_default


class ArtifactRegistry:
    def __init__(
        self,
        path: str = "",
        project: str = None,
        location: str = "europe-west2",
        repository: str = None,
        image: str = None,
        version: str = None,
        tag: str = None,
    ):
        """
        Initialize an ArtifactRegistry object.

        Args:
        - path (str): The path to the resource. This follows the hierarchy `repository/image/tag`.
                      If a full path is given (starting with `'projects/'`), the `project`, `location`, `repository`,
                      `image`, and `tag` will be extracted from the path.
                      The path can be either one of the forms:
            - `projects/PROJECT/locations/LOCATION/repositories/REPOSITORY/packages/IMAGE/versions/sha256:VERSION`
            - `REPOSITORY/IMAGE/VERSION`
            - `REPOSITORY/IMAGE:TAG`
        - project (str): The GCP project ID. Defaults to the `PROJECT` environment variable or the default auth project.
        - location (str): The location of the Artifact Registry. Defaults to `'europe-west2'`.
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - version (str): The version of the image (SHA256 hash).
        - tag (str): The tag of the image (e.g. `'latest'`). If a tag is provided, the `version` will be ignored.
        """
        if isinstance(path, str) and path.startswith("projects/"):
            path = path.split("/")
            path = "/".join(path[1::2])
            path = path.replace("%2F", "/")
            # Extract project and location from path and leave path to be repository/image/package
            try:
                project = path.split("/")[0]
            except IndexError:
                pass
            try:
                location = path.split("/")[1]
            except IndexError:
                # If path is provided as 'projects/project', assume location is intentionally left out
                location = None
            try:
                path = "/".join(path.split("/")[2:])
            except IndexError:
                pass
        self.project = project or os.environ.get("PROJECT") or get_auth_default()[1]
        self.location = location
        self.repository = repository
        self.image = image
        self.tag = tag
        self.version = version
        try:
            self.repository = path.split("/")[0]
        except IndexError:
            pass
        try:
            self.image = path.split("/")[1:]
            if len(self.image) > 1:
                self.image = "/".join(self.image[:-1])
            elif self.image == []:
                self.image = None
            else:
                self.image = self.image[0]
        except IndexError:
            pass
        try:
            self.version = path.split("sha256:")[1]
        except IndexError:
            pass
        try:
            self.tag = self.image.split(":")[1]
            self.image = self.image.split(":")[0]
        except (IndexError, AttributeError):
            pass
        if self.tag:
            self.version = None
        self.level = self._get_level()
        self.path = self._get_path()
        self.artifactregistry_v1 = ModuleHandler(
            "google.cloud.artifactregistry_v1"
        ).please_import(who_is_calling="ArtifactRegistry")
        self.client = ClientHandler(
            self.artifactregistry_v1.ArtifactRegistryClient
        ).get()
        self.types = self.artifactregistry_v1.types
        self.FailedPrecondition = ModuleHandler(
            "google.api_core.exceptions"
        ).please_import("FailedPrecondition", who_is_calling="ArtifactRegistry")
        self.parent = self._get_parent()

    def _get_level(self):
        """
        Get the level of the path. Can be either 'project', 'location', 'repository', or 'file'.

        Returns:
        - str: The level of the path.
        """
        if self.tag or self.version:
            return "digest"
        elif self.image:
            return "image"
        elif self.repository:
            return "repository"
        elif self.location:
            return "location"
        elif self.project:
            return "project"
        else:
            return None

    def _get_path(self, shorten=True):
        """
        Get the path to the resource.

        Args:
        - shorten (bool): Whether to shorten the path to `project/location/repository/file`.

        Returns:
        - str: The path to the resource.
        """
        path = ""
        if self.level is None:
            return path
        elif self.level == "project":
            path = f"projects/{self.project}"
        elif self.level == "location":
            path = f"projects/{self.project}/locations/{self.location}"
        elif self.level == "repository":
            path = f"projects/{self.project}/locations/{self.location}/repositories/{self.repository}"
        elif self.level == "image":
            path = f"projects/{self.project}/locations/{self.location}/repositories/{self.repository}/packages/{self.image}"
        elif self.level == "digest" and self.tag:
            path = f"projects/{self.project}/locations/{self.location}/repositories/{self.repository}/packages/{self.image}/tags/{self.tag}"
        elif self.level == "digest" and self.version:
            path = f"projects/{self.project}/locations/{self.location}/repositories/{self.repository}/packages/{self.image}/versions/sha256:{self.version}"
        if shorten:
            path = "/".join(path.split("/")[1::2])
        return path

    def _get_parent(self):
        """
        Get the parent resource. This is used for making requests to the API. For us this is either location or project.

        Returns:
        - str: The parent resource.
        """
        if self.location is not None:
            return f"projects/{self.project}/locations/{self.location}"
        elif self.project is not None:
            return f"projects/{self.project}"
        else:
            return ""

    def ls_repositories(self, full_id=False):
        """
        List repositories in the Artifact Registry for a given location.

        Args:
        - full_id (bool): Whether to return the full repository ID or just the name.

        Returns:
        - list: The list of repositories.
        """
        output = self.client.list_repositories(parent=self.parent)
        output = [repository.name for repository in output]
        if not full_id:
            output = [repository.split("/")[-1] for repository in output]
        return output

    def ls_files(self, repository=None):
        """
        List files in a repository.

        Args:
        - repository (str): The name of the repository.

        Returns:
        - list: The list of files.
        """
        repository = repository or self.repository
        parent = f"{self.parent}/repositories/{repository}"
        output = self.client.list_files(parent=parent)
        output = [file.name for file in output]
        return output

    def ls_images(self, repository=None, image=None, full_id=False):
        """
        List images in a repository.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - full_id (bool): Whether to return the full image ID or just the name.

        Returns:
        - list: The list of images.
        """
        repository = repository or self.repository
        image = image or self.image
        parent = f"{self.parent}/repositories/{repository}"
        output = self.client.list_packages(parent=parent)
        output = [package.name for package in output]
        if not full_id:
            # Careful not to split("/") in case there is a "/" in the package name
            images = [package.replace(f"{parent}/packages/", "") for package in output]
            output = [f"{repository}/{image}" for image in images]
        return output

    def ls_versions(self, repository=None, image=None, tag=None, full_id=False):
        """
        List versions in an image.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - tag (str): The tag of the image.
        - full_id (bool): Whether to return the full tag ID or just the name.

        Returns:
        - list: The list of tags, sorted by creation time (latest first)
        """
        repository = repository or self.repository
        image = image or self.image
        tag = tag or self.tag
        parent = f"{self.parent}/repositories/{repository}/packages/{image}"
        output = self.client.list_versions(parent=parent)
        output = [(tag.name, tag.create_time) for tag in output]
        output = sorted(output, key=lambda x: x[1], reverse=True)
        output = [tag[0] for tag in output]
        if not full_id:
            versions = [tag.replace(f"{parent}/versions/", "") for tag in output]
            output = [f"{repository}/{image}/{version}" for version in versions]
        return output

    def ls_tags(self, repository=None, image=None, version=None, full_id=False):
        """
        List tags in a version.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - version (str): The version of the image.
        - full_id (bool): Whether to return the full tag ID or just the name.

        Returns:
        - list: The list of tags.
        """
        repository = repository or self.repository
        image = image or self.image
        version = version or self.version
        parent = f"{self.parent}/repositories/{repository}/packages/{image}/versions/sha256:{version}"
        breakpoint()
        output = self.client.list_tags(parent=parent)
        output = [tag.name for tag in output]
        if not full_id:
            tags = [tag.replace(f"{parent}/tags/", "") for tag in output]
            output = [f"{repository}/{image}:{tag}" for tag in tags]
        return output

    def ls(self):
        """
        List repositories or files in a repository.

        Returns:
        - list: The list of repositories or files.
        """
        if self.level == "image":
            return self.ls_versions()
        elif self.level == "repository":
            return self.ls_images()
        elif self.level == "location":
            return self.ls_repositories()
        elif self.level == "project":
            raise ValueError("Cannot list items at the project level.")

    def get_repository(self, repository=None):
        """
        Get a repository.

        Args:
        - repository (str): The name of the repository.

        Returns:
        - Repository: The repository.
        """
        repository = repository or self.repository
        parent = f"{self.parent}/repositories/{repository}"
        return self.client.get_repository(name=parent)

    def get_image(self, repository=None, image=None):
        """
        Get an image.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.

        Returns:
        - Package: The image.
        """
        repository = repository or self.repository
        image = image or self.image
        parent = f"{self.parent}/repositories/{repository}/packages/{image}"
        return self.client.get_package(name=parent)

    def get_version(self, repository=None, image=None, version=None):
        """
        Get a version.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - version (str): The version of the image.

        Returns:
        - Version: The version.
        """
        repository = repository or self.repository
        image = image or self.image
        version = version or self.version
        parent = f"{self.parent}/repositories/{repository}/packages/{image}/versions/sha256:{version}"
        return self.client.get_version(name=parent)

    def get_version_from_tag(self, repository=None, image=None, tag=None):
        """
        Get a tag.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - tag (str): The tag of the image.

        Returns:
        - Tag: The tag.
        """
        repository = repository or self.repository
        image = image or self.image
        tag = tag or self.tag
        parent = f"{self.parent}/repositories/{repository}/packages/{image}/tags/{tag}"
        result = self.client.get_tag(name=parent)
        if result is None:
            raise ValueError(f"Tag not found in {self.location}/{repository}/{image}.")
        version = result.version
        sha256_version = version.replace(
            f"{self.parent}/repositories/{repository}/packages/{image}/versions/sha256:",
            "",
        )
        return sha256_version

    def get_tag(self, repository=None, image=None, tag=None):
        """
        Get a tag.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - tag (str): The tag of the image.

        Returns:
        - Tag: The tag.
        """
        version = self.get_version_from_tag(repository, image, tag)
        output = self.get_version(repository, image, version)
        return output

    def get(self):
        """
        Get an image or version.

        Returns:
        - Package or Version: The image or version.
        """
        if self.level == "repository":
            return self.get_repository()
        elif self.level == "image":
            return self.get_image()
        elif self.level == "digest":
            if self.tag:
                return self.get_tag()
            elif self.version:
                return self.get_version()
        else:
            raise ValueError("Cannot get item at this level.")

    def delete_repository(self, repository=None):
        """
        Delete a repository.

        Args:
        - repository (str): The name of the repository.

        Returns:
        - None
        """
        repository = repository or self.repository
        parent = f"{self.parent}/repositories/{repository}"
        output = self.client.delete_repository(name=parent)
        output.result()
        log(f"Artifact Registry - Deleted repository {self.location}/{repository}.")
        return output

    def delete_image(self, repository=None, image=None):
        """
        Delete an image.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.

        Returns:
        - None
        """
        repository = repository or self.repository
        image = image or self.image
        parent = f"{self.parent}/repositories/{repository}/packages/{image}"
        output = self.client.delete_package(name=parent)
        output.result()
        log(f"Artifact Registry - Deleted image {self.location}/{repository}/{image}.")
        return output

    def delete_version(self, repository=None, image=None, version=None):
        """
        Delete a version.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - version (str): The version of the image.

        Returns:
        - None
        """
        repository = repository or self.repository
        image = image or self.image
        version = version or self.version
        parent = f"{self.parent}/repositories/{repository}/packages/{image}/versions/sha256:{version}"
        output = self.client.delete_version(name=parent)
        try:
            output.result()
        except self.FailedPrecondition as e:
            if "because it is tagged." in str(e):
                breakpoint()
        log(
            f"Artifact Registry - Deleted digest {self.location}/{repository}/{image}/sha256:{version}"
        )
        return output

    def delete_tag(self, repository=None, image=None, tag=None):
        """
        Delete a tag.

        Args:
        - repository (str): The name of the repository.
        - image (str): The name of the image.
        - tag (str): The tag of the image.

        Returns:
        - None
        """
        repository = repository or self.repository
        image = image or self.image
        tag = tag or self.tag
        version = self.get_version_from_tag(repository, image, tag)
        parent = f"{self.parent}/repositories/{repository}/packages/{image}/versions/sha256:{version}"
        output = self.client.delete_tag(name=parent)
        output.result()
        log(
            f"Artifact Registry - Deleted digest {self.location}/{repository}/{image}:{tag}."
        )
        return output

    def delete(self):
        """
        Delete an image, version, or tag.

        Returns:
        - None
        """
        if self.level == "repository":
            return self.delete_repository()
        elif self.level == "image":
            return self.delete_image()
        elif self.level == "digest":
            if self.tag:
                return self.delete_tag()
            elif self.version:
                return self.delete_version()
        else:
            raise ValueError("Cannot delete item at this level.")


if __name__ == "__main__":
    ArtifactRegistry(
        "gcr.io/example-service-123/sha256:411f06abcbda4b36a77c6e792e699b4eeb0193ebe441b6144f8fe42db6eada47",
        location="us",
    ).ls()