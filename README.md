# BeyondTrust SBM Migration

CyberArk envanterini **BeyondTrust Password Safe**'e taşıyan migration aracı (quasys).
CyberArk safe/kullanıcı yapısını ve sunucu envanterini okuyup BeyondTrust üzerinde
kullanıcı grubu, kullanıcı, managed system, managed account, smart rule ve
yetkilendirmeleri **idempotent** (tekrar tekrar çalıştırılabilir) şekilde oluşturur.

## Akış

| Aşama | Ne yapar | Giriş |
|-------|----------|-------|
| PART 1 | `PamEnvanter.xlsx` × `OsEnvanter.xlsx` korelasyonu → `output/Working.xlsx` | `main.py` |
| PART 2 | safe name → UserGroup → User → Membership | `migrate.py` |
| PART 3 | Managed System → Managed Account (+Link / local) | `migrate.py` |
| PART 4 | Smart Rule → UG yetkilendirme → Role + Access Policy | `migrate.py` |
| Temizlik | Yalnızca bu aracın oluşturduğu nesneleri siler | `delete.py` |

Her satır `type` kolonuna göre **AD** (domain MS + link) veya **LOCAL** (kendi sistemi, link yok)
sürecine yönlendirilir. Adımlar **sıkı zincirle** çalışır (bir üst adım başarısızsa alt adımlar atlanır).

## Kurulum

Gerekenler: **Python 3.9+** (3.10+ önerilir), **pip**, **git**. Bağımlılıklar: `openpyxl`, `requests` (**`pandas` gerekmez**).

### Windows

1. **Python kur** — [python.org/downloads](https://www.python.org/downloads/) veya:
   ```powershell
   winget install -e --id Python.Python.3.12
   ```
   Installer ile kuruyorsan **"Add python.exe to PATH"** kutusunu işaretle. Doğrula:
   ```powershell
   python --version
   ```
2. **git kur:**
   ```powershell
   winget install -e --id Git.Git
   ```
3. **Repoyu klonla:**
   ```powershell
   git clone https://github.com/quasys-tech/BeyondTrust-SBM-Migration.git
   cd BeyondTrust-SBM-Migration
   ```
4. **(Önerilir) sanal ortam (venv):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   > Aktivasyon engellenirse: `Set-ExecutionPolicy -Scope Process RemoteSigned`
5. **Bağımlılıkları kur:**
   ```powershell
   pip install -r requirements.txt
   ```
6. **Secret'ları ver** (aşağıdaki "Yapılandırma & secret'lar"a bak) — env ya da `config/secrets.py`.

### Linux

1. **Python + pip + venv + git kur:**
   - Debian / Ubuntu:
     ```bash
     sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
     ```
   - RHEL / CentOS / Fedora:
     ```bash
     sudo dnf install -y python3 python3-pip git
     ```
   Doğrula: `python3 --version`
2. **Repoyu klonla:**
   ```bash
   git clone https://github.com/quasys-tech/BeyondTrust-SBM-Migration.git
   cd BeyondTrust-SBM-Migration
   ```
3. **(Önerilir) sanal ortam (venv):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
4. **Bağımlılıkları kur:**
   ```bash
   pip install -r requirements.txt
   ```
5. **Secret'ları ver** (aşağıdaki "Yapılandırma & secret'lar"a bak) — env ya da `config/secrets.py`.

## Çalıştırma

**Windows (PowerShell):**
```powershell
$env:PYTHONIOENCODING="utf-8"
python main.py          # tüm zincir: korelasyon + migrate (Part 2+3+4)
python delete.py --yes  # temizlik (yalnızca oluşturulanlar)
```

**Linux (bash):**
```bash
PYTHONIOENCODING=utf-8 python3 main.py
python3 delete.py --yes
```

> `PYTHONIOENCODING=utf-8` özellikle Windows konsolunda Türkçe karakterler ve `✓/✗` için gereklidir.

## Yapılandırma & secret'lar

Tüm ayarlar `config/settings.py` içinde (önem sırasına göre dizili) ve `BT_*` ortam
değişkenleriyle override edilebilir. **Secret'lar (API key, parolalar) repoda tutulmaz:**
önce ortam değişkeni (`BT_API_KEY`, `BT_MA_PASSWORD`, `BT_BIND_PASSWORD`), yoksa
gitignore'lu `config/secrets.py` kullanılır.

**Yöntem A — `config/secrets.py`** (gitignore'lu; lokal geliştirme için pratik):
```python
API_KEY = "<PS-Auth key>"
MANAGED_ACCOUNT_PASSWORD = "<...>"
AD_BIND_PASSWORD = "<...>"
```

**Yöntem B — ortam değişkeni** (üretim için önerilir):
```powershell
# Windows (PowerShell)
$env:BT_API_KEY="<PS-Auth key>"; $env:BT_MA_PASSWORD="<...>"; $env:BT_BIND_PASSWORD="<...>"
```
```bash
# Linux (bash)
export BT_API_KEY="<PS-Auth key>"; export BT_MA_PASSWORD="<...>"; export BT_BIND_PASSWORD="<...>"
```

Diğer ayarlar da `BT_*` env ile override edilebilir: `BT_PAM_URL`, `BT_RUNAS_USER`,
`BT_WORKGROUP_NAME`, `BT_BIND_USER` vb. (tam liste `config/settings.py`).

## Ayrıntılı dokümantasyon

Tam mimari, kurallar, senaryo kataloğu, REST endpoint listesi ve doğrulanmış BeyondTrust
davranışları için bkz. **[DOKUMANTASYON.md](DOKUMANTASYON.md)**.
