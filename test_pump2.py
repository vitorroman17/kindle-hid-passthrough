import inspect
from bumble.avdtp import MediaPacketPump
from bumble.a2dp import SbcPacketSource
print("MediaPacketPump:", inspect.signature(MediaPacketPump.__init__))
print("SbcPacketSource:", inspect.signature(SbcPacketSource.__init__))
