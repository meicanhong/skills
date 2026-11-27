# Skills

Personal skill collection.

## Active skills

- [`deploy-project`](deploy-project/SKILL.md): Build `linux/amd64` Docker images, push to Alibaba Cloud ACR, and deploy via the project's own workflow. Copy [`deploy-project/.env.example`](deploy-project/.env.example) to `deploy-project/.env` locally (never commit).
- [`starrocks`](starrocks/SKILL.md): Alibaba Cloud EMR Serverless StarRocks development and operations.
- [`ui-guidelines`](ui-guidelines/SKILL.md): Global UI Design System for modern SaaS / enterprise dashboards built with Tailwind CSS and shadcn/ui.
- [`pstack`](pstack/README.md): Agent skills, subagents, and hooks plugin bundle.

## Archived skills (unmaintained)

The following skills are no longer maintained and have been moved under [`archived/`](archived/):

- [`metabase`](archived/metabase/SKILL.md): Safe Metabase API inspection, querying, reporting, and explicitly requested dashboard updates.
- [`dingtalk-approval-reviewer`](archived/dingtalk-approval-reviewer/SKILL.md): Read-only DingTalk OA approval review through direct enterprise HTTP APIs.
- [`dingtalk-product-delivery-report`](archived/dingtalk-product-delivery-report/SKILL.md): Read-only product delivery risk reporting from DingTalk project, directory, and work-log data.
- [`skincare-explainer-video`](archived/skincare-explainer-video/SKILL.md): Chinese skincare explainer-video production with MiniMax TTS, Alibaba Cloud Fun-ASR, APIMart storyboard images, Seedance clips, and timestamp-accurate editing.
- [`minimax-speech`](archived/minimax-speech/SKILL.md): MiniMax Speech 2.8 HD voice cloning and speech synthesis with the company-authorized Lao Wang studio voice as the default.
- [`apimart-gpt-image-2`](archived/apimart-gpt-image-2/SKILL.md): Non-official GPT-Image-2 generation through APIMart with local reference uploads, polling, downloads, and official fallback disabled.
- [`seedance-video-generator`](archived/seedance-video-generator/SKILL.md): Seedance 2.0 Mini video generation with one-time human-approved submissions, status polling, and safe downloads.

Local credentials, environment overrides, caches, and build artifacts are intentionally excluded from this repository.

The four archived skincare-video skills read shared credentials from `${CODEX_HOME:-$HOME/.codex}/skincare-video-bundle.env`. Copy [`archived/skincare-video-bundle.env.example`](archived/skincare-video-bundle.env.example) to that location and fill the API keys locally. Never commit the completed file.
