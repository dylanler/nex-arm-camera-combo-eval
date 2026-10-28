#!/usr/bin/env bash
# Grab one frame from each camera: snap.sh [prefix] [cams...]  (cams: wrist realsense logitech)
cd "$(dirname "$0")"; mkdir -p snaps
P=${1:-s}; shift
CAMS=${@:-wrist realsense logitech}
for c in $CAMS; do
  case $c in
    wrist) n="icspring camera";;
    realsense) n="Intel(R) RealSense(TM) Depth Camera 415  RGB";;
    logitech) n="C922 Pro Stream Webcam";;
  esac
  ffmpeg -hide_banner -loglevel error -y -f avfoundation -framerate 30 -video_size 640x480 -i "$n" -vf "select=gte(n\,8)" -frames:v 1 snaps/${P}_$c.jpg &
done
wait
ls snaps/${P}_*
