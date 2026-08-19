# Qwen-Image Tool Plugin

Generate and edit images using Alibaba Cloud's Qwen-Image models via DashScope SDK.

The plugin also supports OpenAI-compatible relay gateways (e.g. a self-hosted
NewAPI): when the configured endpoint host is not `aliyuncs.com`, requests are
sent through `POST {root}/v1/images/generations` instead of the native
DashScope SDK.

## Tools

### `generate_image_qwen` - 文生图

Generate high-quality images from text prompts. Supports complex text rendering, multi-style artwork, and fine-grained detail control.

**Parameters:**
- `prompt` (required): Image description (Chinese/English)
- `size`: Image size in "width*height" format (default: `"2048*2048"`)
- `n`: Number of images to generate, 1–6 (default: 1)
- `negative_prompt`: What to exclude from the image
- `prompt_extend`: Enable prompt auto-optimization (default: true)

**Available models:**

| Model | Description |
|-------|-------------|
| `qwen-image-2.0-pro` ⭐ | Best text rendering, semantic adherence |
| `qwen-image-2.0` | Balanced speed and quality |
| `qwen-image-max` | Highest realism |
| `qwen-image-plus` | Diverse art styles |

**Recommended sizes for qwen-image-2.0 series:**
- `2048*2048` (1:1, default)
- `2688*1536` (16:9)
- `1536*2688` (9:16)
- `2368*1728` (4:3)

---

### `edit_image_qwen` - 图像编辑

Edit images or fuse multiple images using text instructions.

**Parameters:**
- `prompt` (required): Edit instruction. Use "图一"/"图二" (or "image 1"/"image 2") to refer to reference images
- `reference_images` (required): List of image URLs or local file paths (at least 1)
- `size`: Output image size (leave empty to auto-detect from input)
- `n`: Number of output images (default: 1)
- `negative_prompt`: What to exclude
- `prompt_extend`: Enable prompt auto-optimization (default: true)

**Supported models:**

| Model | Best for |
|-------|----------|
| `qwen-image-2.0-pro` ⭐ | General editing, text rendering |
| `qwen-image-2.0` | Fast editing |
| `qwen-image-edit-max` | Industrial design, geometry |
| `qwen-image-edit-plus` | Multi-image output |
| `qwen-image-edit` | Basic single-image editing |

**Image input support:**
- HTTP/HTTPS URLs (used directly)
- Local file paths: `.png`, `.jpg`, `.jpeg`, `.webp` (auto-converted to base64)

**Example prompts:**
- Single image edit: `"将图片风格改为水墨画风格"`
- Multi-image fusion: `"以图一的城市照片为底图，将图二中的卡通角色放置在建筑物周围"`
- Text rendering: `"在右下角添加印章，内容为'2025'"`

---

## Configuration

Each tool has independent configuration fields:

| Field | Description | Default |
|-------|-------------|---------|
| `api_key` | DashScope API key (required) | — |
| `endpoint` | Regional API endpoint, or NewAPI relay URL | `https://dashscope.aliyuncs.com/api/v1` |
| `timeout` | Request timeout in seconds | 120 |
| `model` | Model name for image generation/editing | `qwen-image-2.0` (generate) / `qwen-image-2.0-pro` (edit) |

**Endpoints:**
- Beijing: `https://dashscope.aliyuncs.com/api/v1`
- Singapore: `https://dashscope-intl.aliyuncs.com/api/v1`
- NewAPI relay: `https://your-newapi-host/v1` (any non-`aliyuncs.com` host
  switches the plugin to the OpenAI-compatible protocol)

> Note: API key and endpoint must be from the same region.

> In NewAPI relay mode, `edit_image_qwen` sends the first reference image as
> the `image` field (extra images via `metadata.images`) together with the
> prompt to `/v1/images/generations`, instead of the multipart `/images/edits`
> interface.

Get your API key at: https://bailian.console.aliyun.com/

## Output

Generated images are saved to `{DEFAULT_MEDIA_DIR}/qwen_image/` as PNG files. Image URLs from the API are valid for 24 hours.
