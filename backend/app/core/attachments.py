import re
import base64
import logging
import uuid
from pydantic_ai.messages import BinaryContent
from app.schemas.message import ChatAttachment

logger = logging.getLogger("ocin")

# Maximum attachment size: 10MB per image
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024

# Accepted MIME types for images
ACCEPTED_IMAGE_TYPES = [
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
]


def normalize_base64(raw: str) -> bytes:
    """
    Accept either a raw base64 string or a data URL (starts with "data:...;base64,")
    and return decoded bytes.

    Args:
        raw: Base64 string or data URL

    Returns:
        Decoded bytes

    Raises:
        ValueError: If input is invalid base64
    """
    try:
        # Check if it's a data URL (starts with "data:")
        if raw.startswith("data:"):
            # Extract base64 part after "base64,"
            match = re.match(r'data:[^;]*;base64,(.+)', raw)
            if not match:
                raise ValueError("Invalid data URL format")
            base64_part = match.group(1)
            return base64.b64decode(base64_part)
        else:
            # Raw base64 string
            return base64.b64decode(raw)
    except Exception as e:
        raise ValueError(f"Invalid base64 data: {str(e)}")


def build_multimodal_input(text: str, attachments: list[ChatAttachment] | None) -> str | list:
    """
    Build multimodal input for PydanticAI agents.

    If no attachments, return text unchanged (so existing text-only flows are untouched).
    Otherwise return a list: [text, BinaryContent(data=..., media_type=att.type), ...]

    Args:
        text: The user's text input
        attachments: List of ChatAttachment objects or None

    Returns:
        Either a string (text-only) or a list (multimodal)
    """
    # TRACE: Helper entry
    logger.info({
        "event": "attachment_trace",
        "checkpoint": "helper_entry",
        "arg_type": type(attachments).__name__ if attachments else "None",
        "count": len(attachments) if attachments and isinstance(attachments, list) else 0,
    })

    if not attachments:
        return text

    if not isinstance(attachments, list) or len(attachments) == 0:
        return text

    # Build multimodal content list
    # Start with the text part
    content: list[str | BinaryContent] = [text]

    for i, attachment in enumerate(attachments):
        # TRACE: Helper loop iteration - Access Pydantic fields directly with dot notation
        attachment_type = attachment.type if hasattr(attachment, 'type') else None
        attachment_data = attachment.data_base64 if hasattr(attachment, 'data_base64') else None

        logger.info({
            "event": "attachment_trace",
            "checkpoint": "helper_loop_iter",
            "index": i,
            "has_data_base64": attachment_data is not None,
            "type_field": attachment_type,  # Renamed from media_type to match ChatAttachment schema
        })

        if not attachment_type or not attachment_data:
            logger.info({
                "event": "attachment_trace",
                "checkpoint": "helper_skip",
                "reason": "empty_data",
            })
            continue

        # Skip non-image attachments (v1 only supports images)
        if not attachment_type.startswith("image/"):
            logger.warning({
                "event": "attachment_skipped_non_image",
                "type": attachment_type,
            })
            logger.info({
                "event": "attachment_trace",
                "checkpoint": "helper_skip",
                "reason": "non_image",
            })
            continue

        # Skip unsupported image types
        if attachment_type not in ACCEPTED_IMAGE_TYPES:
            logger.warning({
                "event": "attachment_skipped_unsupported_type",
                "type": attachment_type,
                "accepted_types": ACCEPTED_IMAGE_TYPES,
            })
            logger.info({
                "event": "attachment_trace",
                "checkpoint": "helper_skip",
                "reason": "unsupported_type",
            })
            continue

        try:
            # Decode base64 data
            image_bytes = normalize_base64(attachment_data)

            # Log successful decode
            logger.info({
                "event": "attachment_decoded",
                "size_bytes": len(image_bytes),
                "media_type": attachment_type,
            })

            # Enforce size limit
            if len(image_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
                logger.warning({
                    "event": "attachment_too_large",
                    "size_bytes": len(image_bytes),
                    "max_bytes": MAX_ATTACHMENT_SIZE_BYTES,
                })
                logger.info({
                    "event": "attachment_trace",
                    "checkpoint": "helper_skip",
                    "reason": "too_large",
                })
                continue

            # Add binary content to the list
            try:
                binary_content = BinaryContent(data=image_bytes, media_type=attachment_type)
                logger.info({
                    "event": "binary_content_created",
                    "type": type(binary_content).__name__,
                    "data_length": len(binary_content.data),
                    "media_type": binary_content.media_type,
                    "is_bytes_data": isinstance(binary_content.data, bytes),
                })
                content.append(binary_content)
            except Exception as binary_error:
                logger.error({
                    "event": "binary_content_creation_failed",
                    "error": str(binary_error),
                    "media_type": attachment_type,
                })
                logger.info({
                    "event": "attachment_trace",
                    "checkpoint": "helper_skip",
                    "reason": "binary_content_creation_failed",
                })
                continue

        except ValueError as e:
            logger.warning({
                "event": "attachment_decode_failed",
                "error": str(e),
            })
            logger.info({
                "event": "attachment_trace",
                "checkpoint": "helper_skip",
                "reason": "decode_failed",
            })
            continue
        except Exception as e:
            logger.error({
                "event": "attachment_processing_error",
                "error": str(e),
            })
            logger.info({
                "event": "attachment_trace",
                "checkpoint": "helper_skip",
                "reason": "processing_error",
            })
            continue

    # TRACE: Function return
    logger.info({
        "event": "attachment_trace",
        "checkpoint": "helper_return",
        "return_type": type(content).__name__,
        "element_count": len(content) if isinstance(content, list) else 1,
        "first_element_type": type(content[0]).__name__ if isinstance(content, list) else type(content).__name__,
    })

    return content