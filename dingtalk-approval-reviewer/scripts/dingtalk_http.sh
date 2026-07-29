#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CREDENTIALS_FILE="${DINGTALK_CREDENTIALS_FILE:-$SCRIPT_DIR/credentials.env}"
API_BASE='https://api.dingtalk.com'
OAPI_BASE='https://oapi.dingtalk.com'
PLACEHOLDER_SECRET='__REPLACE_WITH_DINGTALK_APP_SECRET__'
PLACEHOLDER_CLIENT_ID='__REPLACE_WITH_DINGTALK_CLIENT_ID__'
PARTIAL_FILE=''

fail() {
  message=$1
  code=${2:-2}
  printf '%s\n' "$message" >&2
  exit "$code"
}

cleanup_partial() {
  if [ -n "$PARTIAL_FILE" ] && [ -f "$PARTIAL_FILE" ]; then
    rm -f -- "$PARTIAL_FILE"
  fi
}

trap cleanup_partial EXIT HUP INT TERM

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令：$1"
}

load_credentials() {
  [ -f "$CREDENTIALS_FILE" ] || fail "凭证文件不存在：$CREDENTIALS_FILE"
  chmod 600 "$CREDENTIALS_FILE"

  # credentials.env 是当前用户控制的私有 shell 配置。
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"

  DINGTALK_CLIENT_ID="${DINGTALK_CLIENT_ID:-${DWS_CLIENT_ID:-}}"
  DINGTALK_CLIENT_SECRET="${DINGTALK_CLIENT_SECRET:-${DWS_CLIENT_SECRET:-}}"

  [ -n "$DINGTALK_CLIENT_ID" ] || fail "凭证配置无效：DINGTALK_CLIENT_ID 为空。"
  [ "$DINGTALK_CLIENT_ID" != "$PLACEHOLDER_CLIENT_ID" ] ||
    fail "凭证配置无效：请填写 DINGTALK_CLIENT_ID。"
  [ -n "$DINGTALK_CLIENT_SECRET" ] || fail "凭证配置无效：DINGTALK_CLIENT_SECRET 为空。"
  [ "$DINGTALK_CLIENT_SECRET" != "$PLACEHOLDER_SECRET" ] ||
    fail "凭证配置无效：请填写 DINGTALK_CLIENT_SECRET。"
}

get_access_token() {
  payload=$(jq -nc \
    --arg app_key "$DINGTALK_CLIENT_ID" \
    --arg app_secret "$DINGTALK_CLIENT_SECRET" \
    '{appKey:$app_key,appSecret:$app_secret}')

  response=$(curl -fsS \
    -X POST "$API_BASE/v1.0/oauth2/accessToken" \
    -H 'Content-Type: application/json' \
    --data "$payload") ||
    fail "钉钉应用认证失败。"

  ACCESS_TOKEN=$(printf '%s' "$response" | jq -er '.accessToken') ||
    fail "钉钉应用认证响应缺少 accessToken。"
}

validate_identifier() {
  name=$1
  value=$2
  [ -n "$value" ] || fail "$name 不能为空。"
  case "$value" in
    *[!A-Za-z0-9._:-]*)
      fail "$name 包含不允许的字符。"
      ;;
  esac
}

request_download_info() {
  process_instance_id=$1
  file_id=$2
  payload=$(jq -nc \
    --arg process_instance_id "$process_instance_id" \
    --arg file_id "$file_id" \
    '{
      processInstanceId:$process_instance_id,
      fileId:$file_id,
      withCommentAttatchment:false
    }')

  curl -fsS \
    -X POST "$API_BASE/v1.0/workflow/processInstances/spaces/files/urls/download" \
    -H "x-acs-dingtalk-access-token: $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    --data "$payload"
}

command_check() {
  get_access_token
  printf '{"configured":true,"authenticated":true,"transport":"direct-http"}\n'
}

command_search_user() {
  keyword=${1:-}
  [ -n "$keyword" ] || fail "search-user 需要 keyword。"
  get_access_token

  payload=$(jq -nc --arg keyword "$keyword" '{queryWord:$keyword,offset:0,size:20}')
  curl -fsS \
    -X POST "$API_BASE/v1.0/contact/users/search" \
    -H "x-acs-dingtalk-access-token: $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    --data "$payload" |
    jq '{
      success:true,
      totalCount,
      hasMore,
      userIds:[.list[] | tostring]
    }'
}

command_user_detail() {
  user_id=${1:-}
  validate_identifier "userId" "$user_id"
  get_access_token

  payload=$(jq -nc --arg user_id "$user_id" '{userid:$user_id}')
  {
    printf 'url = "%s/topapi/v2/user/get?access_token=%s"\n' \
      "$OAPI_BASE" "$ACCESS_TOKEN"
    printf 'request = "POST"\n'
    printf 'header = "Content-Type: application/json"\n'
  } |
    curl -fsS --config - --data "$payload" |
    jq '{
      errcode,
      errmsg,
      result:{
        userId:.result.userid,
        name:.result.name,
        title:.result.title,
        active:.result.active,
        admin:.result.admin,
        deptIds:.result.dept_id_list
      }
    }'
}

command_todo_count() {
  user_id=${1:-}
  validate_identifier "userId" "$user_id"
  get_access_token

  curl -fsS -G \
    "$API_BASE/v1.0/workflow/processes/todoTasks/numbers" \
    -H "x-acs-dingtalk-access-token: $ACCESS_TOKEN" \
    --data-urlencode "userId=$user_id" |
    jq '{success:(.result | type == "number"),result}'
}

