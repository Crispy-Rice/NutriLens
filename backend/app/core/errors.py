"""Application errors that carry a user-readable message.

Rule: anything reaching the client must be understandable without a stack
trace. Internal details go to the log; the response carries code + message +
an actionable hint.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for expected, user-facing failures."""

    code = "internal_error"
    status = 500
    message = "服务出现意外错误，请稍后重试。"
    hint: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        hint: str | None = None,
        code: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        if hint is not None:
            self.hint = hint
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status


class InvalidImageError(AppError):
    code = "invalid_image"
    status = 400
    message = "这张图片无法识别，可能已损坏或不是有效的图片文件。"
    hint = "请换一张照片，或重新拍摄后再试。"


class UnsupportedFormatError(AppError):
    code = "unsupported_format"
    status = 415
    message = "暂不支持这种图片格式。"
    hint = "请上传 JPG、PNG 或 WebP 格式的图片。"


class FileTooLargeError(AppError):
    code = "file_too_large"
    status = 413
    message = "图片文件太大。"
    hint = "请压缩后重试，或直接在手机上选择较小的照片。"


class ImageTooLargeError(AppError):
    code = "image_dimensions_too_large"
    status = 413
    message = "图片分辨率过高，无法处理。"
    hint = "请先裁剪或缩小图片后再上传。"


class TooManyImagesError(AppError):
    code = "too_many_images"
    status = 400
    message = "一次上传的图片太多了。"
    hint = "请减少到规定张数以内再试。"


class TotalUploadTooLargeError(AppError):
    code = "total_upload_too_large"
    status = 413
    message = "这批图片的总大小超过上限。"
    hint = "请减少张数，或先压缩图片再上传。"


class EmptyUploadError(AppError):
    code = "empty_upload"
    status = 400
    message = "没有收到图片文件。"
    hint = "请选择一张图片后再点击分析。"


class InvalidModeError(AppError):
    code = "invalid_mode"
    status = 400
    message = "分析模式不正确。"
    hint = "请选择「快速识别」或「详细分析」。"


class LLMError(AppError):
    code = "llm_error"
    status = 502
    message = "识别服务暂时不可用。"
    hint = "请稍后重试。如果持续失败，请检查后端 .env 中的模型配置。"


class LLMTimeoutError(AppError):
    code = "llm_timeout"
    status = 504
    message = "识别超时，模型响应时间过长。"
    hint = "请重试，或改用「快速识别」模式以缩短耗时。"


class LLMNotConfiguredError(AppError):
    code = "llm_not_configured"
    status = 503
    message = "识别服务尚未配置。"
    hint = "请在 backend/.env 中填写 LLM_API_KEY，或设置 LLM_PROVIDER=mock 使用离线演示模式。"


class InvalidProfileError(AppError):
    code = "invalid_profile"
    status = 400
    message = "饮食画像的数据格式不正确。"
    # Deliberately generic: the error must not echo the profile back, and must
    # not end up in a log.
    hint = "请回到「画像」页面检查后重新保存。"


class NotFoundError(AppError):
    code = "not_found"
    status = 404
    message = "未找到该记录。"
    hint = "它可能已被删除。"
