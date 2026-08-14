# Skills

Personal skill collection.

## Included skills

- [`starrocks`](starrocks/SKILL.md): Alibaba Cloud EMR Serverless StarRocks development and operations.
- [`metabase`](metabase/SKILL.md): Safe Metabase API inspection, querying, reporting, and explicitly requested dashboard updates.
- [`dingtalk-approval-reviewer`](dingtalk-approval-reviewer/SKILL.md): Read-only DingTalk OA approval review through direct enterprise HTTP APIs.
- [`dingtalk-product-delivery-report`](dingtalk-product-delivery-report/SKILL.md): Read-only product delivery risk reporting from DingTalk project, directory, and work-log data.
- [`skincare-explainer-video`](skincare-explainer-video/SKILL.md): Chinese skincare explainer-video production with MiniMax TTS, Alibaba Cloud Fun-ASR, APIMart storyboard images, Seedance clips, and timestamp-accurate editing.
- [`minimax-speech`](minimax-speech/SKILL.md): MiniMax Speech 2.8 HD voice cloning and speech synthesis with the company-authorized Lao Wang studio voice as the default.
- [`apimart-gpt-image-2`](apimart-gpt-image-2/SKILL.md): Non-official GPT-Image-2 generation through APIMart with local reference uploads, polling, downloads, and official fallback disabled.
- [`seedance-video-generator`](seedance-video-generator/SKILL.md): Seedance 2.0 Mini video generation with one-time human-approved submissions, status polling, and safe downloads.

Local credentials, environment overrides, caches, and build artifacts are intentionally excluded from this repository.

The four skincare-video skills read shared credentials from `${CODEX_HOME:-$HOME/.codex}/skincare-video-bundle.env`. Copy [`skincare-video-bundle.env.example`](skincare-video-bundle.env.example) to that location and fill the API keys locally. Never commit the completed file.
