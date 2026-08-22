import os
import errno
import ctypes
import ctypes.util
import logging

log = logging.getLogger("kindle-hid-passthrough")

SBC_BITPOOL_DEFAULT = 53
PCM_BYTES_PER_SAMPLE = 4
SAMPLES_PER_FRAME = 16 * 8
FRAMES_PER_PACKET = 5
PCM_FRAME_SIZE = SAMPLES_PER_FRAME * PCM_BYTES_PER_SAMPLE
PCM_PACKET_SIZE = PCM_FRAME_SIZE * FRAMES_PER_PACKET

class SbcEncoder:
    def __init__(self, bitpool: int = SBC_BITPOOL_DEFAULT):
        self.bitpool = bitpool
        self._sbc_lib = None
        self._sbc_struct = None
        self._available = False
        self._init_libsbc()

    def _init_libsbc(self):
        try:
            lib_name = os.path.join(os.path.dirname(__file__), "libsbc.so.1")
            if not os.path.exists(lib_name):
                lib_name = "/mnt/us/kindle_hid_passthrough/libsbc.so.1"
            
            self._sbc_lib = ctypes.CDLL(lib_name)
            self._sbc_struct = ctypes.create_string_buffer(1024)
            self._sbc_lib.sbc_init.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self._sbc_lib.sbc_init.restype = ctypes.c_int
            
            self._sbc_lib.sbc_encode.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ssize_t)
            ]
            self._sbc_lib.sbc_encode.restype = ctypes.c_ssize_t
            
            ret = self._sbc_lib.sbc_init(self._sbc_struct, 0)
            if ret == 0:
                self._available = True
                log.info("[Audio] libsbc carregada com sucesso!")
        except Exception as e:
            log.warning(f"[Audio] libsbc não encontrada ({e}). Fallback de silêncio será usado.")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def encode_frame(self, pcm_chunk: bytes) -> bytes:
        if not self._available or len(pcm_chunk) < PCM_FRAME_SIZE:
            return None
        out_buf = ctypes.create_string_buffer(256)
        written = ctypes.c_ssize_t(0)
        res = self._sbc_lib.sbc_encode(
            self._sbc_struct, pcm_chunk, PCM_FRAME_SIZE, out_buf, 256, ctypes.byref(written)
        )
        if res > 0 and written.value > 0:
            return out_buf.raw[:written.value]
        return None

    def close(self):
        if self._available and self._sbc_lib:
            try:
                self._sbc_lib.sbc_finish(self._sbc_struct)
            except Exception:
                pass

class FifoAudioStreamer:
    def __init__(self, fifo_path: str = "/tmp/kindle_audio.fifo"):
        self.fifo_path = fifo_path
        self.fifo_fd = None
        self.pcm_buffer = bytearray()
        self.encoder = SbcEncoder()
        
        self.silence_sbc_frame = bytes([0x9C, 0xBD, 0x35, 0x00]) + bytes(115)
        self.silence_rtp_payload = bytes([FRAMES_PER_PACKET]) + (self.silence_sbc_frame * FRAMES_PER_PACKET)
        self._ensure_fifo()

    def _ensure_fifo(self):
        try:
            if not os.path.exists(self.fifo_path):
                os.mkfifo(self.fifo_path, 0o666)
        except Exception as e:
            log.error(f"[Audio] Erro ao criar FIFO {self.fifo_path}: {e}")

        try:
            self.fifo_fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
            log.info(f"[Audio] FIFO {self.fifo_path} aberta (FD={self.fifo_fd})")
        except Exception as e:
            log.error(f"[Audio] Falha ao abrir FIFO: {e}")

    def read_pcm_available(self):
        if self.fifo_fd is None:
            return
        
        try:
            while True:
                chunk = os.read(self.fifo_fd, 8192)
                if not chunk:
                    break
                self.pcm_buffer.extend(chunk)
                
                # Controle de latência e lag (máximo de 3 pacotes, ~43ms em buffer)
                if len(self.pcm_buffer) > PCM_PACKET_SIZE * 3:
                    pass # del self.pcm_buffer[:-PCM_PACKET_SIZE * 3]
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                log.warning(f"[Audio] Erro lendo FIFO: {e}")

    def get_next_payload(self) -> bytes:
        self.read_pcm_available()
        
        if len(self.pcm_buffer) >= PCM_PACKET_SIZE and self.encoder.is_available:
            raw_packet_pcm = bytes(self.pcm_buffer[:PCM_PACKET_SIZE])
            del self.pcm_buffer[:PCM_PACKET_SIZE]
            
            sbc_frames = []
            for i in range(FRAMES_PER_PACKET):
                pcm_chunk = raw_packet_pcm[i * PCM_FRAME_SIZE : (i + 1) * PCM_FRAME_SIZE]
                encoded = self.encoder.encode_frame(pcm_chunk)
                if encoded:
                    sbc_frames.append(encoded)
                else:
                    sbc_frames.append(self.silence_sbc_frame)
            return bytes([FRAMES_PER_PACKET]) + b"".join(sbc_frames)
        
        return self.silence_rtp_payload

    def close(self):
        if self.fifo_fd is not None:
            try:
                os.close(self.fifo_fd)
            except Exception:
                pass
            self.fifo_fd = None
        self.encoder.close()
