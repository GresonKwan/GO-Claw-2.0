# -*- coding: utf-8 -*-
# pylint: disable=too-many-return-statements,too-many-branches
# pylint: disable=too-many-statements,too-many-locals
"""Image generation and editing tools."""

import asyncio
import base64
import logging
import mimetypes
import threading
import time
from pathlib import Path
from typing import List

import httpx
from agentscope.message import DataBlock, TextBlock, URLSource
from agentscope.message import ToolResultState
from agentscope.tool import ToolChunk
from qwenpaw.constant import DEFAULT_MEDIA_DIR
from qwenpaw.plugins import get_tool_config
from qwenpaw.plugins.dashscope_credentials import resolve_media_api
from qwenpaw.plugins.media_quota import media_quota

logger = logging.getLogger(__name__)


def _publish_local(path: Path) -> None:
    """Register on v2.1.2 hosts; stay compatible with older hosts."""
    try:
        from qwenpaw.app.deliverables import register_published

        register_published(path)
    except ImportError:
        return


# Thread lock to protect dashscope global base_http_api_url setting
_DASHSCOPE_LOCK = threading.Lock()

_DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1"
_DEFAULT_TIMEOUT = 120.0
_MISSING_API_KEY_MESSAGE = "媒体服务尚未配置，请检查 GO CLAW 全局服务配置"

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_IMAGE_MODEL = "qwen-image-3.0-pro"
_VALID_MODELS_GENERATE = {_IMAGE_MODEL}
_VALID_MODELS_EDIT = {_IMAGE_MODEL}


class _ModelUnavailableError(Exception):
    """The requested model is unavailable on the resolved endpoint."""


_MODEL_UNAVAILABLE_MARKERS = (
    "no available channel",
    "model_not_found",
    "model not found",
    "does not exist",
    "url error",
)

_GENERATE_MODEL_FALLBACKS = ()
_EDIT_MODEL_FALLBACKS = ()


def _is_model_unavailable(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _MODEL_UNAVAILABLE_MARKERS)


