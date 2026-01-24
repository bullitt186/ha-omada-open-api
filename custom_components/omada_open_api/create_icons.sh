#!/bin/bash
# Create simple placeholder icons for Bronze tier compliance
# These should be replaced with actual TP-Link Omada branding

# Create a simple 256x256 icon.png (TP-Link themed)
convert -size 256x256 xc:white \
  -fill "#009FD9" -draw "circle 128,128 128,200" \
  -fill white -draw "circle 128,128 128,170" \
  -fill "#009FD9" -draw "circle 128,128 128,140" \
  -fill white -pointsize 40 -gravity center -annotate +0+0 "OMADA" \
  icon.png

# Create a simple 256x128 logo.png (wide format)
convert -size 256x128 xc:white \
  -fill "#009FD9" -draw "roundrectangle 10,20 246,108 10,10" \
  -fill white -pointsize 30 -gravity center -annotate +0+0 "TP-Link Omada" \
  logo.png

# Create @2x versions
convert icon.png -resize 512x512 icon@2x.png
convert logo.png -resize 512x256 logo@2x.png

echo "Icon files created successfully"
