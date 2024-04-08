import os
import json

from gcp_tools.utils import try_import

try_import("google.cloud.functions_v2", "CloudFunctions")
import google.cloud.functions_v2 as functions_v2
from google.cloud.functions_v2 import (
    Function,
    BuildConfig,
    ServiceConfig,
    Source,
    StorageSource,
    RepoSource,
    CreateFunctionRequest,
    UpdateFunctionRequest,
)
from google.protobuf.field_mask_pb2 import FieldMask

from gcp_tools.utils import get_default_project, log, get_all_kwargs


class CloudFunctions:

    _clients = {}

    def __init__(self, name=None, project=None, location="europe-west2"):
        self.name = name
        self.project = project or os.environ.get("PROJECT") or get_default_project()
        self.location = location
        self.parent = f"projects/{self.project}/locations/{self.location}"
        self.location_id = self.parent
        self.function_id = f"{self.parent}/functions/{self.name}"

        if self.project in self._clients:
            self.client = self._clients[self.project]
        else:
            self.client = functions_v2.FunctionServiceClient()
            self._clients[self.project] = self.client

    def __repr__(self):
        return f"CloudFunctions({self.name})"

    def ls(self, active_only=False):
        """
        Lists all cloud functions in the project.

        Args:
        - active_only (bool): Whether to only list active cloud functions.

        Returns:
        - (list) List of cloud functions.
        """
        parent = f"projects/{self.project}/locations/{self.location}"
        request = functions_v2.ListFunctionsRequest(parent=parent)
        page_result = self.client.list_functions(request)
        if active_only:
            output = [f.name for f in page_result if f.status.name == "ACTIVE"]
        else:
            output = [f.name for f in page_result]
        return output

    def get(self, name=None):
        """
        Gets a cloud function.

        Args:
        - name (str): The name of the cloud function.

        Returns:
        - (dict) The cloud function.
        """
        if name:
            function_id = f"{self.parent}/functions/{name}"
        else:
            function_id = self.function_id
        request = functions_v2.GetFunctionRequest(name=function_id)
        output = self.client.get_function(request)
        return output

    def exists(self):
        """
        Checks if a cloud function exists.

        Returns:
        - (bool) True if the cloud function exists, False otherwise.
        """
        try:
            self.get()
            return True
        except Exception as e:
            return False

    def call(self, data=None):
        """
        Calls a cloud function.

        Args:
        - data (dict|str): The data to send to the cloud function. If a dict is provided, it will be converted to a JSON string.

        Returns:
        - (dict) The response from the cloud function.
        """
        if data is None:
            data = {}
        payload = json.dumps(data) if isinstance(data, dict) else data
        request = functions_v2.CallFunctionRequest(name=self.name, data=payload)
        print(f"Sending request to cloud function {self.name}...")
        result = self.client.call_function(request)
        return result

    def deploy(
        self,
        source,
        entry_point,
        runtime,
        if_exists="REPLACE",
        **kwargs,
    ):
        """
        Deploys a cloud function.

        Args:
        - source (str): The path to the source code.
        - entry_point (str): The name of the function to execute.
        - runtime (str): The runtime of the cloud function.
        - generation (int): The generation of the cloud function.
        - kwargs (dict): Additional arguments to pass to the cloud function. Available arguments are:
            - description (str): The description of the cloud function.
            - timeout (int): The timeout of the cloud function in seconds.
            - available_memory_mb (int): The amount of memory available to the cloud function in MB.
            - service_account_email (str): The service account email to use for the cloud function.
            - version_id (str): The version ID of the cloud function.
            - labels (dict): The labels to apply to the cloud function.
            - environment_variables (dict): The environment variables to set for the cloud function.
            - max_instances (int): The maximum number of instances to allow for the cloud function.
            - min_instances (int): The minimum number of instances to allow for the cloud function.


        Returns:
        - (dict) The response from the cloud function.
        """
        input_args = {
            "runtime": runtime,
            "entry_point": entry_point,
            "source": source,
            "if_exists": if_exists,
            **kwargs,
        }
        if source.startswith("https://") or source.startswith("gs://"):
            return self.deploy_from_repo(**input_args)
        else:
            return self.deploy_from_zip(**input_args)

    def deploy_from_zip(
        self,
        source,
        entry_point,
        **kwargs,
    ):
        """
        Deploys a cloud function from a zip file.

        Args:
        - source (str): The path to the source code.
        - entry_point (str): The name of the function to execute.
        - kwargs (dict): Additional arguments to pass to the cloud function.

        Returns:
        - (dict) The response from the cloud function.
        """
        if not os.path.exists(source):
            raise FileNotFoundError(f"Local file not found: {source}")

        from gcp_tools import Storage
        from gcp_tools.utils import zip_directory

        log(f"Creating zip file from {source} and uploading to GCS...")
        zip_path = zip_directory(source)
        # Upload the zip file to GCS
        bucket_name = f"{self.project}-cloud-functions"
        upload_path = f"{bucket_name}/cloud-functions/{self.name}/{self.name}.zip"
        Storage(upload_path).upload(zip_path)
        # Deploy the cloud function
        source_archive_url = Storage(upload_path).path
        return self.deploy_from_repo(
            source_archive_url, entry_point=entry_point, **kwargs
        )

    def deploy_from_repo(
        self,
        source,
        entry_point,
        trigger="HTTP",
        https_trigger=None,
        event_trigger=None,
        if_exists="REPLACE",
        generation=1,
        wait_to_complete=True,
        **kwargs,
    ):
        """
        Deploys a cloud function from a repository.

        Args:
        - source (str): The path to the source code.
        - entry_point (str): The name of the function to execute.
        - kwargs (dict): Additional arguments to pass to the cloud function.

        Returns:
        - (dict) The response from the cloud function.
        """

        log(f"Deploying cloud function '{self.name}' from repository {source}...")
        if source.startswith("gs://"):
            from gcp_tools import Storage

            obj = Storage(source)
            bucket_name, file_name = obj.bucket_name, obj.file_name
            storage_source = StorageSource(bucket=bucket_name, object=file_name)
            source = Source(storage_source=storage_source)
        else:
            source = Source(repository=RepoSource(url=source))
        all_kwargs = get_all_kwargs(locals())
        function_exists = self.exists()
        function_kwargs, service_kwargs, build_kwargs = self._split_deploy_kwargs(
            all_kwargs
        )
        kwargs = {k: v for k, v in kwargs.items() if k not in all_kwargs}
        build_config = BuildConfig(**build_kwargs)
        service_config = ServiceConfig(**service_kwargs)
        cloud_function = Function(
            name=self.function_id,
            build_config=build_config,
            service_config=service_config,
            **function_kwargs,
            **kwargs,
        )
        if function_exists and if_exists == "REPLACE":
            log(f"Updating existing cloud function '{self.name}'...")
            update_mask = FieldMask(
                paths=["build_config", "service_config"] + list(kwargs.keys())
            )
            request = UpdateFunctionRequest(
                function=cloud_function, update_mask=update_mask
            )
            output = self.client.update_function(request)
        else:
            print(f"Creating new cloud function '{self.name}'...")
            request = CreateFunctionRequest(
                function=cloud_function, parent=self.parent, function_id=self.name
            )
            output = self.client.create_function(request)
        self._handle_deploy_response(output, wait_to_complete)
        return output

    def _handle_deploy_response(self, response, wait_to_complete):
        if wait_to_complete:
            log("Waiting for the deployment to complete...")
            response.result(timeout=300)
        # Check that the function was deployed and is active
        function = self.get()
        service_config = function.service_config
        print(f"Cloud function '{self.name}': {function.state.name}.")
        if wait_to_complete:
            print(f"Version: {service_config.revision}")
            print(f"URI: {service_config.uri}")

    def _split_deploy_kwargs(self, kwargs):
        """
        Splits the deploy kwargs into function, service and build kwargs.

        Returns:
        - (dict, dict, dict) The function, service and build kwargs.
        """
        function_kwargs = {}
        service_kwargs = {}
        build_kwargs = {}
        for key, value in kwargs.items():
            if key in Function.__annotations__:
                function_kwargs[key] = value
            elif key in ServiceConfig.__annotations__:
                service_kwargs[key] = value
            elif key in BuildConfig.__annotations__:
                build_kwargs[key] = value
        return function_kwargs, service_kwargs, build_kwargs


if __name__ == "__main__":
    CloudFunctions("sample").deploy(
        "samples/cloud_function",
        entry_point="entry_point",
        runtime="python310",
    )
