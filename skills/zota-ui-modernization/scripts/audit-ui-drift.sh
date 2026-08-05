#!/usr/bin/env bash

set -u

root="${1:-.}"
source_root="$root/src"

if [[ ! -d "$source_root" ]]; then
  printf 'error: expected a frontend source directory at %s\n' "$source_root" >&2
  exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
  printf 'error: rg is required\n' >&2
  exit 2
fi

scan() {
  local title="$1"
  local pattern="$2"

  printf '\n## %s\n' "$title"
  rg -n --glob '*.{css,ts,tsx}' "$pattern" "$source_root" || true
}

printf '# Zota UI drift audit\n'
printf 'root: %s\n' "$root"

scan 'Broad Ant Design selectors' '^\s*\.ant-[a-zA-Z0-9_-]+\s*[{,]'
scan 'Important overrides' '!important'
scan 'Very small fonts' "font-size\\s*:\\s*([0-9]|1[01])px|fontSize\\s*:\\s*['\"]?([0-9]|1[01])px"
scan 'Oversized fixed radii' "border-radius\\s*:\\s*(1[2-9]|[2-9][0-9])px|borderRadius\\s*:\\s*['\"]?(1[2-9]|[2-9][0-9])px"
scan 'Deprecated Ant Design props' '\b(bordered|direction|wrapperClassName|maskClosable|bodyStyle|headStyle)='
scan 'Hardcoded hex colors in components' '#[0-9a-fA-F]{3,8}'

printf '\nAudit complete. Review findings against documented exceptions.\n'
