# Kindle HID Passthrough

Userspace Bluetooth HID host for Kindle with UHID passthrough.

## Scope of the KOReader plugin

`hidpassthrough.koplugin` handles the easy input cases only, meaning it opens the evdev node nothing else adopts and lets plain EV_KEY presses reach KOReader bindings.

The hard cases belong in kindle-button-mapper, not here. That covers EV_ABS translation (D-pad hat axes, analog sticks), joystick mapping and keyboard layouts.

This project does Bluetooth and produces a proper evdev node, the mapper gives the buttons meaning, and both stay usable alone.

## SSH Configuration

The Kindle is accessed via SSH using the host alias `kindle`.

## Keep Awake During Development

Stop the Kindle from sleeping/screensaving while developing on it:

```bash
ssh kindle "lipc-set-prop -i com.lab126.powerd preventScreenSaver 1"   # keep awake
ssh kindle "lipc-set-prop -i com.lab126.powerd preventScreenSaver 0"   # restore
```

Verify with `ssh kindle "lipc-get-prop com.lab126.powerd status"` (look for `prevent_screen_saver:1`).

## Deployment

Use `just` commands for all deployment and management:

```bash
just deploy       # Deploy files to Kindle
just restart      # Restart daemon
just ssh          # SSH into Kindle
```

## Daemon Management

```bash
just start        # Start daemon
just stop         # Stop daemon
just restart      # Restart daemon
just status       # Check daemon status
```

## Logs

```bash
just logs         # Follow daemon logs (tail -f)
just logs-recent  # Show last 50 lines
```

## Local Development

```bash
just check        # Check Python syntax
```

## Cache Management

```bash
just clear-cache  # Clear descriptor cache
just show-cache   # Show cached device data
```

## File Locations on Kindle

- Code: `/mnt/us/kindle_hid_passthrough/`
- Upstart config: `/etc/upstart/hid-passthrough.conf`
- Logs: `/var/log/hid_passthrough.log`
- Device config: `/mnt/us/kindle_hid_passthrough/devices.conf`
- Pairing keys: `/mnt/us/kindle_hid_passthrough/cache/pairing_keys.json`

## Manual System File Installation

### udev rules

```bash
cd /mnt/us/kindle_hid_passthrough
mntroot rw
cp assets/99-hid-keyboard.rules /etc/udev/rules.d
udevadm control --reload-rules
mntroot ro
```

### BTManager WAF app (dev install)

```bash
sh /mnt/us/kindle_hid_passthrough/illusion/install-waf-app.sh
```

## Autostart (Upstart)

The Kindle uses Upstart for service management. Two upstart configs are available:

- `hid-passthrough.upstart` - For binary releases (runs compiled binary)
- `hid-passthrough-dev.upstart` - For development (runs Python script)

The `just deploy` command installs the dev version. Binary releases include the production version.

```bash
just remove-autostart  # Disable autostart (removes upstart config)
```

## A2DP Audio Passthrough (ALSA -> SBC)

### O que foi feito
Implementamos um hack agressivo no sistema de áudio nativo do Kindle para capturar qualquer som tocado no aparelho e redirecioná-lo para os fones de ouvido Bluetooth conectados pelo nosso daemon (já que tomamos controle exclusivo da interface `hci0`, cegando o sistema original da Amazon).

### Como foi feito
1. **ALSA Hijack (`/etc/asound.conf`)**: Sobrescrevemos os dispositivos `pcm.!default` e `pcm.dmix0` no Kindle usando os plugins `plug` e `file` do ALSA. Qualquer áudio tocado no sistema (ex: via `aplay`) é forçadamente reamostrado para **44100 Hz, Stereo, S16_LE** e despejado continuamente em um arquivo FIFO (pipe) em `/tmp/kindle_audio.fifo`.
2. **Leitura Assíncrona (`audio_pipe.py`)**: O nosso daemon lê esse pipe continuamente (buffering instantâneo do tipo *bit-bucket* do ALSA nulo) sem bloquear o clock do sistema, armazenando o PCM bruto em memória.
3. **Encoding SBC (`libsbc.so.1`)**: Usamos `ctypes` para invocar a biblioteca de compressão C nativa. Corrigimos um bug crítico de áudio metálico/sintetizador alterando diretamente a memória da `sbc_struct` no Python para forçar o modo **Joint Stereo (0x03)** e **44.1kHz (0x02)**, batendo perfeitamente com a negociação AVDTP que o Bumble faz com os fones de ouvido.
4. **Streaming AVDTP (`host.py`)**: O PCM é fatiado (5 frames por pacote), comprimido para SBC, envelopado como payload RTP, e injetado na conexão A2DP de forma assíncrona. Se não houver áudio tocando, o daemon envia frames de silêncio sintéticos pré-calculados para manter os fones acordados.
5. **KOReader Audiobook Plugin (Fork)**: Como o plugin original tentava usar a infraestrutura da Amazon (`gst-launch` -> `mixersink` -> `audiomgrd`), ele travava por timeout pois a antena BT nativa estava morta. Modificamos o plugin para simplesmente usar o `aplay` padrão do Linux, que cai perfeitamente no nosso cano do ALSA.