command_todo_list() {
  user_id=${1:-}
  offset=${2:-0}
  count=${3:-20}
  validate_identifier "userId" "$user_id"
  case "$offset:$count" in
    *[!0-9:]*|:*|*:) fail "offset 和 count 必须是非负整数。" ;;
  esac
  [ "$count" -le 20 ] || fail "count 不能超过 20。"
  get_access_token

  payload=$(jq -nc \
    --arg user_id "$user_id" \
    --argjson offset "$offset" \
    --argjson count "$count" \
    '{offset:$offset,count:$count,userid:$user_id,status:0}')

  {
    printf 'url = "%s/topapi/process/workrecord/task/query?access_token=%s"\n' \
      "$OAPI_BASE" "$ACCESS_TOKEN"
    printf 'request = "POST"\n'
    printf 'header = "Content-Type: application/json"\n'
  } |
    curl -fsS --config - --data "$payload" |
    jq '{
      errcode,
      errmsg,
      result:{
        hasMore:(.result.has_more // false),
        tasks:[
          (.result.list // [])[] |
          {
            taskId:(.task_id // .taskId),
            processInstanceId:(.instance_id // .processInstanceId),
            title,
            createTime:(.create_time // .createTime)
          }
        ]
      }
    }'
}

command_detail() {
  process_instance_id=${1:-}
  output=${2:-}
  validate_identifier "processInstanceId" "$process_instance_id"
  [ -n "$output" ] || fail "detail 需要明确的输出文件路径。"
  [ ! -e "$output" ] || fail "输出文件已存在：$output"
  output_dir=$(dirname -- "$output")
  [ -d "$output_dir" ] || fail "输出目录不存在：$output_dir"
  get_access_token

  umask 077
  curl -fsS -G \
    "$API_BASE/v1.0/workflow/processInstances" \
    -H "x-acs-dingtalk-access-token: $ACCESS_TOKEN" \
    --data-urlencode "processInstanceId=$process_instance_id" \
    -o "$output" ||
    fail "审批详情读取失败。"

  jq -e '.success == true and .result != null' "$output" >/dev/null ||
    fail "审批详情响应无效。"
  printf '{"success":true,"output":"%s"}\n' "$output"
}

command_download_info() {
  process_instance_id=${1:-}
  file_id=${2:-}
  validate_identifier "processInstanceId" "$process_instance_id"
  validate_identifier "fileId" "$file_id"
  get_access_token

  response=$(request_download_info "$process_instance_id" "$file_id") ||
    fail "附件下载信息读取失败。"
  printf '%s' "$response" |
    jq --arg file_id "$file_id" '{
      success:(.success == true),
      result:{
        fileId:(.result.fileId | tostring),
        spaceId:(.result.spaceId | tostring),
        requestedFileId:$file_id,
        hasDownloadUri:(.result.downloadUri != null)
      }
    }'
}

command_download() {
  process_instance_id=${1:-}
  file_id=${2:-}
  space_id=${3:-}
  output=${4:-}
  validate_identifier "processInstanceId" "$process_instance_id"
  validate_identifier "fileId" "$file_id"
  validate_identifier "spaceId" "$space_id"
  [ -n "$output" ] || fail "download 需要明确的输出文件路径。"
  [ ! -e "$output" ] || fail "输出文件已存在：$output"
  output_dir=$(dirname -- "$output")
  [ -d "$output_dir" ] || fail "输出目录不存在：$output_dir"
  get_access_token

  response=$(request_download_info "$process_instance_id" "$file_id") ||
    fail "附件下载信息读取失败。"
  printf '%s' "$response" |
    jq -e \
      --arg file_id "$file_id" \
      --arg space_id "$space_id" \
      '
        .success == true and
        (.result.fileId | tostring) == $file_id and
        (.result.spaceId | tostring) == $space_id and
        (.result.downloadUri | type) == "string" and
        (.result.downloadUri | length) > 0
      ' >/dev/null ||
    fail "附件下载信息与请求的 fileId/spaceId 不匹配。"

  download_uri=$(printf '%s' "$response" | jq -er '.result.downloadUri')
  umask 077
  PARTIAL_FILE=$(mktemp "$output.partial.XXXXXX")
  curl -fsSL "$download_uri" -o "$PARTIAL_FILE" ||
    fail "附件下载失败。"
  mv -- "$PARTIAL_FILE" "$output"
  PARTIAL_FILE=''

  bytes=$(wc -c <"$output" | tr -d ' ')
  printf '{"success":true,"output":"%s","fileId":"%s","spaceId":"%s","bytes":%s}\n' \
    "$output" "$file_id" "$space_id" "$bytes"
}

main() {
  require_command curl
  require_command jq
  load_credentials

  case "${1:-}" in
    check)
      command_check
      ;;
    search-user)
      shift
      command_search_user "$@"
      ;;
    user-detail)
      shift
      command_user_detail "$@"
      ;;
    todo-count)
      shift
      command_todo_count "$@"
      ;;
    todo-list)
      shift
      command_todo_list "$@"
      ;;
    detail)
      shift
      command_detail "$@"
      ;;
    download-info)
      shift
      command_download_info "$@"
      ;;
    download)
      shift
      command_download "$@"
      ;;
    *)
      fail "用法：$0 {check|search-user <keyword>|user-detail <userId>|todo-count <userId>|todo-list <userId> [offset] [count]|detail <processInstanceId> <output>|download-info <processInstanceId> <fileId>|download <processInstanceId> <fileId> <spaceId> <output>}"
      ;;
  esac
}

main "$@"
