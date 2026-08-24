# -*- coding: utf-8 -*-
# pylint: disable=too-many-return-statements,too-many-branches
# pylint: disable=too-many-statements,too-many-locals
"""Wan 2.7 video generation tools."""

import asyncio
import base64
import logging
import mimetypes
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import List, Optional

import httpx
from agentscope.message import DataBlock, TextBlock, URLSource
from agentscope.message import ToolResultState
from agentscope.tool import ToolChunk
from qwenpaw.constant import DEFAULT_MEDIA_DIR
from qwenpaw.plugins import get_tool_config
from qwenpaw.plugins.dashscope_credentials import resolve_media_api
from qwenpaw.plugins.media_quota import media_quota

logger = logging.getLogger(__name__)

# Thread lock to protect dashscope global base_http_api_url setting
_DASHSCOPE_LOCK = threading.Lock()

_DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1"
_DEFAULT_TIMEOUT = 600.0
_MISSING_API_KEY_MESSAGE = "请在 GO CLAW 批次凭证或当前数字员工工具配置中填写 DashScope API Key"
_TEXT_TO_VIDEO_MODEL = "wan2.7-t2v"
_IMAGE_TO_VIDEO_MODEL = "wan2.7-i2v"
_REFERENCE_TO_VIDEO_MODEL = "wan2.7-r2v"

# Polling interval (seconds) for OpenAI-compatible video tasks
_OPENAI_POLL_INTERVAL = 5.0


class _ModelUnavailableError(Exception):
    """The requested model is unavailable on the resolved endpoint."""


_MODEL_UNAVAILABLE_MARKERS = (
    "no available channel",
    "model_not_found",
    "model not found",
    "does not exist",
    "url error",
)

_T2V_MODEL_FALLBACKS = ("wan2.7-t2v",)
_I2V_MODEL_FALLBACKS = ("wan2.7-i2v",)
_R2V_MODEL_FALLBACKS = ("wan2.7-r2v",)


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


_VALID_RESOLUTIONS = {"720P", "1080P"}
_VALID_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4"}

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _resolve_image_url(path_or_url: str) -> str:
    """Resolve an image path or URL to a usable URL.

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
    default_model: str,
) -> tuple[str, str, str, float, str]:
    """Extract mode, api_key, base_url, timeout and model from config.

    Args:
        tool_config: Tool configuration dict.
        default_model: Fallback model name when not set in config.

    Returns:
        Tuple of (mode, api_key, base_url, timeout, model). ``mode`` is
        "dashscope" (native SDK) or "openai" (OpenAI-compatible relay);
        ``base_url`` matches the resolved mode.
    """
    mode, base_url, api_key = resolve_media_api(tool_config)

    timeout_raw = tool_config.get("timeout")
    if timeout_raw is None or float(timeout_raw) <= 0:
        timeout = _DEFAULT_TIMEOUT
    else:
        timeout = float(timeout_raw)

    model = tool_config.get("model", "") or default_model

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


async def _download_video(
    video_url: str,
    save_dir: Path,
    prefix: str,
    timeout: float,
) -> Path:
    """Download video from URL and save to local directory.

    Args:
        video_url: Public URL of the video.
        save_dir: Directory to save the video.
        prefix: Filename prefix.
        timeout: HTTP timeout in seconds.

    Returns:
        Path: Local path of the saved video.

    Raises:
        Exception: If download fails.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    filename = f"{prefix}_{timestamp}.mp4"
    video_path = save_dir / filename

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", video_url) as response:
            response.raise_for_status()
            chunks = []
            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                chunks.append(chunk)
    await asyncio.to_thread(video_path.write_bytes, b"".join(chunks))

    logger.info(f"Video saved to {video_path}")
    return video_path


