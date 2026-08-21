#!/usr/bin/env bash
#
# Build local do binario ARMv7 para o Kindle.
#
# Usa o MESMO ambiente do CI: estagio `builder-env` de .github/Dockerfile.arm
# (Debian bookworm armhf, bumble corrigido pelo patch, CFLAGS/LDFLAGS de ARM).
# A unica diferenca e que a arvore de fontes entra por bind mount em vez de
# COPY, entao iterar nao reconstroi a imagem.
#
# Saida e caches ficam em volumes Docker, nunca em /mnt/c: o Nuitka gera dezenas
# de milhares de arquivos pequenos e o drvfs/9p do WSL cobra caro por cada um.
#
# LTO fica desligado por padrao. Em host x86_64 o armhf roda sob QEMU e o lto1
# de 32 bits estoura o address space (`--jobs=N` vira `-flto=N`, N processos
# lto1 simultaneos). O CI nao tem esse problema: ubuntu-24.04-arm roda armhf
# nativo. Para reproduzir o artefato do CI localmente: LTO=yes JOBS=4 ./build-local.sh
#
# Uso:
#   scripts/build-local.sh              # compila (loop rapido)
#   scripts/build-local.sh --out        # compila e extrai main.dist para nuitka-out/local.dist
#   scripts/build-local.sh --full       # artefato completo, identico ao CI (imagem inteira)
#   scripts/build-local.sh --clean      # zera caches e saida
#   LTO=yes JOBS=4 scripts/build-local.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_ENV="kindle-hid-passthrough-builder-env"
IMAGE_FULL="kindle-hid-passthrough-builder"
CONTAINER="kindle-builder"
VOL_NUITKA="kindle-nuitka-cache"
VOL_CCACHE="kindle-ccache"
VOL_OUT="kindle-nuitka-out"
PLATFORM="linux/arm/v7"

JOBS="${JOBS:-$(nproc)}"
LTO="${LTO:-no}"
DO_OUT=0
DO_FULL=0
DO_CLEAN=0

for arg in "$@"; do
    case "$arg" in
        --out)   DO_OUT=1 ;;
        --full)  DO_FULL=1 ;;
        --clean) DO_CLEAN=1 ;;
        -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "argumento desconhecido: $arg" >&2; exit 2 ;;
    esac
done

log() { printf '\n== %s\n' "$*"; }

cd "$REPO"

# BUILD_SHA: mesmo carimbo que o CI aplica, consumido por config.py:33.
git rev-parse --short HEAD > kindle_hid_passthrough/BUILD_SHA 2>/dev/null || echo unknown > kindle_hid_passthrough/BUILD_SHA
log "BUILD_SHA=$(cat kindle_hid_passthrough/BUILD_SHA)"

if [ "$DO_CLEAN" = 1 ]; then
    log "Removendo caches e saida"
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker volume rm -f "$VOL_NUITKA" "$VOL_CCACHE" "$VOL_OUT" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------- modo --full
if [ "$DO_FULL" = 1 ]; then
    log "Build completo (estagio final de Dockerfile.arm, identico ao CI)"
    docker build --platform "$PLATFORM" -f .github/Dockerfile.arm -t "$IMAGE_FULL" .
    out="$REPO/nuitka-out/local-release"
    rm -rf "$out"; mkdir -p "$out/dist" "$out/scripts"
    cid="$(docker create --platform "$PLATFORM" "$IMAGE_FULL")"
    trap 'docker rm "$cid" >/dev/null 2>&1 || true' EXIT
    # Espelha o passo "Extract binaries" de .github/workflows/build-arm.yml.
    # Se aquele passo mudar, este precisa mudar junto.
    docker cp "$cid:/build/kindle-hid-passthrough"   "$out/kindle-hid-passthrough"
    docker cp "$cid:/build/libsyscall_wrapper.so"    "$out/libsyscall_wrapper.so"
    docker cp "$cid:/build/nuitka-out/main.dist/."   "$out/dist/"
    docker cp "$cid:/build/mousecursor"              "$out/scripts/mousecursor"
    chmod +x "$out/kindle-hid-passthrough" "$out/dist/main.bin" \
             "$out/dist/ld-linux-armhf.so.3" "$out/scripts/mousecursor"
    log "Artefato completo em nuitka-out/local-release/"
    du -sh "$out"
    exit 0
fi

# ------------------------------------------------- ambiente de build (builder-env)
log "Preparando imagem $IMAGE_ENV (estagio builder-env)"
docker build --platform "$PLATFORM" -f .github/Dockerfile.arm --target builder-env -t "$IMAGE_ENV" .

for v in "$VOL_NUITKA" "$VOL_CCACHE" "$VOL_OUT"; do
    docker volume inspect "$v" >/dev/null 2>&1 || docker volume create "$v" >/dev/null
done

# Recria o container so quando a imagem mudou. Os caches vivem nos volumes,
# entao recriar nao custa recompilacao.
want="$(docker image inspect "$IMAGE_ENV" --format '{{.Id}}')"
have="$(docker inspect "$CONTAINER" --format '{{.Image}}' 2>/dev/null || echo none)"
if [ "$want" != "$have" ]; then
    log "Recriando container $CONTAINER"
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$CONTAINER" --platform "$PLATFORM" \
        -v "$REPO:/workspace" \
        -v "$VOL_NUITKA:/nuitka-cache" \
        -v "$VOL_CCACHE:/ccache" \
        -v "$VOL_OUT:/nuitka-out" \
        -w /workspace \
        --entrypoint sleep "$IMAGE_ENV" infinity >/dev/null
fi
docker start "$CONTAINER" >/dev/null 2>&1 || true

# ------------------------------------------------------------------- compilar
log "Nuitka: jobs=$JOBS lto=$LTO"
docker exec "$CONTAINER" python3 -m nuitka \
    --mode=standalone \
    --jobs="$JOBS" \
    --lto="$LTO" \
    --assume-yes-for-downloads \
    --output-dir=/nuitka-out \
    --include-data-file=kindle_hid_passthrough/config.ini=kindle_hid_passthrough/config.ini \
    --include-data-file=kindle_hid_passthrough/BUILD_SHA=kindle_hid_passthrough/BUILD_SHA \
    --include-data-dir=kindle_hid_passthrough/modules=kindle_hid_passthrough/modules \
    --nofollow-import-to=pytest \
    --nofollow-import-to=unittest \
    --nofollow-import-to=setuptools \
    --nofollow-import-to=grpc \
    --nofollow-import-to=google \
    --nofollow-import-to=usb \
    --report=/nuitka-out/compilation-report.xml \
    kindle_hid_passthrough/main.py

log "Resultado"
docker exec "$CONTAINER" sh -c 'ls -la /nuitka-out/main.dist/main.bin; echo "objetos: $(ls /nuitka-out/main.build/*.o | wc -l)"'
docker exec "$CONTAINER" sh -c 'CCACHE_DIR=/ccache ccache -s | head -6'

if [ "$DO_OUT" = 1 ]; then
    log "Extraindo main.dist para nuitka-out/local.dist/"
    rm -rf "$REPO/nuitka-out/local.dist"
    mkdir -p "$REPO/nuitka-out/local.dist"
    docker cp "$CONTAINER:/nuitka-out/main.dist/." "$REPO/nuitka-out/local.dist/"
    du -sh "$REPO/nuitka-out/local.dist"
else
    log "main.dist ficou no volume $VOL_OUT (use --out para extrair)"
fi
