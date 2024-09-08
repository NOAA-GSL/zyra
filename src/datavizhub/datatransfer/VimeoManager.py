import vimeo


class VimeoManager:
    """
    VimeoUploader is a specialized class designed to facilitate the uploading of videos to Vimeo.
    This class simplifies the process of interacting with the Vimeo API, providing an intuitive
    interface for uploading videos, managing video settings, and handling video metadata.

    Built upon the 'PyVimeo' library, the VimeoUploader encapsulates various aspects of the Vimeo
    API, such as authentication, video upload, and response handling. It is ideal for applications
    where seamless integration with Vimeo's video hosting platform is required, such as in content
    management systems, video processing pipelines, or social media applications.

    Usage:
    Initialize the class with Vimeo API credentials (client ID, client secret, and access token).
    Utilize the `upload_video` method to upload videos to Vimeo. The class can be extended to include
    additional functionalities provided by the Vimeo API, such as updating video metadata or deleting videos.

    Example:
    ```python
    vimeo_uploader = VimeoUploader('CLIENT_ID', 'CLIENT_SECRET', 'ACCESS_TOKEN')
    video_uri = vimeo_uploader.upload_video('/path/to/video.mp4', 'My Video Title')
    print(f'Uploaded video is available at: {video_uri}')
    ```

    Note:
    Ensure that the Vimeo API credentials used are securely stored and have the necessary permissions
    for the actions you intend to perform. Also, be aware of Vimeo's API rate limits and terms of service
    to avoid any disruptions in service.
    """

    def __init__(self, client_id, client_secret, access_token):
        """
        Initialize the VimeoUploader with Vimeo API credentials.

        Args:
            client_id (str): The client ID for the Vimeo API.
            client_secret (str): The client secret for the Vimeo API.
            access_token (str): The access token for the Vimeo API.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.vimeo_client = vimeo.VimeoClient(
            token=access_token, key=client_id, secret=client_secret
        )

    def upload_video(self, file_path, video_name=None):
        """
        Upload a video to Vimeo.

        Args:
            file_path (str): The path to the video file to upload.
            video_name (str, optional): The name of the video. Defaults to None.

        Returns:
            str: The URI of the uploaded video on Vimeo.

        Raises:
            Exception: If the upload fails or the response is invalid.
        """
        try:
            response = self.vimeo_client.upload(file_path, data={"name": video_name})

            # Validate response
            if isinstance(response, dict) and "uri" in response:
                return response["uri"]
            else:
                raise Exception("Invalid response received from Vimeo API.")

        except Exception as e:
            # Handle or rethrow exception with additional context
            raise Exception(f"Failed to upload video to Vimeo: {str(e)}") from e

    def update_video(self, file_path, video_uri):
        """
        Update a video on Vimeo.

        Args:
            file_path (str): The path to the video file to update.
            video_uri (str): The URI of the existing video. (Ex: '/videos/900195230')

        Returns:
            str: The URI of the uploaded video on Vimeo.

        Raises:
            Exception: If the update fails or the response is invalid.
        """
        try:
            response = self.vimeo_client.replace(video_uri, file_path)

            # Validate response
            if isinstance(response, str):
                return response
            else:
                raise Exception("Invalid response received from Vimeo API.")

        except Exception as e:
            # Handle or rethrow exception with additional context
            raise Exception(f"Failed to update video on Vimeo: {str(e)}") from e

    def update_video_description(self, video_uri, new_description):
        """
        Update the description of a video on Vimeo.

        Args:
            video_uri (str): The URI of the video to update. (Ex: '/videos/123456789')
            new_description (str): The new description for the video.

        Returns:
            str: A confirmation message if the update is successful.

        Raises:
            Exception: If the update fails or the response is invalid.
        """
        try:
            # Prepare the patch data with the new description
            patch_data = {'description': new_description}

            # Send the PATCH request to update the video's description
            response = self.vimeo_client.patch(video_uri, data=patch_data)

            # Validate response
            if response.status_code == 200:  # HTTP OK
                return f"Description updated successfully for video: {video_uri}"
            else:
                raise Exception(f"Failed to update video description. Response status code: {response.status_code}")

        except Exception as e:
            # Handle or rethrow exception with additional context
            raise Exception(f"Failed to update video description on Vimeo: {str(e)}") from e


    # Additional methods for other functionalities like updating or deleting videos can be added here
