# SPDX-License-Identifier: Apache-2.0
import pytest

from zyra.utils.credential_manager import CredentialManager


# Test Initialization
def test_initialization_without_filename():
    manager = CredentialManager()
    assert manager.filename is None


def test_initialization_with_filename():
    manager = CredentialManager("tests/testdata/credentials")
    assert manager.filename == "tests/testdata/credentials"


# Test Reading Credentials
def test_read_valid_credentials():
    # Assuming 'credentials' has valid credentials
    manager = CredentialManager("tests/testdata/credentials")
    manager.read_credentials(expected_keys=["SOME_KEY"])
    assert manager.get_credential("SOME_KEY") is not None


def test_read_nonexistent_file():
    manager = CredentialManager("tests/testdata/nonexistent")
    with pytest.raises(FileNotFoundError):
        manager.read_credentials()


# Test Adding and Deleting Credentials
def test_add_credential():
    manager = CredentialManager()
    manager.add_credential("TEST_KEY", "TEST_VALUE")
    assert manager.get_credential("TEST_KEY") == "TEST_VALUE"


def test_delete_credential():
    manager = CredentialManager()
    manager.add_credential("TEST_KEY", "TEST_VALUE")
    manager.delete_credential("TEST_KEY")
    with pytest.raises(KeyError):
        manager.get_credential("TEST_KEY")


# Test Context Manager
def test_context_manager():
    with CredentialManager() as manager:
        manager.add_credential("TEMP_KEY", "TEMP_VALUE")
        assert manager.get_credential("TEMP_KEY") == "TEMP_VALUE"
    with pytest.raises(KeyError):
        manager.get_credential("TEMP_KEY")


# Test Clear Credentials
def test_clear_credentials():
    manager = CredentialManager()
    manager.add_credential("TEMP_KEY1", "TEMP_VALUE1")
    manager.add_credential("TEMP_KEY2", "TEMP_VALUE2")
    manager.clear_credentials()
    assert len(manager.credentials) == 0
