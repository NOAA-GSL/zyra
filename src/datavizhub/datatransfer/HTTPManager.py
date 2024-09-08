import logging
from pathlib import Path

import requests


class HTTPHandler:
    """Handles HTTP operations such as file downloads."""

    @staticmethod
    def download_file(url, filename):
        """Helper method to download a file from a given URL."""
        try:
            response = requests.get(url, timeout=10)  # Added timeout for safety
            response.raise_for_status()  # This will raise an exception for 4xx/5xx errors

            with Path(filename).open('wb') as f:
                f.write(response.content)
            logging.info(f"Successfully downloaded {url}")

        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred while downloading {url}: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            logging.error(f"Connection error occurred while downloading {url}: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logging.error(f"Timeout occurred while downloading {url}: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Error occurred while downloading {url}: {req_err}")
        except Exception as e:
            logging.error(f"An error occurred while downloading {url}: {e}")

    @staticmethod
    def fetch_data(url):
        """Fetches data from a given URL and returns it."""
        try:
            response = requests.get(url, timeout=10)  # Added timeout for safety
            response.raise_for_status()  # Raises an exception for 4xx/5xx errors
            return response.content  # Return the content of the response

        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred while fetching data from {url}: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            logging.error(f"Connection error occurred while fetching data from {url}: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logging.error(f"Timeout occurred while fetching data from {url}: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Error occurred while fetching data from {url}: {req_err}")
        except Exception as e:
            logging.error(f"An error occurred while fetching data from {url}: {e}")

        # Return None if there was an error
        return None

    @staticmethod
    def fetch_text(url):
        """Fetch the content of a URL as text."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raises stored HTTPError, if one occurred.
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            return None

    @staticmethod
    def fetch_json(url):
        """Fetch the content of a URL and parse it as JSON."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raises stored HTTPError, if one occurred.
            return response.json()  # Converts JSON response into Python dictionary
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            return None

    @staticmethod
    def post_data(url, data, headers=None):
        """Send data to a URL using POST and return the response."""
        try:
            response = requests.post(url, data=data, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Post request failed: {e}")
            return None

    @staticmethod
    def fetch_headers(url):
        """Fetch the headers of a URL."""
        try:
            response = requests.head(url, timeout=10)
            response.raise_for_status()
            return response.headers
        except requests.exceptions.RequestException as e:
            logging.error(f"HEAD request failed: {e}")
            return None