async def _run_video_task_openai(
    base_url: str,
    api_key: str,
    payload: dict,
    timeout: float,
) -> str:
    """Create and poll an OpenAI-compatible video task (NewAPI relay).

    NewAPI does not forward DashScope native paths, so video requests
    go through ``POST {base_url}/video/generations`` followed by
    polling ``GET {base_url}/video/generations/{task_id}`` until the
    task succeeds, fails, or the total timeout budget runs out.

    Args:
        base_url: OpenAI-compatible base URL ending in ``/v1``.
        api_key: API key for the gateway.
        payload: JSON body for the create request.
        timeout: Total timeout budget in seconds.

    Returns:
        The result video URL.

    Raises:
        RuntimeError: If the gateway or the task reports an error.
        TimeoutError: If the task does not finish within ``timeout``.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    create_url = f"{base_url}/video/generations"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            create_url,
            json=payload,
            headers=headers,
        )
        if response.status_code != 200:
            message = (
                f"OpenAI-compatible video API error: "
                f"{response.status_code} - {response.text[:500]}"
            )
            if _is_model_unavailable(message):
                raise _ModelUnavailableError(message)
            raise RuntimeError(message)
        body = response.json()
        task_id = body.get("task_id") or body.get("id")
        if not task_id:
            raise RuntimeError(
                "OpenAI-compatible video API did not return a task id: "
                f"{body}",
            )

        poll_url = f"{create_url}/{task_id}"
        deadline = time.monotonic() + timeout
        while True:
            poll = await client.get(poll_url, headers=headers)
            if poll.status_code != 200:
                raise RuntimeError(
                    f"OpenAI-compatible video poll error: "
                    f"{poll.status_code} - {poll.text[:500]}",
                )
            data = poll.json().get("data") or {}
            status = str(data.get("status") or "").upper()
            if status == "SUCCESS":
                result_url = data.get("result_url")
                if not result_url:
                    raise RuntimeError(
                        "OpenAI-compatible video task succeeded but "
                        "returned no result_url",
                    )
                return result_url
            if status == "FAILED":
                raise RuntimeError(
                    f"Video generation failed: "
                    f"{data.get('fail_reason') or 'unknown reason'}",
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Video generation timed out after {timeout}s "
                    f"(task {task_id})",
                )
            await asyncio.sleep(_OPENAI_POLL_INTERVAL)


def _call_video_synthesis(
    api_key: str,
    endpoint: str,
    model: str,
    prompt: str,
    **kwargs,
):
    """Call DashScope VideoSynthesis with thread-safe endpoint setup.

    Args:
        api_key: DashScope API key.
        endpoint: Base HTTP API URL.
        model: Model name.
        prompt: Text prompt.
        **kwargs: Additional parameters passed to VideoSynthesis.call().

    Returns:
        SDK response object.
    """
    import dashscope
    from dashscope import VideoSynthesis

    with _DASHSCOPE_LOCK:
        dashscope.base_http_api_url = endpoint
        rsp = VideoSynthesis.call(
            api_key=api_key,
            model=model,
            prompt=prompt,
            **kwargs,
        )

    return rsp


async def text_to_video_wan(
    prompt: str,
    resolution: str = "720P",
    ratio: str = "16:9",
    duration: int = 5,
    negative_prompt: str = "",
    audio_url: str = "",
    prompt_extend: bool = True,
) -> ToolChunk:
    """Generate a video from a text prompt using Wan 2.7.

    Uses Alibaba Cloud's wan2.7-t2v model to create videos from
    natural language descriptions. Supports multi-shot narratives,
    custom audio, and negative prompts.

    Args:
        prompt (str):
            Text description of the video to generate.
            Supports Chinese and English, up to 5000 characters.
            Use timestamps for multi-shot control, e.g.:
            "第1个镜头[0-3秒] 全景：..."
        resolution (str, optional):
            Video resolution. "720P" or "1080P". Default: "720P".
        ratio (str, optional):
            Aspect ratio. "16:9", "9:16", "1:1", "4:3", "3:4".
            Default: "16:9".
        duration (int, optional):
            Video duration in seconds, range [2, 15]. Default: 5.
        negative_prompt (str, optional):
            Describe what to exclude from the video.
        audio_url (str, optional):
            Public HTTP/HTTPS URL of background audio (wav/mp3).
            If not provided, model auto-generates audio.
        prompt_extend (bool, optional):
            Enable prompt auto-optimization. Default: True.

    Returns:
        ToolChunk: Contains local video path and metadata.
    """
    video_lease = None
    try:
        tool_config = get_tool_config("text_to_video_wan") or {}

        mode, api_key, base_url, timeout, model = _extract_config(
            tool_config,
            default_model=_TEXT_TO_VIDEO_MODEL,
        )
        if not api_key:
            return _missing_api_key_result()

        if resolution not in _VALID_RESOLUTIONS:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid resolution '{resolution}'. "
                            f"Must be one of: "
                            f"{', '.join(sorted(_VALID_RESOLUTIONS))}"
                        ),
                    ),
                ],
            )

        if ratio not in _VALID_RATIOS:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid ratio '{ratio}'. "
                            f"Must be one of: "
                            f"{', '.join(sorted(_VALID_RATIOS))}"
                        ),
                    ),
                ],
            )

        if not 2 <= duration <= 15:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid duration '{duration}'. "
                            f"Must be between 2 and 15 seconds."
                        ),
                    ),
                ],
            )

        logger.info(
            f"Generating text-to-video: mode={mode}, model={model}, "
            f"resolution={resolution}, ratio={ratio}, "
            f"duration={duration}s",
        )

        video_lease = media_quota.acquire_video()
        if not video_lease.allowed:
            return _quota_denied_result(video_lease.message)

        candidates = _model_candidates(model, _T2V_MODEL_FALLBACKS)
        fallback_note = ""
        last_unavailable = ""
        for candidate in candidates:
            try:
                if mode == "openai":
                    # OpenAI-compatible relay (e.g. NewAPI): vendor parameters
                    # ride inside the metadata object.
                    metadata = {
                        "resolution": resolution,
                        "ratio": ratio,
                        "prompt_extend": prompt_extend,
                    }
                    if negative_prompt:
                        metadata["negative_prompt"] = negative_prompt
                    if audio_url:
                        metadata["audio_url"] = audio_url
                    payload = {
                        "model": candidate,
                        "prompt": prompt,
                        "duration": duration,
                        "metadata": metadata,
                    }
                    video_url = await _run_video_task_openai(
                        base_url,
                        api_key,
                        payload,
                        timeout,
                    )
                else:
                    kwargs = {
                        "resolution": resolution,
                        "ratio": ratio,
                        "duration": duration,
                        "prompt_extend": prompt_extend,
                    }
                    if negative_prompt:
                        kwargs["negative_prompt"] = negative_prompt
                    if audio_url:
                        kwargs["audio_url"] = audio_url

                    rsp = await asyncio.to_thread(
                        _call_video_synthesis,
                        api_key=api_key,
                        endpoint=base_url,
                        model=candidate,
                        prompt=prompt,
                        **kwargs,
                    )

                    if rsp.status_code != HTTPStatus.OK:
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

                    video_url = rsp.output.video_url
                if candidate != model:
                    fallback_note = f"（默认模型 {model} 不可用，已自动改用 {candidate}）"
                break
            except _ModelUnavailableError as exc:
                last_unavailable = str(exc)
                logger.warning(
                    "video model %s unavailable, trying next fallback: %s",
                    candidate,
                    exc,
                )
        else:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: 所有候选视频模型均不可用："
                            f"{'、'.join(candidates)}。"
                            f"最后一次错误：{last_unavailable}"
                        ),
                    ),
                ],
            )

        logger.info(
            f"Text-to-video generated, downloading: {video_url}",
        )

        save_dir = DEFAULT_MEDIA_DIR / "wan27"
        video_path = await _download_video(
            video_url,
            save_dir,
            "t2v",
            timeout,
        )

        return ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                DataBlock(
                    source=URLSource(
                        url="file://" + str(video_path),
                        media_type=mimetypes.guess_type(str(video_path))[0]
                        or "video/*",
                    ),
                ),
                TextBlock(
                    type="text",
                    text=(
                        f"Video generated successfully using "
                        f"Wan 2.7{fallback_note}\n"
                        f"Model: {model}\n"
                        f"Prompt: {prompt}\n"
                        f"Resolution: {resolution}, Ratio: {ratio}, "
                        f"Duration: {duration}s\n"
                        f"Saved to: {video_path}\n"
                        f"Original URL (valid 24h): {video_url}"
                    ),
                ),
            ],
        )
    except Exception as e:
        logger.error(
            f"Text-to-video generation failed: {e}",
            exc_info=True,
        )
        return ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Text-to-video generation failed - {str(e)}",
                ),
            ],
        )
    finally:
        if video_lease is not None and video_lease.allowed:
            video_lease.release()


async def image_to_video_wan(
    prompt: str,
    first_frame_url: str,
    last_frame_url: str = "",
    driving_audio_url: str = "",
    first_clip_url: str = "",
    resolution: str = "720P",
    duration: int = 5,
    prompt_extend: bool = True,
) -> ToolChunk:
    """Generate a video from images using Wan 2.7.

    Supports four modes based on the combination of optional inputs:
    - First-frame: provide only first_frame_url (+ optional audio)
    - First-last-frame: provide first_frame_url + last_frame_url
    - Audio-driven: provide first_frame_url + driving_audio_url
    - Video-continuation: provide first_clip_url (ignores first_frame_url)

    Args:
        prompt (str):
            Text description of the video content.
        first_frame_url (str):
            URL or local file path of the first frame image.
            Supports HTTP/HTTPS URLs and local image files
            (.png/.jpg/.jpeg/.webp).
        last_frame_url (str, optional):
            URL or local file path of the last frame image.
            When provided, creates a first-to-last-frame video.
        driving_audio_url (str, optional):
            Public HTTP/HTTPS URL of a driving audio file (wav/mp3,
            2-30 seconds). Local audio files are not supported.
        first_clip_url (str, optional):
            Public HTTP/HTTPS URL of a video clip to continue.
            When provided, generates a continuation of the clip.
            Local video files are not supported.
        resolution (str, optional):
            Video resolution. "720P" or "1080P". Default: "720P".
        duration (int, optional):
            Video duration in seconds, range [2, 15]. Default: 5.
        prompt_extend (bool, optional):
            Enable prompt auto-optimization. Default: True.

    Returns:
        ToolChunk: Contains local video path and metadata.
    """
    video_lease = None
    try:
        tool_config = get_tool_config("image_to_video_wan") or {}

        mode, api_key, base_url, timeout, model = _extract_config(
            tool_config,
            default_model=_IMAGE_TO_VIDEO_MODEL,
        )
        if not api_key:
            return _missing_api_key_result()

        if resolution not in _VALID_RESOLUTIONS:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid resolution '{resolution}'. "
                            f"Must be one of: "
                            f"{', '.join(sorted(_VALID_RESOLUTIONS))}"
                        ),
                    ),
                ],
            )

        if not 2 <= duration <= 15:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid duration '{duration}'. "
                            f"Must be between 2 and 15 seconds."
                        ),
                    ),
                ],
            )

        # Build media array based on input combination
        media: List[dict] = []

        if first_clip_url:
            # Video continuation mode
            if not first_clip_url.startswith(
                ("http://", "https://"),
            ):
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                "Error: first_clip_url must be a public "
                                "HTTP/HTTPS URL. Local video files are "
                                "not supported."
                            ),
                        ),
                    ],
                )
            media.append(
                {"type": "first_clip", "url": first_clip_url},
            )
        else:
            if not first_frame_url:
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                "Error: first_frame_url is required "
                                "(unless using video-continuation mode "
                                "with first_clip_url)."
                            ),
                        ),
                    ],
                )

            try:
                resolved_first = _resolve_image_url(first_frame_url)
            except (FileNotFoundError, ValueError) as e:
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=f"Error: first_frame_url - {str(e)}",
                        ),
                    ],
                )

            media.append(
                {"type": "first_frame", "url": resolved_first},
            )

            if last_frame_url:
                try:
                    resolved_last = _resolve_image_url(
                        last_frame_url,
                    )
                except (FileNotFoundError, ValueError) as e:
                    return ToolChunk(
                        state=ToolResultState.ERROR,
                        content=[
                            TextBlock(
                                type="text",
                                text=f"Error: last_frame_url - {str(e)}",
                            ),
                        ],
                    )
                media.append(
                    {"type": "last_frame", "url": resolved_last},
                )
            elif driving_audio_url:
                if not driving_audio_url.startswith(
                    ("http://", "https://"),
                ):
                    return ToolChunk(
                        state=ToolResultState.ERROR,
                        content=[
                            TextBlock(
                                type="text",
                                text=(
                                    "Error: driving_audio_url must be a "
                                    "public HTTP/HTTPS URL. Local audio "
                                    "files are not supported."
                                ),
                            ),
                        ],
                    )
                media.append(
                    {
                        "type": "driving_audio",
                        "url": driving_audio_url,
                    },
                )

        mode_desc = (
            "video-continuation"
            if first_clip_url
            else (
                "first-last-frame"
                if last_frame_url
                else "audio-driven"
                if driving_audio_url
                else "first-frame"
            )
        )

        logger.info(
            f"Generating image-to-video: api_mode={mode}, "
            f"mode={mode_desc}, model={model}, "
            f"resolution={resolution}, duration={duration}s",
        )

        video_lease = media_quota.acquire_video()
        if not video_lease.allowed:
            return _quota_denied_result(video_lease.message)

        candidates = _model_candidates(model, _I2V_MODEL_FALLBACKS)
        fallback_note = ""
        last_unavailable = ""
        for candidate in candidates:
            try:
                if mode == "openai":
                    # OpenAI-compatible relay (e.g. NewAPI): the first frame is
                    # sent as the top-level ``image`` field, extra media ride
                    # inside the metadata object.
                    metadata = {
                        "resolution": resolution,
                        "prompt_extend": prompt_extend,
                    }
                    image_field = ""
                    for item in media:
                        if item["type"] == "first_frame" and not image_field:
                            image_field = item["url"]
                        elif item["type"] == "last_frame":
                            metadata["last_frame"] = item["url"]
                        elif item["type"] == "driving_audio":
                            metadata["audio_url"] = item["url"]
                        elif item["type"] == "first_clip":
                            metadata["first_clip"] = item["url"]
                    payload = {
                        "model": candidate,
                        "prompt": prompt,
                        "duration": duration,
                        "metadata": metadata,
                    }
                    if image_field:
                        payload["image"] = image_field
                    video_url = await _run_video_task_openai(
                        base_url,
                        api_key,
                        payload,
                        timeout,
                    )
                else:
                    rsp = await asyncio.to_thread(
                        _call_video_synthesis,
                        api_key=api_key,
                        endpoint=base_url,
                        model=candidate,
                        prompt=prompt,
                        media=media,
                        resolution=resolution,
                        duration=duration,
                        prompt_extend=prompt_extend,
                    )

                    if rsp.status_code != HTTPStatus.OK:
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

                    video_url = rsp.output.video_url
                if candidate != model:
                    fallback_note = f"（默认模型 {model} 不可用，已自动改用 {candidate}）"
                break
            except _ModelUnavailableError as exc:
                last_unavailable = str(exc)
                logger.warning(
                    "video model %s unavailable, trying next fallback: %s",
                    candidate,
                    exc,
                )
        else:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: 所有候选视频模型均不可用："
                            f"{'、'.join(candidates)}。"
                            f"最后一次错误：{last_unavailable}"
                        ),
                    ),
                ],
            )

        logger.info(
            f"Image-to-video generated, downloading: {video_url}",
        )

        save_dir = DEFAULT_MEDIA_DIR / "wan27"
        video_path = await _download_video(
            video_url,
            save_dir,
            "i2v",
            timeout,
        )

        return ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                DataBlock(
                    source=URLSource(
                        url="file://" + str(video_path),
                        media_type=mimetypes.guess_type(str(video_path))[0]
                        or "video/*",
                    ),
                ),
                TextBlock(
                    type="text",
                    text=(
                        f"Video generated successfully using "
                        f"Wan 2.7{fallback_note}\n"
                        f"Model: {model}\n"
                        f"Mode: {mode_desc}\n"
                        f"Prompt: {prompt}\n"
                        f"Resolution: {resolution}, Duration: {duration}s\n"
                        f"Saved to: {video_path}\n"
                        f"Original URL (valid 24h): {video_url}"
                    ),
                ),
            ],
        )
    except Exception as e:
        logger.error(
            f"Image-to-video generation failed: {e}",
            exc_info=True,
        )
        return ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    type="text",
                    text=(
                        f"Error: Image-to-video generation failed - {str(e)}"
                    ),
                ),
            ],
        )
    finally:
        if video_lease is not None and video_lease.allowed:
            video_lease.release()


async def reference_to_video_wan(
    prompt: str,
    reference_images: List[str],
    reference_videos: Optional[List[str]] = None,
    first_frame_url: str = "",
    resolution: str = "720P",
    ratio: str = "16:9",
    duration: int = 5,
    prompt_extend: bool = True,
) -> ToolChunk:
    """Generate a video with character/object references using Wan 2.7.

    Uses reference images and/or videos to maintain character
    consistency in the generated video. In the prompt, reference
    images as "图1", "图2", etc. and reference videos as "视频1",
    "视频2", etc. (or "Image 1", "Video 1" in English prompts).

    Args:
        prompt (str):
            Text description of the video. Use "图1", "图2" to
            refer to reference images, "视频1", "视频2" to refer
            to reference videos (in order of the lists provided).
            Example: "图1在图2的房间里玩耍，视频1走进来"
        reference_images (List[str]):
            List of reference image URLs or local file paths
            (.png/.jpg/.jpeg/.webp). Minimum 1 image.
            These become 图1, 图2, ... in the prompt.
        reference_videos (List[str], optional):
            List of reference video public HTTP/HTTPS URLs.
            Local video files are not supported.
            These become 视频1, 视频2, ... in the prompt.
        first_frame_url (str, optional):
            URL or local file path of an additional first-frame
            image to control the opening scene.
        resolution (str, optional):
            Video resolution. "720P" or "1080P". Default: "720P".
        ratio (str, optional):
            Aspect ratio. "16:9", "9:16", "1:1", "4:3", "3:4".
            Default: "16:9".
        duration (int, optional):
            Video duration in seconds, range [2, 15]. Default: 5.
        prompt_extend (bool, optional):
            Enable prompt auto-optimization. Default: True.

    Returns:
        ToolChunk: Contains local video path and metadata.
    """
    if reference_videos is None:
        reference_videos = []

    video_lease = None
    try:
        tool_config = get_tool_config("reference_to_video_wan") or {}

        mode, api_key, base_url, timeout, model = _extract_config(
            tool_config,
            default_model=_REFERENCE_TO_VIDEO_MODEL,
        )
        if not api_key:
            return _missing_api_key_result()

        if not reference_images:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: reference_images is required. "
                            "Please provide at least one reference image."
                        ),
                    ),
                ],
            )

        if resolution not in _VALID_RESOLUTIONS:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid resolution '{resolution}'. "
                            f"Must be one of: "
                            f"{', '.join(sorted(_VALID_RESOLUTIONS))}"
                        ),
                    ),
                ],
            )

        if ratio not in _VALID_RATIOS:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid ratio '{ratio}'. "
                            f"Must be one of: "
                            f"{', '.join(sorted(_VALID_RATIOS))}"
                        ),
                    ),
                ],
            )

        if not 2 <= duration <= 15:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Invalid duration '{duration}'. "
                            f"Must be between 2 and 15 seconds."
                        ),
                    ),
                ],
            )

        # Build media array: reference_images first, then videos,
        # then optional first_frame
        media: List[dict] = []

        for img_path in reference_images:
            try:
                resolved = _resolve_image_url(img_path)
            except (FileNotFoundError, ValueError) as e:
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                f"Error: reference_images contains invalid "
                                f"entry '{img_path}' - {str(e)}"
                            ),
                        ),
                    ],
                )
            media.append(
                {"type": "reference_image", "url": resolved},
            )

        for vid_url in reference_videos:
            if not vid_url.startswith(("http://", "https://")):
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                f"Error: reference_videos entry '{vid_url}' "
                                f"must be a public HTTP/HTTPS URL. Local "
                                f"video files are not supported."
                            ),
                        ),
                    ],
                )
            media.append(
                {"type": "reference_video", "url": vid_url},
            )

        if first_frame_url:
            try:
                resolved_ff = _resolve_image_url(first_frame_url)
            except (FileNotFoundError, ValueError) as e:
                return ToolChunk(
                    state=ToolResultState.ERROR,
                    content=[
                        TextBlock(
                            type="text",
                            text=f"Error: first_frame_url - {str(e)}",
                        ),
                    ],
                )
            media.append(
                {"type": "first_frame", "url": resolved_ff},
            )

        logger.info(
            f"Generating reference-to-video: "
            f"api_mode={mode}, model={model}, "
            f"reference_images={len(reference_images)}, "
            f"reference_videos={len(reference_videos)}, "
            f"resolution={resolution}, ratio={ratio}, "
            f"duration={duration}s",
        )

        video_lease = media_quota.acquire_video()
        if not video_lease.allowed:
            return _quota_denied_result(video_lease.message)

        candidates = _model_candidates(model, _R2V_MODEL_FALLBACKS)
        fallback_note = ""
        last_unavailable = ""
        for candidate in candidates:
            try:
                if mode == "openai":
                    # OpenAI-compatible relay (e.g. NewAPI): the first ref
                    # image goes to the top-level ``image`` field, remaining
                    # references ride inside ``metadata.images`` / ``videos``.
                    ref_images = [
                        item["url"]
                        for item in media
                        if item["type"] == "reference_image"
                    ]
                    ref_videos = [
                        item["url"]
                        for item in media
                        if item["type"] == "reference_video"
                    ]
                    first_frames = [
                        item["url"]
                        for item in media
                        if item["type"] == "first_frame"
                    ]
                    metadata = {
                        "resolution": resolution,
                        "ratio": ratio,
                        "prompt_extend": prompt_extend,
                    }
                    if len(ref_images) > 1:
                        metadata["images"] = ref_images[1:]
                    if ref_videos:
                        metadata["videos"] = ref_videos
                    if first_frames:
                        metadata["first_frame"] = first_frames[0]
                    payload = {
                        "model": candidate,
                        "prompt": prompt,
                        "image": ref_images[0],
                        "duration": duration,
                        "metadata": metadata,
                    }
                    video_url = await _run_video_task_openai(
                        base_url,
                        api_key,
                        payload,
                        timeout,
                    )
                else:
                    rsp = await asyncio.to_thread(
                        _call_video_synthesis,
                        api_key=api_key,
                        endpoint=base_url,
                        model=candidate,
                        prompt=prompt,
                        media=media,
                        resolution=resolution,
                        ratio=ratio,
                        duration=duration,
                        prompt_extend=prompt_extend,
                    )

                    if rsp.status_code != HTTPStatus.OK:
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

                    video_url = rsp.output.video_url
                if candidate != model:
                    fallback_note = f"（默认模型 {model} 不可用，已自动改用 {candidate}）"
                break
            except _ModelUnavailableError as exc:
                last_unavailable = str(exc)
                logger.warning(
                    "video model %s unavailable, trying next fallback: %s",
                    candidate,
                    exc,
                )
        else:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: 所有候选视频模型均不可用："
                            f"{'、'.join(candidates)}。"
                            f"最后一次错误：{last_unavailable}"
                        ),
                    ),
                ],
            )

        logger.info(
            f"Reference-to-video generated, downloading: " f"{video_url}",
        )

        save_dir = DEFAULT_MEDIA_DIR / "wan27"
        video_path = await _download_video(
            video_url,
            save_dir,
            "r2v",
            timeout,
        )

        return ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                DataBlock(
                    source=URLSource(
                        url="file://" + str(video_path),
                        media_type=mimetypes.guess_type(str(video_path))[0]
                        or "video/*",
                    ),
                ),
                TextBlock(
                    type="text",
                    text=(
                        f"Video generated successfully using "
                        f"Wan 2.7{fallback_note}\n"
                        f"Model: {model}\n"
                        f"Reference images: {len(reference_images)}, "
                        f"Reference videos: {len(reference_videos)}\n"
                        f"Prompt: {prompt}\n"
                        f"Resolution: {resolution}, Ratio: {ratio}, "
                        f"Duration: {duration}s\n"
                        f"Saved to: {video_path}\n"
                        f"Original URL (valid 24h): {video_url}"
                    ),
                ),
            ],
        )
    except Exception as e:
        logger.error(
            f"Reference-to-video generation failed: {e}",
            exc_info=True,
        )
        return ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    type="text",
                    text=(
                        f"Error: Reference-to-video generation failed "
                        f"- {str(e)}"
                    ),
                ),
            ],
        )
    finally:
        if video_lease is not None and video_lease.allowed:
            video_lease.release()
