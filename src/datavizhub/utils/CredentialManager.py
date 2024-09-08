import logging
from pathlib import Path

from dotenv import dotenv_values, find_dotenv


class CredentialManager:
    """
    CredentialManager is a class for managing application credentials securely and efficiently.
    It reads credentials from a specified .env file and manages them internally, providing
    functionalities for adding, listing, deleting, and retrieving credentials. This approach
    ensures that credentials are not exposed to the entire process environment, enhancing security.

    This class can also be used as a context manager, ensuring that all credentials are
    automatically managed within a specific execution context and do not persist beyond their
    intended scope. This is particularly useful for managing the lifecycle of credentials.

    A namespace can optionally be used as a prefix for all credential keys managed by this class.
    This helps to avoid conflicts with other keys and to organize them better.

    The credentials file should be in the format 'key=value'. The class checks for the presence
    of expected keys and raises an error if they're missing. It also allows for the dynamic
    addition and deletion of credentials during runtime.

    Logging is used to track the operations on credentials, aiding in debugging and monitoring.

    Example Usage:
        # Without a namespace
        credential_manager = CredentialManager("path/to/credentials.env")
        credential_manager.read_credentials(expected_keys=['API_KEY', 'SECRET_KEY'])
        credential_manager.add_credential('NEW_KEY', 'new_value')
        credential_manager.delete_credential('NEW_KEY')
        print(credential_manager.list_credentials())  # Lists the current credential keys

        # With a namespace
        credential_manager_ns = CredentialManager("path/to/credentials.env", namespace="MYAPP_")
        credential_manager_ns.read_credentials(expected_keys=['API_KEY', 'SECRET_KEY'])
        # ...

    Example Usage as a Context Manager:
        with CredentialManager("path/to/credentials.env") as credential_manager:
            credential_manager.read_credentials(expected_keys=['API_KEY', 'SECRET_KEY'])
            # Credentials are managed within this block
        # Exiting the block clears the credentials

    Attributes:
        filename (str): Path to the .env file containing credentials.
        namespace (str): Optional prefix for the credential keys managed by this class.
        credentials (dict): Dictionary that stores the credential keys and their values.

    Methods:
        read_credentials(expected_keys=None): Reads credentials from the .env file and stores them internally.
                                              Optionally checks for expected keys.
        list_credentials(expected_keys=None): Returns a list of currently stored credential keys.
                                              Optionally checks for specific expected keys.
        add_credential(key, value): Adds a new credential key-value pair to the stored credentials.
        get_credential(key): Retrieves the value of a credential by its key.
        delete_credential(key): Removes a credential key from the stored credentials.
        clear_credentials(): Clears all the stored credential keys and their values.
    """

    def __init__(self, filename=None, namespace=None):
        """
        Initialize the CredentialManager. If a filename is provided, it will be used to read credentials.
        Otherwise, the CredentialManager starts with no tracked credentials.

        Args:
            filename (str, optional): The name of the file containing the credentials. Defaults to None.
            namespace (str, optional): Prefix for the environment variables managed by this class. Defaults to None.
        """
        self.filename = filename
        self.namespace = namespace if namespace else ""
        self.credentials = {}

    def __enter__(self):
        """
        Enter the runtime context related to this object.
        Reads and sets credentials as environment variables upon entering the context.
        """
        if self.filename:
            self.read_credentials()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the runtime context and perform any cleanup actions.
        Clears all tracked credentials upon exiting the context.

        Args:
            exc_type (Exception): Type of the exception (if any occurred).
            exc_val (Exception): Exception instance (if any occurred).
            exc_tb (traceback): Traceback object (if any occurred).
        """
        self.clear_credentials()
        if exc_type is not None:
            logging.error(f"Exception occurred: {exc_val}")
        # Returning False to propagate the exception (if any)
        return False

    def _namespaced_key(self, key):
        """
        Apply the namespace prefix to a key, if a namespace is defined.

        Args:
            key (str): The original key name.

        Returns:
            str: Namespaced key, if namespace is provided; otherwise, original key.
        """
        return f"{self.namespace}{key}" if self.namespace else key

    def read_credentials(self, expected_keys=None):
        """
        Reads in credentials from the file and sets them as environment variables.
        It checks if all expected keys are present in the file.

        Args:
            expected_keys (list of str): A list of expected keys to be found in the file.

        Raises:
            FileNotFoundError: If the credentials file is not found.
            ValueError: If the file format is incorrect.
            KeyError: If an expected key is not found in the file.
        """
        dotenv_path = Path(self.filename) or find_dotenv()
        if dotenv_path.exists():
            env_vars = dotenv_values(dotenv_path)
            for key, value in env_vars.items():
                namespaced_key = self._namespaced_key(key)
                self.credentials[namespaced_key] = value
                logging.debug(f"Added credential key: {namespaced_key}")

            missing_keys = set(expected_keys or []) - set(self.credentials.keys())
            if missing_keys:
                raise KeyError(f"Missing expected keys: {', '.join(missing_keys)}")
        else:
            raise FileNotFoundError(f"The file {self.filename} was not found.")

    def list_credentials(self, expected_keys=None):
        """
        Lists the keys of the currently tracked credentials and optionally checks if all expected keys are present.

        Args:
            expected_keys (list of str, optional): A list of expected keys to check against the tracked credentials.

        Returns:
            list of str: A list of keys of the tracked credentials.

        Raises:
            KeyError: If any of the expected keys are not in the tracked credentials.
        """
        if expected_keys is not None:
            missing_keys = set(expected_keys) - self.tracked_keys
            if missing_keys:
                raise KeyError(f"Missing expected keys: {', '.join(missing_keys)}")

        return list(self.credentials.keys())

    def get_credential(self, key):
        """
        Retrieves the value of a credential by its key.

        Args:
            key (str): The key of the credential to retrieve.

        Returns:
            str: The value of the credential.

        Raises:
            KeyError: If the key is not found in the tracked credentials.
        """
        namespaced_key = self._namespaced_key(key)
        if namespaced_key not in self.credentials:
            raise KeyError(
                f"Credential key '{namespaced_key}' not found in credentials."
            )

        return self.credentials[namespaced_key]

    def add_credential(self, key, value):
        """
        Adds a new credential key-value pair to the tracked credentials and sets it as an environment variable.
        Updates the value of the key in environment variables if it already exists.

        Args:
            key (str): The key of the credential to add.
            value (str): The value of the credential to add.
        """
        namespaced_key = self._namespaced_key(key)
        self.credentials[namespaced_key] = value
        logging.debug(f"Added/Updated credential key: {namespaced_key}")

    def delete_credential(self, key):
        """
        Deletes a credential key from the tracked credentials and unsets it as an environment variable.

        Args:
            key (str): The key of the credential to delete.
        """
        namespaced_key = self._namespaced_key(key)
        if namespaced_key in self.credentials:
            del self.credentials[namespaced_key]
            logging.debug(f"Removed credential key: {namespaced_key}")
        else:
            logging.warning(f"Key '{namespaced_key}' not found in credentials.")

    def clear_credentials(self):
        """
        Clears all the tracked credential keys and their corresponding environment variables.
        """
        self.credentials.clear()
        logging.debug("All credentials have been cleared.")
