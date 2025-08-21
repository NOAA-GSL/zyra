from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataProcessor(ABC):
    """Abstract base for data processors in the Zyra pipeline.

    This base class defines the minimal contract that processing components
    must fulfill when transforming raw inputs (typically acquired by
    ``zyra.acquisition``) into outputs consumable by downstream
    visualization and publishing steps.

    Processors standardize three phases:

    - ``load(input_source)``: prepare or ingest the input source
    - ``process(**kwargs)``: perform the core processing/transformation
    - ``save(output_path=None)``: persist results if applicable

    An optional ``validate()`` hook is provided for input checking.

    Parameters
    ----------
    ...
        Concrete processors define their own initialization parameters
        according to their domain (e.g., input directories, output paths,
        catalog URLs). There is no common constructor on the base class.

    Examples
    --------
    Use a processor in a pipeline with an acquirer::

        from zyra.acquisition.ftp_manager import FTPManager
        from zyra.processing.video_processor import VideoProcessor

        # Acquire frames
        with FTPManager(host="ftp.example.com") as ftp:
            ftp.fetch("/pub/frames/img_0001.png", "./frames/img_0001.png")
            # ...fetch remaining frames...

        # Process frames into a video
        vp = VideoProcessor(input_directory="./frames", output_file="./out/movie.mp4")
        vp.load("./frames")
        vp.process()
        vp.save("./out/movie.mp4")
    """

    @abstractmethod
    def load(self, input_source: Any) -> None:
        """Load or prepare the input source for processing.

        Parameters
        ----------
        input_source : Any
            Location or handle of input data (e.g., directory path, file path,
            URL, opened handle). Interpretation is processor-specific.
        """

    @abstractmethod
    def process(self, **kwargs: Any) -> Any:
        """Execute core processing and return results if applicable.

        Parameters
        ----------
        **kwargs : Any
            Processor-specific options that influence the run (e.g., flags,
            thresholds, file paths).

        Returns
        -------
        Any
            A result object if the processor yields one (e.g., arrays),
            otherwise ``None``.
        """

    @abstractmethod
    def save(self, output_path: str | None = None) -> str | None:
        """Persist results and return the output path.

        Parameters
        ----------
        output_path : str, optional
            Destination path to write results. If omitted, implementations may
            use their configured default.

        Returns
        -------
        str or None
            The final output path on success; ``None`` if nothing was written.
        """

    def validate(self) -> bool:  # optional
        """Optional input validation.

        Returns
        -------
        bool
            ``True`` when inputs/environment appear valid for processing;
            otherwise ``False``.
        """
        return True

    # ---- Introspection ---------------------------------------------------------------

    @property
    def features(self) -> set[str]:
        """Set of feature strings supported by this processor.

        Returns
        -------
        set of str
            The class-level ``FEATURES`` set if defined, else an empty set.
        """
        feats = getattr(type(self), "FEATURES", None)
        return set(feats) if feats else set()
