# YaxshiLink Device Client

Asinxron Python mijoz dasturi: Arduino va Scanner bilan serial orqali ishlaydi, API/WS orqali server bilan muloqot qiladi. macOS (launchd) va Raspberry Pi/Linux (systemd) uchun auto-start qo'llab-quvvatlanadi. Ushbu hujjat to'liq o'rnatish va foydalanish bo'yicha ko'rsatmalarni o'z ichiga oladi.

## Talablar

- Python 3.10+ (macOS yoki Raspberry Pi OS / Linux)
- Internet ulanishi (API/WS uchun)
- Qurilmalar: Arduino va Barcode Scanner (USB orqali)

## Tez start (har ikkala OS uchun)

1. Setup (venv, kutubxonalar, config, va ixtiyoriy auto-start):

```sh
python3 install.py setup
```

2. Xizmat boshqaruvi (ixtiyoriy):

```sh
python3 install.py service-install   # Auto-start o'rnatish
python3 install.py service-status    # Holatni ko'rish
python3 install.py service-restart   # Qayta ishga tushirish
python3 install.py service-remove    # O'chirish
```

3. Qo'lda ishga tushirish (foreground):

```sh
python3 install.py run
```

## CLI qo'llanma

Hammasi `install.py` orqali boshqariladi.

### Setup va portlar

- `setup` — virtual muhitni (agar bo'lsa) o'chirib, yangidan yaratadi; `requirements.txt` ni o'rnatadi; config sozlamalarini interaktiv so'raydi; OS'ga mos auto-start xizmatini o'rnatishni taklif qiladi.
- `ports` — tizimdagi mavjud serial portlarni chiqaradi.

Misollar:

```sh
python3 install.py setup
python3 install.py ports
```

### Config boshqaruvi

- `config-show` — joriy sozlamalarni ko'rsatadi (config.json).
- `config-edit` — interaktiv tarzda qayta sozlaydi (WS URL, FANDOMAT_ID, DEVICE_TOKEN, BAUDRATE, Arduino/Scanner portlari).
- `config-set` — parametrlar orqali o'rnatadi:

```sh
python3 install.py config-show
python3 install.py config-edit
python3 install.py config-set \
	--ws-url wss://api.yaxshi.link/ws/fandomats \
	--fandomat-id 3 \
	--device-token fnd_xxx... \
	--arduino-port /dev/ttyACM0 \
	--scanner-port /dev/ttyUSB0 \
	--baudrate 9600 \
	--log-dir logs \
	--version 1.0.0
```

`config.json` maydonlari:

- `ws_url`: WebSocket endpoint (masalan: `wss://api.yaxshi.link/ws/fandomats`).
- `fandomat_id`: Qurilma ID (raqam).
- `device_token`: Qurilma tokeni (admin paneldan olinadi).
- `version`: Dastur/firmware versiyasi (masalan: `1.0.0`).
- `arduino_port`, `scanner_port`: Serial portlar.
- `baudrate`: Odatda 9600.
- `log_dir`: Loglar papkasi (`logs`).

### Xizmat (auto-start) boshqaruvi

OS avtomatik aniqlanadi: macOS — launchd, Linux/RPi — systemd.

```sh
python3 install.py service-install
python3 install.py service-status
python3 install.py service-start
python3 install.py service-stop
python3 install.py service-restart
python3 install.py service-remove
```

Joylashuvlar:

- macOS plist: `~/Library/LaunchAgents/com.yaxshilink.device.plist`
- Linux unit: `/etc/systemd/system/yaxshilink.service`
- Service loglar: `logs/service.out.log`, `logs/service.err.log`

### Dasturni ishga tushirish

- Foreground (interaktiv log bilan):

```sh
python3 install.py run
```

- Bevosita (venv ni qo'lda faollashtirib):

```sh
. ./.venv/bin/activate
python main.py
```

### Test va diagnostika

Oddiy sinovlar:

```sh
python3 install.py test-arduino    # Arduino portini ochish testi
python3 install.py test-scanner    # Scanner portini ochish testi
python3 install.py listen-scanner  # Scanner portidan xom oqimni ko'rish
python3 install.py logs --lines 200
python3 install.py test-ws         # WSga ulanish va HELLO testi
python3 install.py monitor         # Interaktiv monitoring (scanner/WS/session)
```

### Serial portlar bo'yicha eslatmalar

- macOS: odatda `/dev/cu.*` yoki `/dev/tty.*` (ko'pincha `cu` ishlatiladi).
- Linux/Raspberry Pi: odatda `/dev/ttyUSB*`, `/dev/ttyACM*`, ba'zan `/dev/serial0`.
- RPi/Linux’da foydalanuvchi `dialout` guruhida bo‘lishi kerak (aks holda serialga ruxsat bo‘lmaydi). Agar kerak bo‘lsa:

```sh
sudo usermod -a -G dialout $USER
newgrp dialout
```

### Muammolar va yechimlar (Troubleshooting)

- Serialga ruxsat yo'q: foydalanuvchini `dialout` ga qo‘shing (Linux), yoki macOS’da port nomlarini tekshiring.
- Scanner o‘qimayapti:
  - Scanner HID (Keyboard) rejimda emas, balki USB-COM/Serial (CDC-ACM) rejimda ekanini tekshiring.
  - `config.json` dagi `scanner_port` to‘g‘ri tanlanganiga ishonch hosil qiling (ko‘pincha Arduino = `/dev/ttyACM0`, Scanner = `/dev/ttyUSB0`).
  - Scanner’da suffix sifatida CR yoki LF yoqilgan bo‘lishi kerak. Biz CR/LF ikkalasini ham qabul qilamiz; bo‘lmasa timeout bo‘yicha flush ishlaydi.
  - Debug uchun xom baytlarni logga yozish: muhit o‘zgaruvchisi `YL_DEBUG_SCANNER=1` bilan ishga tushiring.
- `python3-venv` topilmadi (Linux): `setup` bu paketni o'rnatishni taklif qiladi; `sudo apt-get install -y python3-venv` orqali ham o‘rnating.
- Xizmat ishga tushmadi:
  - Holatni tekshiring: `python3 install.py service-status`
  - Loglar: `python3 install.py logs --lines 200`
  - Linux’da qoʻshimcha: `journalctl -u yaxshilink.service -e` (ixtiyoriy)
- Portlar ro‘yxatda ko‘rinmadi: qurilmalarni qayta ulab ko‘ring, drayverlar va kabellarni tekshiring.

## Tuzilma

- `app/config.py` — Konfiguratsiya va URL-lar
- `app/logger.py` — Session/system loglar
- `app/state.py` — Runtime holat
- `app/arduino.py` — Arduino ulanishi va listener
- `app/scanner.py` — Scanner ulanishi va listener
- `app/ws_client.py` — WebSocket sessiya boshqaruvi
- `app/app_main.py` — Orkestratsiya
- `main.py` — Minimal entrypoint
- `install.py` — Venv, config va auto-start (macOS launchd, Linux systemd)

## Loglar

- `logs/system.log` — tizimiy loglar
- `logs/session_<id>.log` — har bir sessiya uchun loglar
- Xizmat loglari: `logs/service.out.log`, `logs/service.err.log`

## Yangilash va o'chirish

- Yangilash: kodni yangilang, so‘ng `python3 install.py setup` (venv qayta yaratiladi) yoki faqat `requirements.txt` o‘zgargan bo‘lsa, `.venv` ichida `pip install -r requirements.txt`.
- Xizmatni olib tashlash: `python3 install.py service-remove`.
