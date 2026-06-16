# SBM Migration — Proje Dokümantasyonu

> **Amaç:** CyberArk envanterini **BeyondTrust Password Safe**'e taşıyan migration aracı (quasys.com.tr müşterisi).
> CyberArk safe/kullanıcı yapısını ve sunucu envanterini okuyup, BeyondTrust üzerinde
> kullanıcı grubu, kullanıcı, managed system, managed account, smart rule ve yetkilendirmeleri
> **idempotent** (tekrar tekrar çalıştırılabilir) şekilde oluşturur.

Son uçtan uca doğrulama: **2026-06-15**, canlı ortam `pam.quasys.com.tr` — birleşik AD+LOCAL akışı (`type` kolonu), dinamik workgroup çözümü; 12 working satırı (8 AD + 4 LOCAL), tüm adımlar ✓.

---

## 1. Genel Bakış

Araç dört bölümden (PART) oluşur:

| Part | Ne yapar | Giriş betiği |
|------|----------|--------------|
| **PART 1** | `PamEnvanter.xlsx` × `OsEnvanter.xlsx` korelasyonu → `output/Working.xlsx` | `main.py` |
| **PART 2** | safe name → UserGroup → User → Membership | `migrate.py` |
| **PART 3** | Managed System → Managed Account → Link | `migrate.py` |
| **PART 4** | Smart Rule (Quick Rule) → UG yetkilendirme → Role + Access Policy | `migrate.py` |
| **Temizlik** | Yalnızca **bizim oluşturduğumuz** nesneleri siler | `delete.py` |

> **TEK ORTAK EXCEL + `type` kolonu ile yönlendirme:** PamEnvanter'daki her satır `type`
> kolonuna göre Part 3'te **AD** (domain MS + link) veya **LOCAL** (kendi sistemi, link yok)
> sürecine yönlendirilir. Ayrı excel/script yoktur; her şey `migrate.py` içinde.

> **Not:** PART 2, 3 ve 4 tek koşuda (`migrate.py`) **satır satır** birlikte işlenir. PART 1 ayrı bir hazırlık adımıdır.

> **SIKI ZİNCİR (satır bütünlüğü):** Her satır için adımlar **bağımlılık zinciriyle** çalışır — bir üst adım başarısızsa alt adımlar **hiç denenmez** (orphan/yarım nesne üretilmez):
> - **Part 2 (UG+User+Member) başarısız** ⇒ Part 3 ve Part 4 atlanır.
> - **ManagedSystem oluşturulamaz/IGNORED** ⇒ ManagedAccount, Link ve Part 4 atlanır.
> - **ManagedAccount açılamaz** ⇒ Link ve Part 4 atlanır.
>
> Atlanan adımlar `working_output.xlsx`'te `-` (SKIP) olarak görünür ve INFO'da sebep yazılır.

---

## 2. Mimari ve Klasör Yapısı

