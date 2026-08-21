import sys
sys.path.append("/config/.local/lib/python3.12/site-packages")
import bumble.avdtp
import bumble.a2dp
print(dir(bumble.avdtp.MediaPacketPump))
print(dir(bumble.a2dp.SbcPacketSource))
