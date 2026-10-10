# GitHub requirements 来源索引

本文件由 `collect_requirements.py` 生成，机器可读版本见 `requirements_sources.json`。

- 人工条目：来自最初手工核验的 `P0/P1/P2` 清单，`curated=true`。
- 自动条目：来自 GitHub Search API + raw HEAD 校验，`curated=false`，使用前建议人工复核。
- 优先级：`P0` 优先入数据集；`P1` 次之；`P2` 作为补充或负样本。

生成时间：`2026-10-06T07:55:31.783005+00:00`

| # | 仓库 | 文件 | 类型 | 风险 / 价值标签 | 优先级 | 来源 | 抓取地址 |
|---|------|------|------|------------------|--------|------|----------|
| 1 | [pytorch/pytorch](https://github.com/pytorch/pytorch) | `requirements.txt` | 运行时 | torch / cuda / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/pytorch/pytorch/HEAD/requirements.txt) |
| 2 | [AUTOMATIC1111/stable-diffusion-webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui) | `requirements.txt` | 运行时 | torch / opencv / gradio | P0 | 人工 | [raw](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/HEAD/requirements.txt) |
| 3 | [AUTOMATIC1111/stable-diffusion-webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui) | `requirements_versions.txt` | 运行时 | torch / xformers / 版本强锁 | P0 | 人工 | [raw](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/HEAD/requirements_versions.txt) |
| 4 | [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) | `requirements.txt` | 运行时 | torch / transformers | P0 | 人工 | [raw](https://raw.githubusercontent.com/comfyanonymous/ComfyUI/HEAD/requirements.txt) |
| 5 | [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) | `requirements.txt` | 运行时 | torch / xformers / bitsandbytes | P1 | 人工 | [raw](https://raw.githubusercontent.com/kohya-ss/sd-scripts/HEAD/requirements.txt) |
| 6 | [ltdrdata/ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager) | `requirements.txt` | 运行时 | requests / 轻量 | P2 | 人工 | [raw](https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/HEAD/requirements.txt) |
| 7 | [Sanster/IOPaint](https://github.com/Sanster/IOPaint) | `requirements.txt` | 运行时 | torch / diffusers | P1 | 人工 | [raw](https://raw.githubusercontent.com/Sanster/IOPaint/HEAD/requirements.txt) |
| 8 | [hpcaitech/Open-Sora](https://github.com/hpcaitech/Open-Sora) | `requirements.txt` | 运行时 | torch / diffusers / 视频生成 | P1 | 人工 | [raw](https://raw.githubusercontent.com/hpcaitech/Open-Sora/HEAD/requirements.txt) |
| 9 | [chroma-core/chroma](https://github.com/chroma-core/chroma) | `requirements.txt` | 运行时 | numpy / pydantic / fastapi | P0 | 人工 | [raw](https://raw.githubusercontent.com/chroma-core/chroma/HEAD/requirements.txt) |
| 10 | [zilliztech/GPTCache](https://github.com/zilliztech/GPTCache) | `requirements.txt` | 运行时 | numpy / pydantic / 向量库 | P1 | 人工 | [raw](https://raw.githubusercontent.com/zilliztech/GPTCache/HEAD/requirements.txt) |
| 11 | [jina-ai/jina](https://github.com/jina-ai/jina) | `requirements.txt` | 运行时 | numpy / protobuf / grpc | P1 | 人工 | [raw](https://raw.githubusercontent.com/jina-ai/jina/HEAD/requirements.txt) |
| 12 | [jina-ai/serve](https://github.com/jina-ai/serve) | `requirements.txt` | 运行时 | grpc / protobuf / 向量检索 | P0 | 人工 | [raw](https://raw.githubusercontent.com/jina-ai/serve/HEAD/requirements.txt) |
| 13 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | `requirements/common.txt` | 运行时 | torch / transformers / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/vllm-project/vllm/HEAD/requirements/common.txt) |
| 14 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | `requirements/cuda.txt` | 运行时 | torch / cuda / 强锁 | P0 | 人工 | [raw](https://raw.githubusercontent.com/vllm-project/vllm/HEAD/requirements/cuda.txt) |
| 15 | [NVIDIA/TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) | `requirements.txt` | 运行时 | torch / tensorrt / cuda | P0 | 人工 | [raw](https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/HEAD/requirements.txt) |
| 16 | [NVIDIA/apex](https://github.com/NVIDIA/apex) | `requirements.txt` | 运行时 | torch / cuda | P1 | 人工 | [raw](https://raw.githubusercontent.com/NVIDIA/apex/HEAD/requirements.txt) |
| 17 | [microsoft/DeepSpeed](https://github.com/microsoft/DeepSpeed) | `requirements/requirements.txt` | 运行时 | torch / cuda / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/microsoft/DeepSpeed/HEAD/requirements/requirements.txt) |
| 18 | [hpcaitech/ColossalAI](https://github.com/hpcaitech/ColossalAI) | `requirements/requirements.txt` | 运行时 | torch / cuda | P0 | 人工 | [raw](https://raw.githubusercontent.com/hpcaitech/ColossalAI/HEAD/requirements/requirements.txt) |
| 19 | [EleutherAI/gpt-neox](https://github.com/EleutherAI/gpt-neox) | `requirements/requirements.txt` | 运行时 | torch / deepspeed | P0 | 人工 | [raw](https://raw.githubusercontent.com/EleutherAI/gpt-neox/HEAD/requirements/requirements.txt) |
| 20 | [facebookresearch/llama](https://github.com/facebookresearch/llama) | `requirements.txt` | 运行时 | torch / fairscale | P1 | 人工 | [raw](https://raw.githubusercontent.com/facebookresearch/llama/HEAD/requirements.txt) |
| 21 | [meta-llama/llama-recipes](https://github.com/meta-llama/llama-recipes) | `requirements.txt` | 运行时 | torch / transformers | P1 | 人工 | [raw](https://raw.githubusercontent.com/meta-llama/llama-recipes/HEAD/requirements.txt) |
| 22 | [QwenLM/Qwen](https://github.com/QwenLM/Qwen) | `requirements.txt` | 运行时 | torch / transformers | P1 | 人工 | [raw](https://raw.githubusercontent.com/QwenLM/Qwen/HEAD/requirements.txt) |
| 23 | [THUDM/ChatGLM-6B](https://github.com/THUDM/ChatGLM-6B) | `requirements.txt` | 运行时 | torch / transformers | P1 | 人工 | [raw](https://raw.githubusercontent.com/THUDM/ChatGLM-6B/HEAD/requirements.txt) |
| 24 | [ymcui/Chinese-LLaMA-Alpaca](https://github.com/ymcui/Chinese-LLaMA-Alpaca) | `requirements.txt` | 运行时 | torch / transformers | P1 | 人工 | [raw](https://raw.githubusercontent.com/ymcui/Chinese-LLaMA-Alpaca/HEAD/requirements.txt) |
| 25 | [InternLM/InternLM](https://github.com/InternLM/InternLM) | `requirements.txt` | 运行时 | torch / transformers | P1 | 人工 | [raw](https://raw.githubusercontent.com/InternLM/InternLM/HEAD/requirements.txt) |
| 26 | [OpenBMB/MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V) | `requirements.txt` | 运行时 | torch / transformers / 多模态 | P1 | 人工 | [raw](https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/HEAD/requirements.txt) |
| 27 | [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | `requirements.txt` | 运行时 | openai / json | P2 | 人工 | [raw](https://raw.githubusercontent.com/OpenBMB/ChatDev/HEAD/requirements.txt) |
| 28 | [openai/whisper](https://github.com/openai/whisper) | `requirements.txt` | 运行时 | torch / tiktoken | P1 | 人工 | [raw](https://raw.githubusercontent.com/openai/whisper/HEAD/requirements.txt) |
| 29 | [coqui-ai/TTS](https://github.com/coqui-ai/TTS) | `requirements.txt` | 运行时 | torch / numpy / 音频 | P2 | 人工 | [raw](https://raw.githubusercontent.com/coqui-ai/TTS/HEAD/requirements.txt) |
| 30 | [speechbrain/speechbrain](https://github.com/speechbrain/speechbrain) | `requirements.txt` | 运行时 | torch / numpy / 音频 | P2 | 人工 | [raw](https://raw.githubusercontent.com/speechbrain/speechbrain/HEAD/requirements.txt) |
| 31 | [pytorch/audio](https://github.com/pytorch/audio) | `requirements.txt` | 运行时 | torch / numpy | P1 | 人工 | [raw](https://raw.githubusercontent.com/pytorch/audio/HEAD/requirements.txt) |
| 32 | [pytorch/text](https://github.com/pytorch/text) | `requirements.txt` | 运行时 | torch / numpy | P1 | 人工 | [raw](https://raw.githubusercontent.com/pytorch/text/HEAD/requirements.txt) |
| 33 | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | `requirements.txt` | 运行时 | torch / transformers | P2 | 人工 | [raw](https://raw.githubusercontent.com/ggml-org/llama.cpp/HEAD/requirements.txt) |
| 34 | [keras-team/keras](https://github.com/keras-team/keras) | `requirements-common.txt` | 运行时 | tensorflow / numpy | P1 | 人工 | [raw](https://raw.githubusercontent.com/keras-team/keras/HEAD/requirements-common.txt) |
| 35 | [Lightning-AI/torchmetrics](https://github.com/Lightning-AI/torchmetrics) | `requirements.txt` | 运行时 | torch / numpy | P1 | 人工 | [raw](https://raw.githubusercontent.com/Lightning-AI/torchmetrics/HEAD/requirements.txt) |
| 36 | [ray-project/ray](https://github.com/ray-project/ray) | `python/requirements.txt` | 运行时 | numpy / protobuf / grpc | P0 | 人工 | [raw](https://raw.githubusercontent.com/ray-project/ray/HEAD/python/requirements.txt) |
| 37 | [openai/gym](https://github.com/openai/gym) | `requirements.txt` | 运行时 | numpy / 强化学习 | P2 | 人工 | [raw](https://raw.githubusercontent.com/openai/gym/HEAD/requirements.txt) |
| 38 | [ultralytics/yolov5](https://github.com/ultralytics/yolov5) | `requirements.txt` | 运行时 | torch / opencv / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/ultralytics/yolov5/HEAD/requirements.txt) |
| 39 | [ultralytics/yolov3](https://github.com/ultralytics/yolov3) | `requirements.txt` | 运行时 | torch / opencv / numpy | P1 | 人工 | [raw](https://raw.githubusercontent.com/ultralytics/yolov3/HEAD/requirements.txt) |
| 40 | [facebookresearch/detr](https://github.com/facebookresearch/detr) | `requirements.txt` | 运行时 | torch / 目标检测 | P1 | 人工 | [raw](https://raw.githubusercontent.com/facebookresearch/detr/HEAD/requirements.txt) |
| 41 | [facebookresearch/ImageBind](https://github.com/facebookresearch/ImageBind) | `requirements.txt` | 运行时 | torch / 多模态 | P2 | 人工 | [raw](https://raw.githubusercontent.com/facebookresearch/ImageBind/HEAD/requirements.txt) |
| 42 | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | `requirements.txt` | 运行时 | paddle / opencv / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/HEAD/requirements.txt) |
| 43 | [PaddlePaddle/PaddleNLP](https://github.com/PaddlePaddle/PaddleNLP) | `requirements.txt` | 运行时 | paddle / datasets | P1 | 人工 | [raw](https://raw.githubusercontent.com/PaddlePaddle/PaddleNLP/HEAD/requirements.txt) |
| 44 | [PaddlePaddle/PaddleRec](https://github.com/PaddlePaddle/PaddleRec) | `requirements.txt` | 运行时 | paddle / 推荐 | P1 | 人工 | [raw](https://raw.githubusercontent.com/PaddlePaddle/PaddleRec/HEAD/requirements.txt) |
| 45 | [open-mmlab/mmdetection](https://github.com/open-mmlab/mmdetection) | `requirements/runtime.txt` | 运行时 | torch / mmcv / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmdetection/HEAD/requirements/runtime.txt) |
| 46 | [open-mmlab/mmsegmentation](https://github.com/open-mmlab/mmsegmentation) | `requirements/runtime.txt` | 运行时 | torch / mmcv / numpy | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmsegmentation/HEAD/requirements/runtime.txt) |
| 47 | [open-mmlab/mmdetection3d](https://github.com/open-mmlab/mmdetection3d) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 3D | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmdetection3d/HEAD/requirements/runtime.txt) |
| 48 | [open-mmlab/mmocr](https://github.com/open-mmlab/mmocr) | `requirements/runtime.txt` | 运行时 | torch / mmcv / OCR | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmocr/HEAD/requirements/runtime.txt) |
| 49 | [open-mmlab/mmpretrain](https://github.com/open-mmlab/mmpretrain) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 预训练 | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmpretrain/HEAD/requirements/runtime.txt) |
| 50 | [open-mmlab/mmpose](https://github.com/open-mmlab/mmpose) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 姿态 | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmpose/HEAD/requirements/runtime.txt) |
| 51 | [open-mmlab/mmdeploy](https://github.com/open-mmlab/mmdeploy) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 部署 | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmdeploy/HEAD/requirements/runtime.txt) |
| 52 | [open-mmlab/mmtracking](https://github.com/open-mmlab/mmtracking) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 跟踪 | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmtracking/HEAD/requirements/runtime.txt) |
| 53 | [open-mmlab/mmgeneration](https://github.com/open-mmlab/mmgeneration) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 生成 | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmgeneration/HEAD/requirements/runtime.txt) |
| 54 | [open-mmlab/mmagic](https://github.com/open-mmlab/mmagic) | `requirements/runtime.txt` | 运行时 | torch / mmcv / 图像生成 | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-mmlab/mmagic/HEAD/requirements/runtime.txt) |
| 55 | [scikit-image/scikit-image](https://github.com/scikit-image/scikit-image) | `requirements.txt` | 运行时 | numpy / scipy / 图像 | P1 | 人工 | [raw](https://raw.githubusercontent.com/scikit-image/scikit-image/HEAD/requirements.txt) |
| 56 | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) | `requirements.txt` | 开发 | numpy / onnx / 推理 | P1 | 人工 | [raw](https://raw.githubusercontent.com/microsoft/onnxruntime/HEAD/requirements.txt) |
| 57 | [netbox-community/netbox](https://github.com/netbox-community/netbox) | `requirements.txt` | 运行时 | django / 网络设备管理 | P1 | 人工 | [raw](https://raw.githubusercontent.com/netbox-community/netbox/HEAD/requirements.txt) |
| 58 | [boto/boto3](https://github.com/boto/boto3) | `requirements.txt` | 开发 | botocore / urllib3 | P1 | 人工 | [raw](https://raw.githubusercontent.com/boto/boto3/HEAD/requirements.txt) |
| 59 | [open-webui/open-webui](https://github.com/open-webui/open-webui) | `backend/requirements.txt` | 运行时 | fastapi / pydantic | P0 | 人工 | [raw](https://raw.githubusercontent.com/open-webui/open-webui/HEAD/backend/requirements.txt) |
| 60 | [mongodb/mongo-python-driver](https://github.com/mongodb/mongo-python-driver) | `requirements.txt` | 开发 | pymongo / dnspython | P2 | 人工 | [raw](https://raw.githubusercontent.com/mongodb/mongo-python-driver/HEAD/requirements.txt) |
| 61 | [gradio-app/gradio](https://github.com/gradio-app/gradio) | `requirements.txt` | 运行时 | fastapi / pydantic | P1 | 人工 | [raw](https://raw.githubusercontent.com/gradio-app/gradio/HEAD/requirements.txt) |
| 62 | [healthchecks/healthchecks](https://github.com/healthchecks/healthchecks) | `requirements.txt` | 运行时 | django | P1 | 人工 | [raw](https://raw.githubusercontent.com/healthchecks/healthchecks/HEAD/requirements.txt) |
| 63 | [ansible/awx](https://github.com/ansible/awx) | `requirements/requirements.txt` | 运行时 | django / celery | P1 | 人工 | [raw](https://raw.githubusercontent.com/ansible/awx/HEAD/requirements/requirements.txt) |
| 64 | [apache/superset](https://github.com/apache/superset) | `requirements/development.txt` | 开发 | flask / sqlalchemy | P1 | 人工 | [raw](https://raw.githubusercontent.com/apache/superset/HEAD/requirements/development.txt) |
| 65 | [odoo/odoo](https://github.com/odoo/odoo) | `requirements.txt` | 运行时 | python3.10 / 企业应用 | P1 | 人工 | [raw](https://raw.githubusercontent.com/odoo/odoo/HEAD/requirements.txt) |
| 66 | [celery/celery](https://github.com/celery/celery) | `requirements/default.txt` | 运行时 | kombu / 任务队列 | P1 | 人工 | [raw](https://raw.githubusercontent.com/celery/celery/HEAD/requirements/default.txt) |
| 67 | [ansible/ansible](https://github.com/ansible/ansible) | `requirements.txt` | 开发 | jinja2 / 自动化 | P1 | 人工 | [raw](https://raw.githubusercontent.com/ansible/ansible/HEAD/requirements.txt) |
| 68 | [arachnys/cabot](https://github.com/arachnys/cabot) | `requirements.txt` | 运行时 | django / 监控 | P2 | 人工 | [raw](https://raw.githubusercontent.com/arachnys/cabot/HEAD/requirements.txt) |
| 69 | [pandas-dev/pandas](https://github.com/pandas-dev/pandas) | `requirements-dev.txt` | 开发 | numpy / pytest | P1 | 人工 | [raw](https://raw.githubusercontent.com/pandas-dev/pandas/HEAD/requirements-dev.txt) |
| 70 | [great-expectations/great_expectations](https://github.com/great-expectations/great_expectations) | `requirements.txt` | 运行时 | pandas / 数据质量 | P1 | 人工 | [raw](https://raw.githubusercontent.com/great-expectations/great_expectations/HEAD/requirements.txt) |
| 71 | [kubeflow/pipelines](https://github.com/kubeflow/pipelines) | `sdk/python/requirements.txt` | 子模块 | kfp / ML 流水线 | P1 | 人工 | [raw](https://raw.githubusercontent.com/kubeflow/pipelines/HEAD/sdk/python/requirements.txt) |
| 72 | [triton-inference-server/client](https://github.com/triton-inference-server/client) | `src/python/library/requirements/requirements.txt` | 子模块 | grpc / numpy / 推理服务 | P1 | 人工 | [raw](https://raw.githubusercontent.com/triton-inference-server/client/HEAD/src/python/library/requirements/requirements.txt) |
| 73 | [home-assistant/core](https://github.com/home-assistant/core) | `requirements_all.txt` | 运行时 | 全量集成 / 冲突富矿 | P0 | 人工 | [raw](https://raw.githubusercontent.com/home-assistant/core/HEAD/requirements_all.txt) |
| 74 | [home-assistant/core](https://github.com/home-assistant/core) | `requirements.txt` | 运行时 | 核心依赖 | P1 | 人工 | [raw](https://raw.githubusercontent.com/home-assistant/core/HEAD/requirements.txt) |
| 75 | [scrapinghub/splash](https://github.com/scrapinghub/splash) | `requirements.txt` | 运行时 | twisted / 爬虫 | P2 | 人工 | [raw](https://raw.githubusercontent.com/scrapinghub/splash/HEAD/requirements.txt) |
| 76 | [binux/pyspider](https://github.com/binux/pyspider) | `requirements.txt` | 运行时 | flask / tornado / 爬虫 | P2 | 人工 | [raw](https://raw.githubusercontent.com/binux/pyspider/HEAD/requirements.txt) |
| 77 | [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) | `requirements.txt` | 运行时 | flask / 自动化 | P2 | 人工 | [raw](https://raw.githubusercontent.com/dgtlmoon/changedetection.io/HEAD/requirements.txt) |
| 78 | [microsoft/playwright-python](https://github.com/microsoft/playwright-python) | `requirements.txt` | 开发 | greenlet / pyee | P2 | 人工 | [raw](https://raw.githubusercontent.com/microsoft/playwright-python/HEAD/requirements.txt) |
| 79 | [seleniumbase/SeleniumBase](https://github.com/seleniumbase/SeleniumBase) | `requirements.txt` | 运行时 | selenium / 自动化 | P2 | 人工 | [raw](https://raw.githubusercontent.com/seleniumbase/SeleniumBase/HEAD/requirements.txt) |
| 80 | [psf/requests](https://github.com/psf/requests) | `requirements-dev.txt` | 开发 | urllib3 / 网络 | P2 | 人工 | [raw](https://raw.githubusercontent.com/psf/requests/HEAD/requirements-dev.txt) |
| 81 | [encode/httpx](https://github.com/encode/httpx) | `requirements.txt` | 开发 | httpcore / 网络 | P2 | 人工 | [raw](https://raw.githubusercontent.com/encode/httpx/HEAD/requirements.txt) |
| 82 | [tornadoweb/tornado](https://github.com/tornadoweb/tornado) | `requirements.txt` | 开发 | pycurl / 网络 | P2 | 人工 | [raw](https://raw.githubusercontent.com/tornadoweb/tornado/HEAD/requirements.txt) |
| 83 | [huggingface/transformers](https://github.com/huggingface/transformers) | `examples/pytorch/text-classification/requirements.txt` | 示例 | torch / datasets | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/transformers/HEAD/examples/pytorch/text-classification/requirements.txt) |
| 84 | [huggingface/transformers](https://github.com/huggingface/transformers) | `examples/pytorch/language-modeling/requirements.txt` | 示例 | torch / datasets | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/transformers/HEAD/examples/pytorch/language-modeling/requirements.txt) |
| 85 | [huggingface/transformers](https://github.com/huggingface/transformers) | `examples/pytorch/token-classification/requirements.txt` | 示例 | torch / datasets | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/transformers/HEAD/examples/pytorch/token-classification/requirements.txt) |
| 86 | [huggingface/diffusers](https://github.com/huggingface/diffusers) | `examples/textual_inversion/requirements.txt` | 示例 | torch / accelerate | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/diffusers/HEAD/examples/textual_inversion/requirements.txt) |
| 87 | [huggingface/diffusers](https://github.com/huggingface/diffusers) | `examples/dreambooth/requirements.txt` | 示例 | torch / accelerate | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/diffusers/HEAD/examples/dreambooth/requirements.txt) |
| 88 | [huggingface/diffusers](https://github.com/huggingface/diffusers) | `examples/text_to_image/requirements.txt` | 示例 | torch / accelerate | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/diffusers/HEAD/examples/text_to_image/requirements.txt) |
| 89 | [huggingface/diffusers](https://github.com/huggingface/diffusers) | `examples/controlnet/requirements.txt` | 示例 | torch / accelerate | P1 | 人工 | [raw](https://raw.githubusercontent.com/huggingface/diffusers/HEAD/examples/controlnet/requirements.txt) |
| 90 | [boto/botocore](https://github.com/boto/botocore) | `requirements.txt` | 开发 | botocore / urllib3 | P1 | 人工 | [raw](https://raw.githubusercontent.com/boto/botocore/HEAD/requirements.txt) |
| 91 | [apache/superset](https://github.com/apache/superset) | `requirements/base.txt` | 运行时 | 自动发现 / 未人工复核 | P0 | 自动 | [raw](https://raw.githubusercontent.com/apache/superset/master/requirements/base.txt) |

## 统计

- 合计 `91` 条来源：`curated=true` 90 条，`curated=false` 1 条。
- `P0` 共 `28` 条，`P1` 共 `46` 条，`P2` 共 `17` 条。
- 未收录但已排查的失效路径：`zulip/zulip`、`paperless-ngx/paperless-ngx`、`langgenius/dify` 的旧路径均返回 `404`，说明这些仓库已迁移到 pyproject/uv 等新结构。
