from pathlib import Path
p = Path("kindle_hid_passthrough/classic.py")
c = p.read_text()

conflict = """<<<<<<< HEAD
        if is_peripheral and not channels.intr_channel:
=======
        if session.protocol == Protocol.CLASSIC_AUDIO:
            log.info("[Classic] Audio device connected. Letting AVDTP listener take over.")
            log.success(f"[Classic] {self._format_device(session.address)} connected (Audio)")
            return

        # In HID over BR/EDR the Device opens both channels toward the Host.
        # Paging outward races that, and every peer measured opened them
        # within 250 ms, so a short wait costs less than the collision does.
        if (peer_driving or is_peripheral) and not channels.intr_channel:
>>>>>>> af747d7 (feat: Add AVDTP/A2DP source infrastructure)"""

resolution = """        if session.protocol == Protocol.CLASSIC_AUDIO:
            log.info("[Classic] Audio device connected. Letting AVDTP listener take over.")
            log.success(f"[Classic] {self._format_device(session.address)} connected (Audio)")
            return

        if is_peripheral and not channels.intr_channel:"""

c = c.replace(conflict, resolution)
p.write_text(c)
