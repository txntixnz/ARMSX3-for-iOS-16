#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$1" && pwd)"
install_dir="$2"
mkdir -p "$install_dir"
install_dir="$(cd "$install_dir" && pwd)"
# FFmpeg 8.0: same libavcodec ABI major (62) as pinned upstream headers.
expected=140fd653aed8cad774f991ba083e2d01e86420c7
test "$(git -C "$source_dir" rev-parse HEAD)" = "$expected"
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
cc="$(xcrun --sdk iphoneos --find clang)"
cd "$source_dir"
./configure --prefix="$install_dir" --target-os=darwin --arch=aarch64 \
  --enable-cross-compile --sysroot="$sdk" --cc="$cc" \
  --extra-cflags="-target arm64-apple-ios16.0 -mcpu=apple-a15" \
  --extra-ldflags="-target arm64-apple-ios16.0 -isysroot $sdk" \
  --enable-static --disable-shared --enable-pic --disable-programs \
  --disable-doc --disable-debug --disable-autodetect --disable-network \
  --disable-everything --disable-avdevice --disable-avfilter \
  --enable-decoder=aac,aac_latm,atrac3,atrac3p,atrac9,mp3,pcm_s16le,pcm_s8,h264,mpeg4,mpeg2video,mjpeg,mjpegb \
  --enable-encoder=pcm_s16le,ac3,aac,ffv1,mpeg4,mjpeg \
  --enable-muxer=avi,h264,mjpeg,mp4 \
  --enable-demuxer=h264,m4v,mp3,mpegvideo,mpegps,mjpeg,mov,avi,aac,pmp,oma,pcm_s16le,pcm_s8,wav \
  --enable-parser=h264,mpeg4video,mpegaudio,mpegvideo,mjpeg,aac,aac_latm \
  --enable-protocol=file --enable-bsf=mjpeg2jpeg
make -j3
make install
