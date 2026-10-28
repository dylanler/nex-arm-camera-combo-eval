#!/usr/bin/env bash
# usage: ./r.sh read | ./r.sh move '{"shoulder_pan":2048}' [dur] | ./r.sh pos '[..6..]' [dur] | ./r.sh quit
# plus: ./r.sh snap  -> captures logitech + wrist JPEGs into snaps/
cd "$(dirname "$0")"
case "$1" in
  read) msg='{"cmd":"read"}' ;;
  move|pos) msg="{\"cmd\":\"move\",\"pos\":$2,\"dur\":${3:-2.0}}" ;;
  quit) msg='{"cmd":"quit"}' ;;
  snap)
    mkdir -p snaps; ts=$(date +%H%M%S)
    ffmpeg -hide_banner -loglevel error -f avfoundation -pixel_format bgr0 -framerate 30 -video_size 640x480 -i "C922 Pro Stream Webcam:none" -vf "select=gte(n\,8)" -frames:v 1 -y snaps/${ts}_top.jpg &
    ffmpeg -hide_banner -loglevel error -f avfoundation -pixel_format bgr0 -framerate 30 -video_size 640x480 -i "icspring camera:none" -vf "select=gte(n\,8)" -frames:v 1 -y snaps/${ts}_wrist.jpg &
    wait; echo snaps/${ts}_top.jpg snaps/${ts}_wrist.jpg; exit ;;
esac
python3 - "$msg" <<'EOF'
import socket,sys
s=socket.create_connection(("127.0.0.1",8799)); s.sendall((sys.argv[1]+"\n").encode())
print(s.makefile().readline().strip())
EOF
