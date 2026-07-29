#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SKILL_PARENT=$(CDPATH= cd -- "$SKILL_DIR/.." && pwd)
SKILL_NAME=$(basename -- "$SKILL_DIR")
OUTPUT_ARG="${1:-$PWD/$SKILL_NAME.zip}"
OUTPUT_DIR=$(dirname -- "$OUTPUT_ARG")
OUTPUT_NAME=$(basename -- "$OUTPUT_ARG")

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)
OUTPUT_PATH="$OUTPUT_DIR/$OUTPUT_NAME"

if [ -e "$OUTPUT_PATH" ]; then
  echo "输出文件已存在，请换一个文件名：$OUTPUT_PATH" >&2
  exit 2
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "缺少 zip 命令，无法打包。" >&2
  exit 2
fi

(
  cd "$SKILL_PARENT"
  zip -q "$OUTPUT_PATH" \
    "$SKILL_NAME/.gitignore" \
    "$SKILL_NAME/SKILL.md" \
    "$SKILL_NAME/agents/openai.yaml" \
    "$SKILL_NAME/references/oa-attachments.md" \
    "$SKILL_NAME/references/review-rules.md" \
    "$SKILL_NAME/scripts/credentials.env.example" \
    "$SKILL_NAME/scripts/dingtalk_http.sh" \
    "$SKILL_NAME/scripts/package_skill.sh" \
    "$SKILL_NAME/scripts/setup_credentials.sh"
)

echo "{\"success\":true,\"output\":\"$OUTPUT_PATH\",\"credentialsIncluded\":false}"
