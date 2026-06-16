# Offline Kurulum (İnternet Erişimi Olmayan Sunucu)

Bu klasör, SBM Migration aracının çalışması için gereken tüm Python bağımlılıklarının
`.whl` (wheel) paketlerini içerir. İnternet erişimi olmayan (air-gapped) sunucularda
kurulum bu paketlerden yapılır.

## İçerik

| Paket | Sürüm | Kullanım |
|-------|-------|----------|
| `openpyxl` | 3.1.5 | Excel okuma/yazma (Part 1 & 2) |
| `requests` | 2.34.2 | BeyondTrust REST API (Part 2) |
| `et_xmlfile` | 2.0.0 | openpyxl bağımlılığı |
| `charset_normalizer` | 3.4.7 | requests bağımlılığı |
| `idna` | 3.18 | requests bağımlılığı |
| `urllib3` | 2.7.0 | requests bağımlılığı |
| `certifi` | 2026.5.20 | requests bağımlılığı (TLS sertifikaları) |

## ⚠️ Platform / Python Sürümü Uyumu

Bu paketler şu ortam için indirilmiştir:

- **İşletim sistemi:** Windows (64-bit / `win_amd64`)
- **Python sürümü:** 3.14 (cp314)

> Çoğu paket platformdan bağımsızdır (`py3-none-any`), ancak
> `charset_normalizer-3.4.7-cp314-cp314-win_amd64.whl` Windows + Python 3.14'e
> özeldir. Hedef sunucuda **farklı bir işletim sistemi veya Python sürümü** varsa,
> bu klasördeki paketleri internet erişimi olan bir makinede yeniden indirin
> (en alttaki "Paketleri Yeniden İndirme" bölümüne bakın).

## Kurulum Adımları

### 1. Projeyi sunucuya kopyalayın
Tüm proje klasörünü (`offline_packages` dahil) hedef sunucuya taşıyın.

### 2. (Önerilir) Sanal ortam oluşturun
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS için:
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Paketleri offline kurun
Proje kök dizininde (SBM klasörü) şu komutu çalıştırın:

```powershell
pip install --no-index --find-links offline_packages -r requirements.txt
```

Açıklama:
- `--no-index` → PyPI'a (internete) bağlanmayı tamamen kapatır.
- `--find-links offline_packages` → paketleri yalnızca bu klasörden arar.

### 4. Kurulumu doğrulayın
```powershell
python -c "import openpyxl, requests; print('OK', openpyxl.__version__, requests.__version__)"
```

Çıktı `OK 3.1.5 2.34.2` benzeri ise kurulum başarılıdır.

---

## Paketleri Yeniden İndirme (Hedef ortam farklıysa)

İnternet erişimi **olan** bir makinede, hedef sunucuyla aynı işletim sistemi ve
Python sürümünü kullanarak:

```powershell
pip download -r requirements.txt -d offline_packages
```

Hedef ortam farklı bir platformsa (örn. internetli makine Windows ama sunucu Linux),
platformu belirterek indirin:

```bash
pip download -r requirements.txt -d offline_packages \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --only-binary=:all:
```

Ardından `offline_packages` klasörünü hedef sunucuya kopyalayıp yukarıdaki
kurulum adımlarını uygulayın.
