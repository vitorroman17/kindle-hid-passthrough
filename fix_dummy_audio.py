import re
from pathlib import Path

host_file = Path("kindle_hid_passthrough/host.py")
content = host_file.read_text()

# We need to replace the _continue_classic_audio_after_pairing function
import ast

def get_function_body():
    return """
    async def _continue_classic_audio_after_pairing(self, session):
        from bumble.avdtp import Protocol, LocalSource, StreamEndPointType, State, MediaPacketPump, RealtimeClock
        from bumble.rtp import MediaPacket
        import time

        log.info("[Classic] Audio device connected. Initiating AVDTP...")
        
        from bumble.avdtp import MediaCodecCapabilities, AVDTP_AUDIO_MEDIA_TYPE
        from bumble.a2dp import A2DP_SBC_CODEC_TYPE, SbcMediaCodecInformation
        
        # We reuse the capabilities
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
        
        source = LocalSource([codec_caps])

        avdtp_protocol = None
        if self.a2dp_listener.servers.get(session.connection.handle):
            avdtp_protocol = self.a2dp_listener.servers[session.connection.handle]
            log.info("AVDTP already connected by remote")
        else:
            try:
                log.info("Connecting AVDTP to remote...")
                avdtp_protocol = await Protocol.connect(session.connection)
                self.a2dp_listener.set_server(session.connection, avdtp_protocol)
            except Exception as e:
                log.error(f"Failed to connect AVDTP: {e}")
                return

        avdtp_protocol.add_source(source)

        endpoints = await avdtp_protocol.discover_remote_endpoints()
        sink_endpoint = next((e for e in endpoints if e.tsep == StreamEndPointType.SINK), None)
        if not sink_endpoint:
            log.error("No AVDTP SINK endpoints found on remote")
            return

        log.info(f"Found remote SINK endpoint: {sink_endpoint.seid}")
        
        stream = await avdtp_protocol.create_stream(source, sink_endpoint)
        log.info("Configured stream. Opening...")
        
        await stream.open()
        log.info("Stream opened. Starting...")
        
        await stream.start()
        log.success("[Classic Audio] AVDTP streaming started! Injecting silence...")

        # 44.1kHz, JS, 16 blocks, 8 subbands, bitpool 53 -> 119 bytes per frame
        # SBC Syncword = 0x9C. sf_cm_am = 0xBD. bitpool = 0x35. CRC = 0x00.
        # We will use dummy zeros for the rest of the frame.
        # The headset may drop it due to bad CRC, but it will keep the connection alive.
        sbc_frame = bytes([0x9C, 0xBD, 0x35, 0x00]) + bytes(115)
        
        # We put 5 frames per RTP packet to reduce overhead (5 * 2.9ms = 14.5ms per packet)
        frames_per_packet = 5
        # A2DP SBC Media Payload Header:
        # bit 7: Fragment=0, bit 6: Start=0, bit 5: Last=0, bit 4: RFA=0, bits 0-3: number of frames (5)
        media_payload_header = bytes([frames_per_packet])
        rtp_payload = media_payload_header + (sbc_frame * frames_per_packet)
        
        samples_per_frame = 16 * 8  # 128
        samples_per_packet = samples_per_frame * frames_per_packet

        async def packet_generator():
            seq = 0
            ts = 0
            while stream.state == State.STREAMING:
                packet = MediaPacket(
                    version=2, padding=0, extension=0, marker=0,
                    sequence_number=seq, timestamp=ts, ssrc=0,
                    csrc_list=[], payload_type=96, payload=rtp_payload
                )
                yield packet
                seq = (seq + 1) & 0xFFFF
                ts = (ts + samples_per_packet) & 0xFFFFFFFF

        pump = MediaPacketPump(packet_generator(), RealtimeClock(44100))
        
        # Track the task properly
        session.audio_pump_task = self._track_task(asyncio.create_task(pump.start(stream.send_media_packet)))
"""

start_idx = content.find("    async def _continue_classic_audio_after_pairing")
end_idx = content.find("    # ==================== COMMON ====================")

content = content[:start_idx] + get_function_body() + "\n" + content[end_idx:]

with open("kindle_hid_passthrough/host.py", "w") as f:
    f.write(content)
