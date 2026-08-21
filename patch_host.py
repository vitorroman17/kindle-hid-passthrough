from pathlib import Path
import re

p = Path("kindle_hid_passthrough/host.py")
c = p.read_text()

# 1. Fix CoD
c = c.replace('class_of_device = 0x000104', 'class_of_device = 0x200104')

# 2. Remove dead code in start()
dead_code = """
            # Setup SBC capabilities
            codec_caps = MediaCodecCapabilities(
                media_type=AVDTP_AUDIO_MEDIA_TYPE,
                media_codec_type=A2DP_SBC_CODEC_TYPE,
                media_codec_information=SbcMediaCodecInformation(
                    sampling_frequency=SbcMediaCodecInformation.SamplingFrequency.SF_44100,
                    channel_mode=SbcMediaCodecInformation.ChannelMode.JOINT_STEREO,
                    block_length=SbcMediaCodecInformation.BlockLength.BL_16,
                    subbands=SbcMediaCodecInformation.Subbands.S_8,
                    allocation_method=SbcMediaCodecInformation.AllocationMethod.LOUDNESS,
                    minimum_bitpool_value=2,
                    maximum_bitpool_value=53,
                ),
            )
            
            # We will just add the capabilities to the listener later, 
            # or when a connection arrives. For now, just register SDP."""

c = c.replace(dead_code, "")

# 3. Add done_callback for fail fast in audio pump
pump_code = """        # Track the task properly
        session.audio_pump_task = self._track_task(asyncio.create_task(pump.start(stream.send_media_packet)))"""
        
new_pump_code = """        # Track the task properly
        session.audio_pump_task = self._track_task(asyncio.create_task(pump.start(stream.send_media_packet)))
        
        def pump_done(task):
            try:
                task.result()
                log.warning("Audio pump stopped unexpectedly.")
            except Exception as e:
                log.error(f"Audio pump crashed: {e!r}")
            # Fail fast
            import os, signal
            os.kill(os.getpid(), signal.SIGTERM)
            
        session.audio_pump_task.add_done_callback(pump_done)"""

c = c.replace(pump_code, new_pump_code)

p.write_text(c)
