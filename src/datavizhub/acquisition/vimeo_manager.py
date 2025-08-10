"""Vimeo upload manager using PyVimeo.

Implements :class:`~datavizhub.acquisition.base.DataAcquirer` with upload-only
support to Vimeo. Fetching and listing are not supported.
"""

from typing import Iterable, Optional

import vimeo

from datavizhub.acquisition.base import DataAcquirer


class VimeoManager(DataAcquirer):
    CAPABILITIES = {"upload"}
    """Upload videos to Vimeo using PyVimeo.

    This manager encapsulates video uploads and updates via the Vimeo API
    using :mod:`PyVimeo`. It participates in the acquisition interface for
    pipeline consistency, though generic file fetching/listing is not
    supported for Vimeo in this project.

    Supported Protocols
    -------------------
    - Vimeo API (token-based)

    Parameters
    ----------
    client_id : str
        Vimeo API client ID.
    client_secret : str
        Vimeo API client secret.
    access_token : str
        Vimeo API access token.

    Examples
    --------
    Upload a video and get its URI::

        from datavizhub.acquisition.vimeo_manager import VimeoManager

        vm = VimeoManager(client_id, client_secret, access_token)
        vm.connect()
        uri = vm.upload_video("/path/to/video.mp4", video_name="My Video")
        vm.disconnect()
        print(uri)
    """

    def __init__(self, client_id: str, client_secret: str, access_token: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.vimeo_client: Optional[vimeo.VimeoClient] = None

    def connect(self) -> None:
        """Initialize the Vimeo client using provided credentials."""
        self.vimeo_client = vimeo.VimeoClient(
            token=self.access_token, key=self.client_id, secret=self.client_secret
        )

    def fetch(self, remote_path: str, local_filename: Optional[str] = None) -> bool:
        """Fetching from Vimeo is not supported.

        Raises
        ------
        NotImplementedError
            Always raised to indicate downloads are not supported.
        """
        raise NotImplementedError("Fetching from Vimeo is not supported.")

    def list_files(self, remote_path: Optional[str] = None) -> Optional[Iterable[str]]:
        """Listing is not implemented for Vimeo.

        Returns
        -------
        None
            Always returns ``None``.
        """
        return None

    def disconnect(self) -> None:
        """Release the Vimeo client reference."""
        self.vimeo_client = None

    # Existing functionality
    def upload_video(self, file_path: str, video_name: Optional[str] = None) -> str:
        """Upload a local video to Vimeo.

        Parameters
        ----------
        file_path : str
            Path to the local video file.
        video_name : str, optional
            Optional title to assign to the video.

        Returns
        -------
        str
            The Vimeo video URI for the uploaded content.

        Raises
        ------
        Exception
            If the upload fails or the response cannot be interpreted.
        """
        if self.vimeo_client is None:
            self.connect()
        assert self.vimeo_client is not None
        response = self.vimeo_client.upload(file_path, data={"name": video_name})
        if isinstance(response, dict) and "uri" in response:
            return response["uri"]
        elif isinstance(response, str):
            return response
        else:
            raise Exception("Invalid response received from Vimeo API.")

    def upload(self, local_path: str, remote_path: str) -> bool:
        """Standardized upload interface mapping to :meth:`upload_video`.

        Parameters
        ----------
        local_path : str
            Local video file path.
        remote_path : str
            Interpreted as the Vimeo video name/title.

        Returns
        -------
        bool
            ``True`` if an upload URI was returned.
        """
        uri = self.upload_video(local_path, video_name=remote_path)
        return bool(uri)

    def update_video(self, file_path: str, video_uri: str) -> str:
        """Replace the video file for an existing Vimeo video.

        Parameters
        ----------
        file_path : str
            Path to the replacement video file.
        video_uri : str
            Vimeo video URI (e.g., ``"/videos/12345"``).

        Returns
        -------
        str
            The URI of the updated video.

        Raises
        ------
        Exception
            If the update fails or the response cannot be interpreted.
        """
        if self.vimeo_client is None:
            self.connect()
        assert self.vimeo_client is not None
        response = self.vimeo_client.replace(video_uri, file_path)
        if isinstance(response, str):
            return response
        else:
            raise Exception("Invalid response received from Vimeo API.")

    def update_video_description(self, video_uri: str, new_description: str) -> str:
        """Update the description of a Vimeo video.

        Parameters
        ----------
        video_uri : str
            Vimeo video URI (e.g., ``"/videos/12345"``).
        new_description : str
            New description text to set.

        Returns
        -------
        str
            Confirmation message when the update succeeds.

        Raises
        ------
        Exception
            If the Vimeo API call fails.
        """
        if self.vimeo_client is None:
            self.connect()
        assert self.vimeo_client is not None
        patch_data = {"description": new_description}
        response = self.vimeo_client.patch(video_uri, data=patch_data)
        if hasattr(response, "status_code") and response.status_code == 200:
            return f"Description updated successfully for video: {video_uri}"
        else:
            raise Exception(
                f"Failed to update video description. Response status code: {getattr(response, 'status_code', 'unknown')}"
            )
