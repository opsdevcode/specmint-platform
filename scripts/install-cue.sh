#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/cue/VERSION")"
OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}" in
  Linux)
    case "${ARCH}" in
      x86_64) CUE_ARCH="linux_amd64" ;;
      aarch64|arm64) CUE_ARCH="linux_arm64" ;;
      *)
        echo "unsupported Linux architecture: ${ARCH}" >&2
        exit 1
        ;;
    esac
    ;;
  Darwin)
    case "${ARCH}" in
      x86_64) CUE_ARCH="darwin_amd64" ;;
      arm64) CUE_ARCH="darwin_arm64" ;;
      *)
        echo "unsupported Darwin architecture: ${ARCH}" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "unsupported OS: ${OS} (need Linux or Darwin)" >&2
    exit 1
    ;;
esac

ASSET="cue_v${VERSION}_${CUE_ARCH}.tar.gz"
URL="https://github.com/cue-lang/cue/releases/download/v${VERSION}/${ASSET}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

curl -fsSL -o "${WORKDIR}/${ASSET}" "${URL}"
EXPECTED="$(awk -v name="${ASSET}" '$2 == name { print $1 }' "${ROOT}/tools/cue.sha256")"
if [[ -z "${EXPECTED}" ]]; then
  echo "no pinned checksum for ${ASSET} in tools/cue.sha256" >&2
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum "${WORKDIR}/${ASSET}" | awk '{ print $1 }')"
else
  ACTUAL="$(shasum -a 256 "${WORKDIR}/${ASSET}" | awk '{ print $1 }')"
fi
if [[ "${ACTUAL}" != "${EXPECTED}" ]]; then
  echo "checksum mismatch for ${ASSET}" >&2
  echo "expected ${EXPECTED}" >&2
  echo "actual   ${ACTUAL}" >&2
  exit 1
fi

tar -xzf "${WORKDIR}/${ASSET}" -C "${WORKDIR}"
install -m 0755 "${WORKDIR}/cue" "${ROOT}/tools/cue"
"${ROOT}/tools/cue" version | grep -F "v${VERSION}"
