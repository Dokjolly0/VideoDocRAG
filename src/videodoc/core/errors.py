class VideoDocError(Exception):
    """Base class for all VideoDocRAG domain exceptions."""


class InvalidProjectNameError(VideoDocError):
    """Raised when a project name cannot be turned into a valid slug."""


class InvalidConfigError(VideoDocError):
    """Raised when a project's config.yaml is missing, malformed, or fails validation."""


class ProjectNotFoundError(VideoDocError):
    """Raised when a project reference cannot be resolved to a path or registry entry."""


class RegistryConflictError(VideoDocError):
    """Raised when registering a project name would overwrite a different existing path."""
