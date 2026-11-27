#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CREDENTIALS_FILE="${DINGTALK_CREDENTIALS_FILE:-$SCRIPT_DIR/credentials.env}"
EXAMPLE_FILE="$SCRIPT_DIR/credentials.env.example"

ensure_credentials_file() {
  if [ -f "$CREDENTIALS_FILE" ]; then
    chmod 600 "$CREDENTIALS_FILE"
    return
  fi

  [ -f "$EXAMPLE_FILE" ] || {
    printf '凭证模板不存在：%s\n' "$EXAMPLE_FILE" >&2
    exit 2
  }

  umask 077
  cp "$EXAMPLE_FILE" "$CREDENTIALS_FILE"
  printf '已创建凭证文件：%s\n' "$CREDENTIALS_FILE" >&2
  printf '请填写 DINGTALK_CLIENT_ID 和 DINGTALK_CLIENT_SECRET 后重试。\n' >&2
}

main() {
  case "${1:-setup}" in
    setup)
      ensure_credentials_file
      ;;
    --check|check)
      ensure_credentials_file
      exec "$SCRIPT_DIR/dingtalk_http.sh" check
      ;;
    *)
      printf '用法：%s [setup|--check]\n' "$0" >&2
      exit 2
      ;;
  esac
}

main "$@"
