class VideoDocError(Exception):
    """Base class for all VideoDocRAG domain exceptions."""


class InvalidProjectNameError(VideoDocError):
    """Raised when a project name cannot be turned into a valid slug."""


class InvalidConfigError(VideoDocError):
    """Raised when a project's config.yaml is missing, malformed, or fails validation."""


class InvalidSourceManifestError(VideoDocError):
    """Raised when a project's sources.yaml is missing, malformed, or fails validation."""


class ProjectNotFoundError(VideoDocError):
    """Raised when a project reference cannot be resolved to a path or registry entry."""


class RegistryConflictError(VideoDocError):
    """Raised when registering a project name would overwrite a different existing path."""


class ExternalToolNotFoundError(VideoDocError):
    """Raised when a required external binary (e.g. ffprobe) is not found on PATH."""


class NoVideosFoundError(VideoDocError):
    """Raised when a project's videos/ source (internal or external) resolves to zero video files."""


class VideoIdCollisionError(VideoDocError):
    """Raised when two different video files would resolve to the same slugified video id."""


class InvalidVideoMetadataError(VideoDocError):
    """Raised when a video's metadata.json is missing, malformed, or fails validation."""


class DatabaseError(VideoDocError):
    """Raised when a structural (not per-video) failure occurs reading or writing project.db."""