def _model_candidates(primary: str, fallbacks: tuple) -> list:
    seen, out = set(), []
    for name in (primary, *fallbacks):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _resolve_image_url(path_or_url: str) -> str:
    """Resolve an image path or URL to a usable string.

    If the input is an HTTP/HTTPS URL, return it as-is.
    If the input is a local file path, read the file and return
    a base64 data URL.

    Args:
        path_or_url: HTTP/HTTPS URL or local file path.

    Returns:
        str: A URL (original URL or base64 data URL).

    Raises:
        FileNotFoundError: If the local file does not exist.
        ValueError: If the file format is not supported.
    """
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url

    path_obj = Path(path_or_url)
    if not path_obj.exists():
        raise FileNotFoundError(
            f"Image file not found: {path_or_url}",
        )
    if not path_obj.is_file():
        raise ValueError(f"Not a file: {path_or_url}")

    ext = path_obj.suffix.lower()
    if ext not in _IMAGE_MIME_TYPES:
        raise ValueError(
            f"Unsupported image format: {ext}. "
            f"Supported: {', '.join(_IMAGE_MIME_TYPES.keys())}",
        )

    mime_type = _IMAGE_MIME_TYPES[ext]
    with open(path_obj, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{image_data}"


def _extract_config(
    tool_config: dict,
    model: str,
) -> tuple[str, str, str, float, str]:
    """Resolve global media credentials plus a fixed internal model.

    Args:
        tool_config: Tool configuration dict.
        model: Internal model selected for this media operation.

    Returns:
        Tuple of (mode, api_key, base_url, timeout, model). ``mode`` is
        "dashscope" (native SDK) or "openai" (OpenAI-compatible relay);
        ``base_url`` matches the resolved mode.
    """
    mode, base_url, api_key = resolve_media_api({})

    timeout_raw = tool_config.get("timeout")
    if timeout_raw is None or float(timeout_raw) <= 0:
        timeout = _DEFAULT_TIMEOUT
    else:
        timeout = float(timeout_raw)

    return mode, api_key, base_url, timeout, model


def _missing_api_key_result() -> ToolChunk:
    """Return the actionable customer-facing missing-key error."""
    return ToolChunk(
        state=ToolResultState.ERROR,
        content=[
            TextBlock(
                type="text",
                text=_MISSING_API_KEY_MESSAGE,
            ),
        ],
    )


def _quota_denied_result(message: str) -> ToolChunk:
    return ToolChunk(
        state=ToolResultState.ERROR,
        content=[TextBlock(type="text", text=message)],
    )


async def _download_image(
    image_url: str,
    save_dir: Path,
    prefix: str,
    timeout: float,
) -> Path:
    """Download image from URL and save to local directory.

    Args:
        image_url: Public URL of the image.
        save_dir: Directory to save the image.
        prefix: Filename prefix.
        timeout: HTTP timeout in seconds.

    Returns:
        Path: Local path of the saved image.

    Raises:
        Exception: If download fails.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    filename = f"{prefix}_{timestamp}.png"
    image_path = save_dir / filename

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", image_url) as response:
            response.raise_for_status()
            chunks = []
            async for chunk in response.aiter_bytes(chunk_size=512 * 1024):
                chunks.append(chunk)
    await asyncio.to_thread(image_path.write_bytes, b"".join(chunks))

    logger.info(f"Image saved to {image_path}")
    return image_path


async def _generate_images_openai(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    size: str = "",
    n: int = 1,
    image: str = "",
    extra_images: List[str] | None = None,
    timeout: float,
) -> List[str]:
    """Call an OpenAI-compatible images/generations endpoint (NewAPI).

    NewAPI does not forward DashScope native paths, so media requests
    must go through the OpenAI-compatible ``POST {base_url}/images/
    generations`` interface. For edit/fusion requests the reference
    image rides along as the ``image`` field (URL or base64 data URI),
    which the configured upstream image service accepts.

    Args:
        base_url: OpenAI-compatible base URL ending in ``/v1``.
        api_key: API key for the gateway.
        model: Model name.
        prompt: Text prompt.
        size: Output size in "width*height" format (optional).
        n: Number of images.
        image: Optional reference image (URL or base64 data URI).
        extra_images: Additional reference images for fusion.
        timeout: HTTP timeout in seconds.

    Returns:
        List of generated image URL strings.

    Raises:
        RuntimeError: If the gateway returns an error or no images.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "n": n,
    }
    if size:
        payload["size"] = size
    if image:
        payload["image"] = image
        if extra_images:
            payload["metadata"] = {"images": list(extra_images)}

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{base_url}/images/generations"
    logger.info(f"OpenAI-compatible image request: model={model}, url={url}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        message = (
            f"OpenAI-compatible image API error: "
            f"{response.status_code} - {response.text[:500]}"
        )
        if _is_model_unavailable(message):
            raise _ModelUnavailableError(message)
        raise RuntimeError(message)

    data = response.json().get("data") or []
    urls = [item.get("url") for item in data if isinstance(item, dict)]
    return [url for url in urls if url]


def _call_multimodal_conversation(
    api_key: str,
    endpoint: str,
    model: str,
    messages: list,
    **kwargs,
):
    """Call DashScope MultiModalConversation with thread-safe setup.

    Args:
        api_key: DashScope API key.
        endpoint: Base HTTP API URL.
        model: Model name.
        messages: Message list for the conversation.
        **kwargs: Additional parameters passed to call().

    Returns:
        SDK response object.
    """
    import dashscope
    from dashscope import MultiModalConversation

    with _DASHSCOPE_LOCK:
        dashscope.base_http_api_url = endpoint
        rsp = MultiModalConversation.call(
            api_key=api_key,
            model=model,
            messages=messages,
            result_format="message",
            stream=False,
            **kwargs,
        )

    return rsp


def _parse_image_urls(response) -> List[str]:
    """Extract image URLs from MultiModalConversation response.

    Args:
        response: SDK response object.

    Returns:
        List of image URL strings.
    """
    urls = []
    choices = getattr(
        getattr(response, "output", None),
        "choices",
        None,
    )
    if not choices:
        return urls
    for choice in choices:
        message = getattr(choice, "message", None)
        if not message:
            continue
        content = getattr(message, "content", None)
        if not content:
            continue
        for item in content:
            if isinstance(item, dict):
                url = item.get("image")
            else:
                url = getattr(item, "image", None)
            if url:
                urls.append(url)
    return urls


