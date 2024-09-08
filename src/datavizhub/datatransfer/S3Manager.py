import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError


class S3Manager:
    """
    S3Manager is a class designed for simplified interaction with Amazon S3 (Simple Storage Service).
    It provides a streamlined and intuitive interface for common S3 operations such as uploading,
    downloading, and managing files in an S3 bucket. This class is built on top of the 'boto3' library,
    the official Amazon Web Services (AWS) SDK for Python.

    The S3Manager class handles tasks like file uploads to S3, downloads from S3, and could be extended
    to include more complex functionalities like listing bucket contents, deleting files, or managing
    bucket policies. It abstracts away the lower-level function calls to 'boto3', providing a more
    accessible interface for performing these operations.

    Usage:
    Initialize the class with AWS credentials (access key and secret key) and the name of the S3 bucket.
    Methods are provided for uploading and downloading files, with the potential to extend the class
    for additional S3 functionalities as needed.

    Example:
    ```python
    s3_manager = S3Manager('ACCESS_KEY', 'SECRET_KEY', 'my-s3-bucket')
    s3_manager.upload_file('/path/to/local/file.txt', 'remote_file.txt')
    s3_manager.download_file('remote_file.txt', '/path/to/local/downloaded_file.txt')
    ```

    Note:
    Proper handling of AWS credentials is crucial for the security of your S3 data. Ensure that the
    credentials provided to this class have the appropriate permissions for the intended operations and
    are managed securely, preferably using AWS IAM roles and policies.
    """

    def __init__(self, access_key, secret_key, bucket_name):
        """
        Initialize the S3Manager with AWS credentials and the name of the bucket.

        Args:
            access_key (str): AWS access key.
            secret_key (str): AWS secret key.
            bucket_name (str): Name of the S3 bucket to interact with.
        """
        try:
            self.bucket_name = bucket_name
            self.s3_client = boto3.client(
                "s3", aws_access_key_id=access_key, aws_secret_access_key=secret_key
            )
            logging.debug(f"Connection to {bucket_name} established.")
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            return False
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to upload file to S3: {e}")
            return False

    def download_file(self, file_path, local_file_name):
        """
        Download a file from the specified S3 bucket.

        Args:
            file_path (str): The path to the file to download.
            local_file_name (str): The name to use for the file downloaded from S3.

        Returns:
            bool: True if download was successful, False otherwise.
        """
        try:
            self.s3_client.download_file(self.bucket_name, file_path, local_file_name)
            logging.info(f"{local_file_name} downloaded from {self.bucket_name}")
            return True
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            return False
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to download file from S3: {e}")
            return False

    def upload_file(self, file_path, s3_file_name):
        """
        Upload a file to the specified S3 bucket.

        Args:
            file_path (str): The path to the file to upload.
            s3_file_name (str): The name to use for the file in S3.

        Returns:
            bool: True if upload was successful, False otherwise.
        """
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, s3_file_name)
            logging.info(f"{s3_file_name} uploaded to {self.bucket_name}")
            return True
        except NoCredentialsError:
            logging.error("Credentials not available for AWS S3.")
            return False
        except (ClientError, BotoCoreError) as e:
            logging.error(f"Failed to upload file to S3: {e}")
            return False

    # Additional methods for other S3 functionalities (e.g., list_files, delete_file) can be added here