```
SBM/
├── main.py                       # GİRİŞ: tüm zinciri çalıştırır (Part1 korelasyon -> migrate)
├── migrate.py                    # PART 2+3+4 (AD/LOCAL routing); tek başına da çalışır
├── delete.py                     # TEMİZLİK (ayrı/bağımsız — müşteriye verilmez)
├── requirements.txt              # openpyxl + requests
│
├── config/
│   └── settings.py               # TÜM ayarlar — önem sırasına göre (kimlik üstte, template altta)
│
├── common/
│   ├── logging_setup.py          # Renkli konsol + zaman damgalı dosya logu
│   └── excel_utils.py            # Sheet -> dict satır okuma
│
├── correlation/                  # === PART 1 ===
│   ├── models.py                 # OsRecord, PamRow, WorkingRow, IgnoredRow (+ account_type)
│   ├── excel_reader.py           # Başlık (header) tabanlı excel okuma (type kolonu opsiyonel)
│   ├── os_inventory.py           # IP/hostname arama indeksi + duplicate (belirsiz) tespiti
│   ├── correlator.py             # Korelasyon kuralları (Part 1'in kalbi)
│   └── excel_writer.py           # Working.xlsx yazımı (type kolonu dahil)
│
├── beyondtrust/                  # === REST istemcisi ===
│   ├── session.py                # SignAppin + cookie tabanlı HTTP (get/post/put/delete)
│   ├── cache.py                  # Lazy, çok-anahtarlı, write-through cache
│   └── endpoints/
│       ├── user_groups.py        # UserGroups + UG↔SmartRule (accesslevel/role)
│       ├── users.py              # Users (create/add-to-group/delete)
│       ├── workgroups.py         # GET /Workgroups  (ad→id dinamik çözüm)
│       ├── managed_systems.py    # ManagedSystems + link/unlink
│       ├── managed_accounts.py   # ManagedAccounts
│       ├── functional_accounts.py# GET /FunctionalAccounts  (ad→id)
│       ├── password_rules.py     # GET /PasswordRules        (ad→id)
│       ├── smart_rules.py        # SmartRules + QuickRules
│       └── access_policies.py    # GET /AccessPolicies       (ad→id)
│
├── migration/                    # === Orkestrasyon (iş kuralları) ===
│   ├── processor.py              # PART 2: RowProcessor + RowResult (önce User, sonra UG)
│   ├── system_processor.py       # PART 3 (AD): SystemProcessor (domain MS + link)
│   ├── local_system_processor.py # PART 3 (LOCAL): LocalSystemProcessor (kendi sistemi, link yok)
│   ├── smart_rule_processor.py   # PART 4: SmartRuleProcessor
│   ├── account_type.py           # 'type' kolonu sınıflandırma (local / ad)
│   ├── managed_system/
│   │   ├── factory.py            # OS tipine göre payload kurucu seçimi
│   │   ├── linux.py              # Linux MS payload
│   │   └── windows.py            # Windows MS payload
│   ├── managed_account/
│   │   ├── ad_account.py         # AD managed account payload + account_key
│   │   └── local_account.py      # LOCAL managed account payload (DomainName="None")
│   ├── output_writer.py          # working_output.xlsx (✓/✗ renkli)
│   └── object_tracker.py         # Oluşturulan nesnelerin kaydı (delete.py için)
│
├── data/                         # Girdi excelleri (PamEnvanter+OsEnvanter) + generated_objects.json
├── output/                       # Working.xlsx (P1) + working_output.xlsx (P2+3+4)
└── logs/                         # Zaman damgalı çalışma logları
```

**Katman ayrımı:**
- `beyondtrust/endpoints/*` → **sadece HTTP + yanıt çözümleme** (iş kuralı yok).
- `migration/*` → **iş kuralları** (var mı? yoksa oluştur? eşleşme? idempotentlik).
- `config/settings.py` → tüm sabitler, hiçbir "magic value" kodda gömülü değil.

---

## 3. Kurulum ve Çalıştırma

### Gereksinimler
- Python 3 (ortamda `pandas` **yok**; yalnızca `openpyxl` + `requests` kullanılır).
- `pip install -r requirements.txt`

### Çalıştırma
```powershell
# TÜM ZİNCİR tek komut: Part 1 korelasyon -> migrate (Part 2+3+4)
$env:PYTHONIOENCODING="utf-8"; python main.py

# (opsiyonel) Sadece migration'ı tekrar koş — Working.xlsx zaten üretilmişse
$env:PYTHONIOENCODING="utf-8"; python migrate.py

# Temizlik (yalnızca oluşturulanları siler)
$env:PYTHONIOENCODING="utf-8"; python delete.py          # onay sorar
$env:PYTHONIOENCODING="utf-8"; python delete.py --yes    # onaysız siler
```

