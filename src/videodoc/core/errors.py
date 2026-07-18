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


class TranscriptionEngineError(VideoDocError):
    """Raised when config.transcription.engine is unsupported, or the configured
    transcription engine/model could not be loaded at all."""


class InvalidTranscriptError(VideoDocError):
    """Raised when a video's transcript JSON is missing, malformed, or fails validation."""


class InvalidFrameManifestError(VideoDocError):
    """Raised when a video's frames.json manifest is missing, malformed, or fails validation."""



class InvalidOCRManifestError(VideoDocError):
    """Raised when a video's ocr.json manifest is missing, malformed, or fails validation."""


class InvalidCodeManifestError(VideoDocError):
    """Raised when a video's code extraction manifest is missing, malformed, or fails validation."""


class InvalidChunkManifestError(VideoDocError):
    """Raised when a video's chunk manifest is missing, malformed, or fails validation."""


class InvalidEmbeddingManifestError(VideoDocError):
    """Raised when a video's embedding manifest is missing, malformed, or fails validation."""


class EmbeddingEngineNotSupportedError(VideoDocError):
    """Raised when config.embedding.provider names an embedding provider that is not implemented."""


class InvalidVectorIndexError(VideoDocError):
    """Raised when a local vector index manifest is missing, malformed, or fails validation."""


class VectorIndexUnavailableError(VideoDocError):
    """Raised when retrieval needs a vector index that has not been built yet."""


class VectorIndexNotSupportedError(VideoDocError):
    """Raised when config.retrieval.vector_db names a vector backend that is not implemented."""


class OutlineSourceUnavailableError(VideoDocError):
    """Raised when documentation outline generation has no chunk/source material to use."""


class DocumentationOutlineUnavailableError(VideoDocError):
    """Raised when Markdown section generation needs an outline that is missing or empty."""


class InvalidDocumentationSectionManifestError(VideoDocError):
    """Raised when a generated documentation section source manifest is malformed."""


class DocumentationReviewUnavailableError(VideoDocError):
    """Raised when documentation review has no generated Markdown sections to inspect."""


class OCREngineUnavailableError(VideoDocError):
    """Raised once, up front, when at least one video needs fresh OCR but the 'rapidocr'
    package cannot be imported -- checked a single time per run rather than once per frame.
    A per-video failure to actually instantiate/run
    the engine (e.g. a corrupt cached model file) is a different, per-video error instead --
    see OCRService."""


class OCREngineNotSupportedError(VideoDocError):
    """Raised when config.ocr.engine names an engine OCRService does not actually implement
    (only 'rapidocr' is supported). Checked unconditionally at the start of every run, not
    only when fresh OCR is needed: OCRService always instantiates RapidOCR regardless of this
    setting, so an unnoticed mismatch (e.g. a project's config.yaml still saying the old
    'paddleocr' default) would otherwise silently run the wrong engine and record an
    ocr.json manifest that misreports which engine actually produced its results."""