async def generate_image(
    prompt: str,
    size: str = "2048*2048",
    n: int = 1,
    negative_prompt: str = "",
    prompt_extend: bool = True,
) -> ToolChunk:
    """Generate images from a text prompt.

    When the configured endpoint points to an OpenAI-compatible relay
    (e.g. a NewAPI gateway, any non-aliyuncs.com host), the request is
    sent through ``POST {root}/v1/images/generations`` instead of the
    native DashScope SDK.

    Args:
        prompt (str):
            Text description of the image to generate.
            Supports Chinese and English prompts.
        size (str, optional):
            Output image size in "width*height" format.
            Recommended sizes: "2048*2048" (1:1, default),
            "2688*1536" (16:9), "1536*2688" (9:16),
            "2368*1728" (4:3).
        n (int, optional):
            Number of images to generate (1-6 for 2.0 series,
            fixed 1 for max/plus). Default: 1.
        negative_prompt (str, optional):
            Describe what to exclude from the image.
        prompt_extend (bool, optional):
            Enable prompt auto-optimization. Default: True.

    Returns:
        ToolChunk: Contains generated images and metadata.
    """
    try:
        tool_config = get_tool_config("generate_image") or {}

        mode, api_key, base_url, timeout, model = _extract_config(
            tool_config,
            model=_IMAGE_MODEL,
        )
        if not api_key:
            return _missing_api_key_result()

        if model not in _VALID_MODELS_GENERATE:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid model '{model}'. "
                            f"Valid options: "
                            f"{', '.join(sorted(_VALID_MODELS_GENERATE))}"
                        ),
                    ),
                ],
            )

        if not 1 <= n <= 6:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid n '{n}'. "
                            f"Must be between 1 and 6."
                        ),
                    ),
                ],
            )

        logger.info(
            f"Generating image with Qwen-Image: "
            f"mode={mode}, model={model}, size={size}, n={n}",
        )

        quota_lease = media_quota.acquire_image(n)
        if not quota_lease.allowed:
            return _quota_denied_result(quota_lease.message)

        candidates = _model_candidates(model, _GENERATE_MODEL_FALLBACKS)
        for candidate in candidates:
            try:
                if mode == "openai":
                    # OpenAI-compatible relay (e.g. NewAPI): POST /v1/images/
                    # generations and read the URL from data[0].
                    image_urls = await _generate_images_openai(
                        base_url=base_url,
                        api_key=api_key,
                        model=candidate,
                        prompt=prompt,
                        size=size or "1024*1024",
                        n=n,
                        timeout=timeout,
                    )
                else:
                    messages = [
                        {
                            "role": "user",
                            "content": [{"text": prompt}],
                        },
                    ]

                    call_kwargs = {
                        "watermark": False,
                        "prompt_extend": prompt_extend,
                        "n": n,
                    }
                    if size:
                        call_kwargs["size"] = size
                    if negative_prompt:
                        call_kwargs["negative_prompt"] = negative_prompt

                    rsp = await asyncio.to_thread(
                        _call_multimodal_conversation,
                        api_key=api_key,
                        endpoint=base_url,
                        model=candidate,
                        messages=messages,
                        **call_kwargs,
                    )

                    if rsp.status_code != 200:
                        error_msg = (
                            f"DashScope API error: {rsp.status_code} - "
                            f"{rsp.code}: {rsp.message}"
                        )
                        if _is_model_unavailable(error_msg):
                            raise _ModelUnavailableError(error_msg)
                        logger.error(error_msg)
                        return ToolChunk(
                            state=ToolResultState.ERROR,
                            content=[
                                TextBlock(
                                    type="text",
                                    text=f"Error: {error_msg}",
                                ),
                            ],
                        )

                    image_urls = _parse_image_urls(rsp)
                break
            except _ModelUnavailableError as exc:
                logger.warning(
                    "configured image model %s is unavailable: %s",
                    candidate,
                    exc,
                )
        else:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text="图片服务当前不可用，请稍后重试或联系管理员。",
                    ),
                ],
            )

        if not image_urls:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: No images returned from API. "
                            "Please try again."
                        ),
                    ),
                ],
            )

        logger.info(
            f"Qwen-Image generated {len(image_urls)} image(s)",
        )

        save_dir = DEFAULT_MEDIA_DIR / "qwen_image"
        content_blocks = []
        saved_paths = []

        for idx, img_url in enumerate(image_urls):
            prefix = f"qwen_image_gen_{idx}"
            try:
                image_path = await _download_image(
                    img_url,
                    save_dir,
                    prefix,
                    timeout,
                )
                _publish_local(image_path)
                saved_paths.append(str(image_path))
                content_blocks.append(
                    DataBlock(
                        source=URLSource(
                            url="file://" + str(image_path),
                            media_type=mimetypes.guess_type(
                                str(image_path),
                            )[0]
                            or "image/*",
                        ),
                    ),
                )
            except Exception as e:
                logger.error(
                    f"Failed to download image {idx}: {e}",
                )
                content_blocks.append(
                    DataBlock(
                        source=URLSource(
                            url=img_url,
                            media_type=mimetypes.guess_type(img_url)[0]
                            or "image/*",
                        ),
                    ),
                )
                saved_paths.append(img_url)

        content_blocks.append(
            TextBlock(
                type="text",
                text=(
                    f"Generated {len(image_urls)} image(s)\n"
                    f"Prompt: {prompt}\n"
                    f"Size: {size}, Count: {n}\n"
                    f"Saved to: {', '.join(saved_paths)}"
                ),
            ),
        )

        return ToolChunk(state=ToolResultState.SUCCESS, content=content_blocks)

    except Exception as e:
        logger.error(
            f"Qwen-Image generation failed: {e}",
            exc_info=True,
        )
        return ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    type="text",
                    text=(f"Error: Image generation failed - {str(e)}"),
                ),
            ],
        )