> `python main.py` önce korelasyonu yapıp `Working.xlsx` üretir, sonra `migrate.py`'yi
> çağırır. Part 1 başarısızsa zincir durur. `migrate.py` tek başına da çalıştırılabilir
> (mevcut `Working.xlsx`'i okur). **`main.py`'den sonra `migrate.py`'yi ayrıca çağırmaya gerek yok.**

> **ÖNEMLİ — Windows konsolu (cp1252):** Türkçe karakterler ve `✓/✗` işaretleri için
> betikleri **`PYTHONIOENCODING=utf-8`** ile çalıştırın.

### Kimlik ve secret'lar
Tüm kimlik bilgileri `config/settings.py` içinde **ortam değişkeni (env) ile override edilebilir**
şekilde tanımlıdır. Üretimde secret'lar env'den (veya gitignore'lu `config/secrets.py`'dan) verilir:

| Env | Açıklama |
|-----|----------|
| `BT_PAM_URL` | PAM kök adresi |
| `BT_API_KEY` | PS-Auth uygulama anahtarı |
| `BT_RUNAS_USER` | runas kullanıcısı (örn. `SBM_MIGRATE`) |
| `BT_BIND_USER` / `BT_BIND_PASSWORD` | AD bind kullanıcı/parola |
| `BT_MA_PASSWORD` | Managed account parolası |
| `BT_WORKGROUP_NAME` | MS Workgroup adı (varsayılan "BeyondTrust Workgroup"; ID dinamik çözülür) |

> Tüm ayarların tam listesi `config/settings.py` içinde (önem sırasına göre dizili); her biri `BT_*` env değişkeniyle override edilebilir.

---

## 4. Uçtan Uca Veri Akışı

```
PamEnvanter.xlsx ─┐
                  ├─►[PART 1 correlate]─► output/Working.xlsx ─┐
OsEnvanter.xlsx  ─┘     (Working + Ignored Rows)               │
                                                               ▼
                                          ┌─────────── migrate.py (her satır) ───────────┐
                                          │ PART 2: UserGroup → User → Membership          │
                                          │ PART 3: ManagedSystem → ManagedAccount → Link  │
                                          │ PART 4: SmartRule → AccessLevel → Role         │
                                          └───────────────────────────────────────────────┘
                                                               │
                                          output/working_output.xlsx  (✓/✗ rapor)
                                          data/generated_objects.json (silme takibi)
```

---

## 5. PART 1 — Korelasyon (`main.py`)

`PamEnvanter.xlsx` ve `OsEnvanter.xlsx` **başlık adına göre** okunur (kolon sırası önemsiz).
Her PamEnvanter satırının `remoteMachines` alanı `;` ile parçalanır; her parça OsEnvanter'da
IP veya hostname üzerinden aranır.

### Uygulanan kurallar (`correlation/correlator.py`)

| # | Kural | Sonuç |
|---|-------|-------|
| 1 | `remoteMachines` `;` ile parçalanır, her parça ayrı işlenir | — |
| 2 | Her parça OsEnvanter'da (IP **veya** hostname) aranır | — |
| 3 | **Eşleşme yok** | → **Ignored** ("OsEnvanter'da eşleşme bulunamadı") |
| 4 | Eşleşti ama **OS bilgisi boş** | → **Ignored** ("OS bilgisi boş") |
| 5 | **Domain boş** | → `DEFAULT_DOMAIN` (`quasys.com.tr`) kullanılır, working üretilir |
| 6 | **Hostname boş** (ayar açıksa `HOSTNAME_FALLBACK_TO_IP`) | → hostname yerine IP yazılır |
| 7 | IP boş | şimdilik boş bırakılır |
| 8 | **OsEnvanter'da aynı IP/hostname birden fazla kez** (belirsiz) | → **Ignored** ("birden fazla kez var, kontrol edin") |

> `type` kolonu (varsa) korele satıra taşınır; yoksa o satır AD/servis sayılır (bkz. 8B).

### Çıktı: `output/Working.xlsx`
- **`Working`** sayfası: başarılı eşleşmeler (PamEnvanterSatır, username, ip address, hostname, OS, safe name, domain, **type**).
- **`Ignored Rows`** sayfası: işlenemeyen satırlar + sebep.

---

## 6. PART 2 — UserGroup / User / Membership (`migration/processor.py`)

Her working satırı için sırayla (**önce User**, sonra UserGroup):

1. **User:** ad = **`safe name`** kolonu (UserType = ActiveDirectory). AD doğrulaması burada olur. Var mı? Yoksa oluştur.
2. **User Group:** ad = **`safe name`** kolonu. Cache'te var mı? Yoksa oluştur.
3. **Membership:** User'ı gruba üye yap.

### Kurallar
- **UserGroup adı VE User adı ikisi de `safe name` kolonundan beslenir** (açık talimat).
  `username` (örn. `srvsbmuser1`) Part 3'te managed account olur.
- **Sıra: önce User.** AD'de safe name'e karşılık kullanıcı **bulunamazsa** satır **IGNORED** edilir (Ignored sheet'e gider) ve **UserGroup hiç oluşturulmaz** (orphan UG üretilmez). Diğer hatalar (örn. ad çok uzun) ✗ FAIL.
- UserGroup create izinleri: `[{PermissionID:52, AccessLevelID:1}, {PermissionID:76, AccessLevelID:3}]`, `groupType=BeyondInsight`.
- User create: `UserType=ActiveDirectory`; sadece `UserName` excelden, forest/domain/bind ayarları settings'ten.
- **İdempotentlik:** UserGroup ve User **isme göre** tekil; aynı çalışmada veya önceki çalışmalardan varsa tekrar oluşturulmaz (cache + preload).

### BeyondTrust REST
| İşlem | Çağrı |
|-------|-------|
| Liste | `GET /UserGroups`, `GET /Users` |
| Create UG | `POST /UserGroups` (lowercase: `groupType, groupName, description, isActive, Permissions`) |
| Create User | `POST /Users/` (sondaki slash) |
| Üyelik | `POST /Users/{userId}/UserGroups/{groupId}` |

> **Not:** AD user create ilk seferde AD sync nedeniyle ~18 sn sürebilir. Duplicate üyelikte 400/409 + "already/exist" → başarı sayılır.

---

## 7. PART 3 — Managed System / Account / Link (`migration/system_processor.py`)

Her working satırı için:

### Adım 1 — Managed System (IP unique ile)
```
IP var + hostname eşleşiyor   → mevcut sistemi kullan
IP var + hostname uyuşmuyor   → IGNORED ("kontrol edin"), satır durur
IP yok (eşleşme yok)          → OS tipine göre yeni oluştur
OS tipi tanınmıyor            → IGNORED ("OS tipi tanınmadı")
```
- **OS sınıflandırma** (`factory.classify_os`): `OS_LINUX_KEYS` / `OS_WINDOWS_KEYS` içinden "içerir" eşleşmesi.
- Linux → `PlatformID=2`, Windows → `PlatformID=1`. Tipe ayrık payload (`linux.py` / `windows.py`).

### Adım 2 — Managed Account (AD, domain MS altında)
- `username` (örn. `srvsbmuser1`), **domain managed system (id=2, `quasys.com.tr`)** altında AD managed account olarak açılır.
- **Tekil eşleşme anahtarı: `AccountName + DomainName`** (`account_key` = `name@domain`, lowercase). Aynı isimli hesap farklı domain'lerde **ayrı** kabul edilir. Boş domain → `DEFAULT_DOMAIN`.
- MA username başına bir kez açılır (cache), her sisteme linklenir.

### Adım 3 — Link
- Managed account → row'un managed system'ine `POST /ManagedSystems/{sysId}/LinkedAccounts/{accId}`.

### Functional Account (iki bağımsız flag)
Managed system oluşturulurken functional account ve auto-management **iki ayrı ayar** ile kontrol edilir:

| Ayar | Varsayılan | Etki |
|------|-----------|------|
| `FUNCTIONAL_ACCOUNT_USAGE` | `True` | True → ad (`BTFunctionalAccount`) `GET /FunctionalAccounts` ile `FunctionalAccountID`'ye çözülüp payload'a eklenir |
| `AUTO_MANAGEMENT` | `False` | `AutoManagementFlag` değerini belirler |

> ⚠️ **KRİTİK (canlıda doğrulandı):** BeyondTrust, `AutoManagementFlag=False` iken gönderilen
> `FunctionalAccountID`'yi **sessizce düşürür** (kayıtta `None` olur, hata vermez).
> Functional account'un gerçekten **yapışması için ikisi de `True` olmalıdır.**
> `USAGE=True + AUTO=False` olduğunda kod tek seferlik **WARN** basar.
> Functional account adı bulunamazsa sistem fonksiyonel hesapsız oluşturulur (payload'dan `FunctionalAccountID` çıkarılır, `null` gönderilmez).

### Password Policy
- `LINUX_PASSWORD_POLICY` / `WINDOWS_PASSWORD_POLICY` (varsayılan: `"Default Password Policy"`).
- Ad, `GET /PasswordRules` ile **`PasswordRuleID`**'ye çözülüp payload'a yazılır.
- ⚠️ **"Default Password Policy" id=0'dır ve 0 GEÇERLİ bir değerdir** → kod `is not None` ile kontrol eder, 0'ı asla düşürmez. Bulunamazsa template varsayılanı (0) kalır.
- Functional account'un aksine, `PasswordRuleID` **auto-management'tan bağımsız** her zaman yapışır (canlıda doğrulandı).

---

## 8. PART 4 — Smart Rule / UG Yetkilendirme / Role (`migration/smart_rule_processor.py`)

Part 2/3 tamamlandıktan **sonra**, aynı satır için çağrılır. Üç adım:

### Adım 1 — Smart Rule (Quick Rule)
- Ad = **`f"{SMARTRULE_MA_PREFIX}_{safe name}"`** → örn. `SBM_MA_sbmuser1`.
- `GET /SmartRules` (Title eşleşme) ile aranır:
  - **Yoksa:** `POST /QuickRules` ile managed account id'siyle oluşturulur.
  - **Varsa:** `GET /QuickRules/{id}/ManagedAccounts` ile mevcut hesap id'leri alınır; bu MA id eklenip `PUT /QuickRules/{id}/ManagedAccounts {AccountIDs:[...]}` ile güncellenir. (Zaten bağlıysa dokunulmaz.)

### Adım 2 — UserGroup ↔ SmartRule AccessLevel
- Precheck: `GET /UserGroups/{gid}/SmartRules`.
- `POST /UserGroups/{gid}/SmartRules/{srid}/AccessLevels {AccessLevelID:3}` (3 = Read/Write).
- ⚠️ **Rol atamadan ÖNCE şarttır** (yoksa "must set AccessLevel before setting roles" 400 döner).

### Adım 3 — Role + Access Policy
- **Access policy:** `ACCESS_POLICY_NAME` (`"Default Auto-Approve Access Policy"`) → `GET /AccessPolicies` ile id'ye (5000) çözülür.
- Precheck: `GET /UserGroups/{gid}/SmartRules/{srid}/Roles` **boşsa** atar.
- `POST /UserGroups/{gid}/SmartRules/{srid}/Roles {Roles:[{RoleID:"3"}], AccessPolicyID:"5000"}`.
- **RoleID 3 = "Requestor/Approver"** (canlı `GET /Roles` ile doğrulandı).

### BeyondTrust Role / Access Policy referansı (quasys, canlı)
**Roller (`GET /Roles`):** 1=Requestor, 2=Approver, **3=Requestor/Approver**, 4=Information Security Administrator, 5=Auditor, 7=Credentials Manager, 8=Recorded Session Reviewer, 9=Active Session Reviewer.

**Access Policies (`GET /AccessPolicies`):** 5000="Default Auto-Approve Access Policy", 5002="Quasys Custom Request Approve".

---

## 8B. LOCAL vs AD Yönlendirmesi (`type` kolonu)

Tek ortak `PamEnvanter.xlsx` kullanılır; her satır **`type` kolonuyla** sınıflandırılır
(`migration/account_type.py`):
- **`local`** (veya `lokal`) → **LOCAL** süreç.
- diğer her şey (`ad`, `domain`, `servis`, boş) → **AD/servis** süreç.

`migrate.py` döngüsü Part 3'te bu kolona göre yönlendirir; **Part 2 ve Part 4 iki tip için de aynıdır**:

| Adım | AD / servis hesabı | LOCAL hesap |
|------|--------------------|-------------|
| Part 2 (UG/User/Member) | aynı | aynı |
| **Managed Account** | **domain MS (id=2) altında** | **row'un KENDİ MS'i altında** |
| **Link** | **var** (`LinkedAccounts`) | **YOK** |
| MA payload | AD (DomainName, UPN, SAM) | local (`DomainName:"None"`) |
| Tekil eşleşme | AccountName+DomainName (domain MS) | system + AccountName (per-system) |
| Part 4 (SmartRule/Role) | aynı (`SBM_MA_{safe}`) | aynı |

> Aynı `safe`'in hem AD hem local hesapları aynı `SBM_MA_{safe}` smart rule'unda toplanır.
> LOCAL satırlarda `working_output`'ta **Link kolonu `-`**; `part3_ok()` local'de link aramaz.
> İşleyici: AD → `SystemProcessor`, LOCAL → `LocalSystemProcessor` (her ikisi de `migrate.py`'da kurulur).

---

## 8C. Senaryo Kataloğu (edge-case'ler ve ele alınışları)

Canlıda dummy data ile doğrulanmış senaryolar:

### Korelasyon (OsEnvanter eşleştirme) → `Working.xlsx` "Ignored Rows"
| Kod | Senaryo | Sonuç |
|-----|---------|-------|
| C1 | IP token OsEnvanter'da yok | IGNORED — "eşleşme bulunamadı" |
| C2 | Hostname token OsEnvanter'da yok | IGNORED — "eşleşme bulunamadı" |
| C3 | Eşleşti ama OsEnvanter'da **OS boş** | IGNORED — "OS bilgisi boş" |
| C4 | OsEnvanter kaydında **IP kolonu boş** (hostname ile eşleşti) | WORKING (ip boş) → Part 3'te MS FAIL |
| C5 | OsEnvanter kaydında **hostname boş** (IP ile eşleşti) | WORKING — hostname = IP (fallback) |
| C6 | OsEnvanter'da **domain boş** | WORKING — domain = `DEFAULT_DOMAIN` |
| C7 | `remoteMachines` boş | satır hiç working üretmez |
| C8 | OsEnvanter'da **aynı IP birden fazla kez** (belirsiz) | IGNORED — "birden fazla kez var (belirsiz), kontrol edin" |
| C9 | OsEnvanter'da **aynı hostname birden fazla kez** | IGNORED — belirsiz (C8 ile aynı mantık) |

### Managed System (Part 3)
| Kod | Senaryo | Sonuç |
|-----|---------|-------|
| M1 | OS tipi tanınmıyor (Solaris/AIX) | IGNORED — "OS tipi tanınmadı" |
| M2 | IP boş (C4 sonucu) | MS FAIL — "IPAddress is required" → MA/Link/Part4 atlanır |
| M3 | IP geçersiz (999.999.999.999) | MS FAIL — "IPAddress is invalid" |
| M4 | IP mevcut sistemde **farklı hostname** | IGNORED — "kontrol edin" |
| M5 | IP mevcut + hostname eşleşiyor | mevcut sistemi kullan (idempotent) |

### User / safe name (Part 2)
| Kod | Senaryo | Sonuç |
|-----|---------|-------|
| U1 | safe name boş | satır işlenmez (UG ✗) |
| U2 | **AD'de kullanıcı bulunamadı** | **IGNORED** — UserGroup oluşturulmaz (önce User denenir) |
| U3 | safe name geçerli AD user | User OK |
| U5 | safe name mevcut (önceki koşu) | mevcut (idempotent) |

### Managed Account
| Kod | Senaryo | Sonuç |
|-----|---------|-------|
| A1 | AD: username boş | MA ✗ → Link/Part4 atlanır |
| A2 | AD: geçerli username | domain MS altında create + link |
| A3 | AD: aynı username farklı domain | ayrı hesap (AccountName+DomainName) |
| A4 | LOCAL: username boş | local MA ✗ |
| A5 | LOCAL: geçerli username | kendi sistemi altında, link yok |
| A6 | MA mevcut | reuse (idempotent) |

### type kolonu (yönlendirme)
| Kod | Senaryo | Sonuç |
|-----|---------|-------|
| T1 | `type=ad` | domain süreç (domain MS + link) |
| T2 | `type=local` | local süreç (kendi sistemi, link yok) |
| T3 | `type` boş/bilinmeyen | AD süreç (varsayılan) |

### Girdi sağlamlığı (input robustness) — canlıda doğrulandı
| Senaryo | Sonuç |
|---------|-------|
| Çoklu token `ip1;hostname2;ip3` | her token ayrı işlenir; AD'de 1 hesap → N sisteme link |
| Tekrarlı token `ip;ip` | dedup — aynı MS/MA/link tekrar denenmez |
| Boş segment `ip;;;host` | boş parçalar atlanır |
| Boşluk + BÜYÜK harf `  SBMSRV12  ` | trim + case-insensitive eşleşir |
| `type` = `LOCAL` / `  ad  ` (büyük harf/boşluk) | doğru sınıflandırılır (trim+lower) |
| Aynı `safe` altında AD + LOCAL satırları | aynı `SBM_MA_{safe}` smart rule'unda **karışık** toplanır |
| Aynı (sistem+hesap) farklı safe'lerde (local) | hesap reuse; her safe'in kendi smart rule'una eklenir |

> Genel ilke: **veri/eşleşme/AD eksikliği → IGNORED** (Ignored sheet, "kontrol edin"); **API reddi/bağımlılık eksikliği → ✗ FAIL**. Her iki durumda da sıkı zincir alt adımları atlar; hiçbir senaryoda crash olmaz.
>
> **Doğrulama (19 senaryo satırı tek koşuda):** 22 working (AD:18, LOCAL:4), korelasyon 2 IGNORED (eşleşme/OS), migrate 3 IGNORED (Solaris OS / hostname uyuşmazlığı / AD'de yok), MS ✗4 (IP boş/geçersiz + Solaris + hostname uyuşmazlığı), MA ✗1 (username boş); AD'de-yok satırı için **grup oluşturulmadı** (orphan yok); sbmuser1 smart rule'unda 1 AD + 3 LOCAL hesap karışık.

---

## 9. İdempotentlik ve Cache (`beyondtrust/cache.py`)

Her nesne türü **lazy yüklenen, çok-anahtarlı, write-through** bir cache ile yönetilir:
- Çalışma başında `preload_all()` ile mevcut tüm kayıtlar bir kez API'den çekilir.
- Yeni oluşturulan nesne anında cache'e eklenir (`add`) → aynı çalışma içinde tekrar oluşturma denenmez.
- Önceki çalışmalardan kalan kayıtlar preload sayesinde "mevcut" görülür.

**Tekil eşleşme anahtarları:**

| Tür | Anahtar |
|-----|---------|
| UserGroup | `Name` |
| User | `UserName` |
| ManagedSystem | `IPAddress` (+ `SystemName/HostName`) |
| DomainManagedAccount | **`AccountName + DomainName`** |
| FunctionalAccount | `AccountName` / `DisplayName` |
| PasswordRule | `Name` |
| SmartRule | `Title` |
| AccessPolicy | `Name` |

---

## 10. Takip ve Temizlik

### Takip (`migration/object_tracker.py`)
Migration **yalnızca kendi oluşturduğu** nesneleri `data/generated_objects.json`'a yazar:
`UserGroup, User, UserGroupMembership, ManagedSystem, ManagedAccount, Link, SmartRule`.
Var olan (preexisting) kayıtlara asla dokunulmaz.

### Temizlik (`delete.py`)
Takip dosyasını okuyarak **bağımlılık sırasıyla** siler:
```
1/7 SmartRule      (DELETE /SmartRules/{id} — UG/role bağlarını da kaldırır)
2/7 Link           (unlink)
3/7 ManagedAccount
4/7 ManagedSystem
5/7 Membership
6/7 User
7/7 UserGroup
```
- Başarı durumunda takip dosyası sıfırlanır; hata varsa **korunur** (tekrar denenebilir).
- Functional account / password rule / access policy gibi **bizim oluşturmadığımız** nesneler silinmez.
- `delete.py` migration'dan **bağımsızdır** (hiçbir modül onu import etmez) ve **müşteriye teslim edilmez**.

---

## 11. Çıktılar

| Dosya | İçerik |
|-------|--------|
| `output/Working.xlsx` | PART 1 çıktısı (Working + Ignored Rows) |
| `output/working_output.xlsx` | PART 2+3+4 sonucu — her satır için ✓/✗ kolonları (renkli): User Group, User, Member, Managed System, Managed Account, Link, **Smart Rule, AccessLevel, Role** + ID kolonları (Group/User/MS/MA/SR ID) + INFO |
| `data/generated_objects.json` | Silme takip dosyası |
| `logs/sbm_migration_*.log` | Zaman damgalı ayrıntılı log (konsol INFO, dosya DEBUG) |

Konsola çalışma sonunda **ÖZET RAPOR (Part 2 + 3 + 4)** basılır: her adım için `✓ N / ✗ N` ve oluşturulan nesne sayıları.

---

## 12. Ayar Referansı (`config/settings.py`)

### Part 1
| Ayar | Varsayılan | Açıklama |
|------|-----------|----------|
| `DEFAULT_DOMAIN` | `quasys.com.tr` | Domain boşsa kullanılır |
| `REMOTE_MACHINES_SEPARATOR` | `;` | remoteMachines ayırıcısı |
| `HOSTNAME_FALLBACK_TO_IP` | `True` | Hostname boşsa IP yaz |

### BeyondTrust / Part 2
| Ayar | Varsayılan | Açıklama |
|------|-----------|----------|
| `API_BASE_URL` | `https://pam.quasys.com.tr/BeyondTrust/api/public/v3` | REST taban |
| `VERIFY_SSL` | `False` | Self-signed sertifika |
| `USER_GROUP_PERMISSIONS` | `[{52,1},{76,3}]` | UG izinleri |
| `USER_TYPE` | `ActiveDirectory` | User tipi |

### Part 3
| Ayar | Varsayılan | Açıklama |
|------|-----------|----------|
| `WORKGROUP_NAME` | `BeyondTrust Workgroup` | MS'lerin Workgroup ADI; ID `GET /Workgroups` ile ada göre dinamik çözülür |
| `DOMAIN_MANAGED_SYSTEM_NAME` | `quasys.com.tr` | AD account'ların açıldığı directory MS (id=2) |
| `FUNCTIONAL_ACCOUNT_USAGE` | `True` | Functional account atansın mı |
| `AUTO_MANAGEMENT` | `False` | AutoManagementFlag (FA'nın yapışması için True olmalı) |
| `LINUX/WINDOWS_FUNCTIONAL_ACCOUNT_NAME` | `BTFunctionalAccount` | FA adı (→ id'ye çözülür) |
| `LINUX/WINDOWS_PASSWORD_POLICY` | `Default Password Policy` | Password policy adı (→ PasswordRuleID'ye çözülür) |

### Part 4
| Ayar | Varsayılan | Açıklama |
|------|-----------|----------|
| `SMARTRULE_MA_PREFIX` | `SBM_MA` | Smart rule adı öneki (`SBM_MA_{safe}`) |
| `SMART_RULE_ACCESS_LEVEL_ID` | `3` | UG-SR erişim seviyesi (Read/Write) |
| `SMART_RULE_ROLE_IDS` | `[3]` | Atanacak roller (Requestor/Approver) |
| `ACCESS_POLICY_NAME` | `Default Auto-Approve Access Policy` | Access policy adı (→ id'ye çözülür) |

---

## 13. BeyondTrust REST — Kullanılan Endpoint Özeti

**Auth:** `POST /Auth/SignAppin` (header `Authorization: PS-Auth key=<KEY>; runas=<USER>;`) → cookie `ASP.NET_SessionId`; sonraki tüm isteklerde `Cookie` yeterli. `POST /Auth/Signout`.

| Alan | Endpoint'ler |
|------|--------------|
| UserGroup | `GET/POST/DELETE /UserGroups`, `POST /Users/{u}/UserGroups/{g}` |
| User | `GET /Users`, `POST /Users/`, `DELETE /Users/{u}` |
| Workgroup | `GET /Workgroups` (ad → ID dinamik çözüm) |
| ManagedSystem | `GET /ManagedSystems`, `POST /Workgroups/{wg}/ManagedSystems`, `GET /ManagedSystems/{id}`, `DELETE /ManagedSystems/{id}` |
| Link | `GET/POST/DELETE /ManagedSystems/{s}/LinkedAccounts/{a}` |
| ManagedAccount | `GET/POST /ManagedSystems/{s}/ManagedAccounts`, `DELETE /ManagedAccounts/{a}` |
| FunctionalAccount | `GET /FunctionalAccounts` |
| PasswordRule | `GET /PasswordRules` |
| SmartRule / QuickRule | `GET /SmartRules`, `POST /QuickRules`, `GET/PUT /QuickRules/{id}/ManagedAccounts`, `DELETE /SmartRules/{id}` |
| UG↔SmartRule | `GET /UserGroups/{g}/SmartRules`, `POST .../{g}/SmartRules/{s}/AccessLevels`, `GET/POST .../{g}/SmartRules/{s}/Roles` |
| AccessPolicy | `GET /AccessPolicies` |

---

## 14. Doğrulanmış BeyondTrust Davranışları (canlı testle teyitli)

1. **Auth cookie:** SignAppin sonrası tek `requests.Session` ile `ASP.NET_SessionId` cookie'si tüm isteklere yeter; `Authorization` tekrar gerekmez.
2. **Functional account ⇒ auto-management:** `AutoManagementFlag=False` iken `FunctionalAccountID` **kaydedilmez** (sessizce `None`). Yapışması için `AutoManagementFlag=True` şart. (Test: auto=False+FA=1 → None; auto=True+FA=1 → 1.)
3. **PasswordRuleID:** create'te yapışır, **auto-management'tan bağımsız** (0→0, 1→1). 0 ("Default Password Policy") geçerli değerdir.
4. **AccessLevel → Role sırası:** Role atamadan önce UG-SmartRule AccessLevel atanmalı.
5. **Silme:** Quick rule oluşturulsa da silme `DELETE /SmartRules/{id}` (QuickRules değil!) ile yapılır; UG/role bağlarını da kaldırır.
6. Duplicate işlemlerde 400/409 + "already/exist/duplicate" → başarı sayılır.

---

## 15. Bilinen Sınırlamalar / Sıradaki İşler

- **Part 2 iç-bütünlük:** Sıkı zincir Part'lar **arasında** uygulanır. Part 2'nin **kendi içinde** UserGroup, User'dan önce oluşturulur; AD'de olmayan bir kullanıcıda User başarısız olsa da UserGroup oluşmuş kalır (küçük orphan). İstenirse User-fail'de UG geri alınabilir veya sıra değiştirilebilir.
- **Çok-domain managed account:** "mevcut mu" kontrolü `AccountName+DomainName` ile domain-duyarlı; ancak **create hâlâ tek directory MS (id=2) altında** yapılıyor. Gerçek çok-domain için her domain'e ayrı directory MS çözümü gerekir (henüz yok).
- **Gerçek yönetime alma / autochange:** Functional account'un fiilen devreye girmesi `AUTO_MANAGEMENT=True` senaryosunu gerektirir (varsayılan kapalı). İstendiğinde açılarak yönetilen (managed) sistemler oluşturulabilir.
- **IP boş satırlar:** Part 1'de IP çözümlemesi (nslookup) henüz uygulanmadı.

---

## Ek: Hızlı Komut Özeti

```powershell
$env:PYTHONIOENCODING="utf-8"
python main.py          # TÜM ZİNCİR: Part1 korelasyon -> migrate (Part2+3+4, AD/LOCAL routing)
python delete.py --yes  # Temizlik (AD + local, yalnızca oluşturulanlar)
```

> **`python main.py` tüm zinciri sırayla çalıştırır:** (1) Part 1 korelasyon
> (`Working.xlsx`, `type` kolonu dahil), (2) `migrate.py` (Part 2+3+4; her satır
> `type` kolonuna göre AD veya LOCAL sürecine yönlendirilir). Part 1 başarısızsa
> zincir durur. `migrate.py` ayrıca tek başına da çalıştırılabilir.
