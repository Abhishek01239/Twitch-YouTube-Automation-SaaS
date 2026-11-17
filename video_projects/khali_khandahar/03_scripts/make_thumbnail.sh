#!/bin/bash
# YouTube thumbnail (1280x720) from the "found in the corner" frame, with title text from the creator's own logline.
P="$1"; F="$P/04_assets/fonts"
ffmpeg -y -v error -ss 790.8 -i "$P/01_source/original_cloudinary_360p.mp4" -frames:v 1 -vf "\
hqdn3d=2:2:3:3,scale=1280:720:flags=lanczos,unsharp=5:5:0.8,\
eq=contrast=1.18:saturation=0.75:gamma=0.95,colorbalance=rs=-0.05:bs=0.08:rh=0.06,\
vignette=angle=PI/3.2,\
drawbox=x=0:y=0:w=1280:h=210:color=black@0.55:t=fill,\
drawtext=fontfile=$F/InterDisplay-Black.otf:text='KHALI KHANDAHAR':fontsize=118:fontcolor=white:x=(w-tw)/2:y=34:borderw=6:bordercolor=0x8B0000,\
drawtext=fontfile=$F/InterDisplay-SemiBold.otf:text='NO LIVING SOUL REMAINS':fontsize=44:fontcolor=0xFF3B3B:x=(w-tw)/2:y=160:borderw=2:bordercolor=black" \
"$P/06_final/Thumbnail.jpg"