async def edit_image(
    prompt: str,
    reference_images: List[str],
    size: str = "",
    n: int = 1,
    negative_prompt: str = "",
    prompt_extend: bool = True,
) -> ToolChunk:
    """Edit or fuse images.

    Supports single-image editing (modify content, style transfer,
    text rendering) and multi-image fusion (combine elements from
    multiple images).

    When the configured endpoint points to an OpenAI-compatible relay
    (e.g. a NewAPI gateway, any non-aliyuncs.com host), the reference
    image is sent as the ``image`` field together with the prompt to
    ``POST {root}/v1/images/generations`` instead of the native
    DashScope SDK.

    Args:
        prompt (str):
            Description of the desired edit or fusion.
            When multiple images are provided, use "图一" / "图二"
            (or "image 1" / "image 2" in English) to refer to them.
        reference_images (List[str]):
            List of reference image URLs or local file paths
            (.png/.jpg/.jpeg/.webp). At least 1 image required.
            Each item can be:
            - HTTP/HTTPS URL
            - Local file path (auto-converted to base64)
        size (str, optional):
            Output image size in "width*height" format.
            Leave empty to auto-detect based on input image.
            Example: "1024*1024", "2048*2048".
        n (int, optional):
            Number of output images (1-6 for 2.0/edit-plus,
            fixed 1 for edit-max/edit). Default: 1.
        negative_prompt (str, optional):
            Describe what to exclude from the output.
        prompt_extend (bool, optional):
            Enable prompt auto-optimization. Default: True.

    Returns:
        ToolChunk: Contains edited images and metadata.
    """
    try:
        if not reference_images:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: reference_images is required. "
                            "Please provide at least one image."
                        ),
                    ),
                ],
            )

        tool_config = get_tool_config("edit_image") or {}

        mode, api_key, base_url, timeout, model = _extract_config(
            tool_config,
            model=_IMAGE_MODEL,
        )
        if not api_key:
            return _missing_api_key_result()

        if model not in _VALID_MODELS_EDIT:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid model '{model}'. "
                            f"Valid options: "
                            f"{', '.join(sorted(_VALID_MODELS_EDIT))}"
                        ),
                    ),
                ],
            )

        if not 1 <= n <= 6:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid n '{n}'. "
                            f"Must be between 1 and 6."
                        ),
                    ),
                ],
            )

        # Resolve reference images first (shared by both API modes)
        resolved_images = []
        for img_input in reference_images:
            try:
                resolved = _resolve_image_url(img_input)
            except (FileNotFoundError, ValueError) as e:
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                f"Error: reference_images contains invalid "
                                f"entry '{img_input}' - {str(e)}"
                            ),
                        ),
                    ],
                )
            resolved_images.append(resolved)

        logger.info(
            f"Editing image with Qwen-Image: "
            f"mode={mode}, model={model}, "
            f"reference_images={len(reference_images)}, n={n}",
        )

        quota_lease = media_quota.acquire_image(n)
        if not quota_lease.allowed:
            return _quota_denied_result(quota_lease.message)

        candidates = _model_candidates(model, _EDIT_MODEL_FALLBACKS)
        for candidate in candidates:
            try:
                if mode == "openai":
                    # OpenAI-compatible relay (e.g. NewAPI): send the reference
                    # image(s) with the prompt to /v1/images/generations.
                    # The upstream image service accepts reference images
                    # via ``image``; extras go to ``metadata.images``.
                    image_urls = await _generate_images_openai(
                        base_url=base_url,
                        api_key=api_key,
                        model=candidate,
                        prompt=prompt,
                        size=size,
                        n=n,
                        image=resolved_images[0],
                        extra_images=resolved_images[1:] or None,
                        timeout=timeout,
                    )
                else:
                    # Build message content: images first, then prompt text
                    content = [{"image": url} for url in resolved_images]
                    content.append({"text": prompt})

                    messages = [{"role": "user", "content": content}]

                    call_kwargs = {
                        "watermark": False,
                        "prompt_extend": prompt_extend,
                        "n": n,
                    }
                    if size:
                        call_kwargs["size"] = size
                    if negative_prompt:
                        call_kwargs["negative_prompt"] = negative_prompt

                    rsp = await asyncio.to_thread(
                        _call_multimodal_conversation,
                        api_key=api_key,
                        endpoint=base_url,
                        model=candidate,
                        messages=messages,
                        **call_kwargs,
                    )

                    if rsp.status_code != 200:
                        error_msg = (
                            f"DashScope API error: {rsp.status_code} - "
                            f"{rsp.code}: {rsp.message}"
                        )
                        if _is_model_unavailable(error_msg):
                            raise _ModelUnavailableError(error_msg)
                        logger.error(error_msg)
                        return ToolChunk(
                            state=ToolResultState.ERROR,
                            content=[
                                TextBlock(
                                    type="text",
                                    text=f"Error: {error_msg}",
                                ),
                            ],
                        )

                    image_urls = _parse_image_urls(rsp)
                break
            except _ModelUnavailableError as exc:
                logger.warning(
                    "configured image edit model %s is unavailable: %s",
                    candidate,
                    exc,
                )
        else:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text="图片编辑服务当前不可用，请稍后重试或联系管理员。",
                    ),
                ],
            )

        if not image_urls:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: No images returned from API. "
                            "Please try again."
                        ),
                    ),
                ],
            )

        logger.info(
            f"Qwen-Image edit produced {len(image_urls)} image(s)",
        )

        save_dir = DEFAULT_MEDIA_DIR / "qwen_image"
        content_blocks = []
        saved_paths = []

        for idx, img_url in enumerate(image_urls):
            prefix = f"qwen_image_edit_{idx}"
            try:
                image_path = await _download_image(
                    img_url,
                    save_dir,
                    prefix,
                    timeout,
                )
                _publish_local(image_path)
                saved_paths.append(str(image_path))
                content_blocks.append(
                    DataBlock(
                        source=URLSource(
                            url="file://" + str(image_path),
                            media_type=mimetypes.guess_type(
                                str(image_path),
                            )[0]
                            or "image/*",
                        ),
                    ),
                )
            except Exception as e:
                logger.error(
                    f"Failed to download image {idx}: {e}",
                )
                content_blocks.append(
                    DataBlock(
                        source=URLSource(
                            url=img_url,
                            media_type=mimetypes.guess_type(img_url)[0]
                            or "image/*",
                        ),
                    ),
                )
                saved_paths.append(img_url)

        content_blocks.append(
            TextBlock(
                type="text",
                text=(
                    f"Edited {len(image_urls)} image(s)\n"
                    f"Prompt: {prompt}\n"
                    f"Reference images: {len(reference_images)}\n"
                    f"Saved to: {', '.join(saved_paths)}"
                ),
            ),
        )

        return ToolChunk(state=ToolResultState.SUCCESS, content=content_blocks)

    except Exception as e:
        logger.error(
            f"Qwen-Image edit failed: {e}",
            exc_info=True,
        )
        return ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Image editing failed - {str(e)}",
                ),
            ],
        )
