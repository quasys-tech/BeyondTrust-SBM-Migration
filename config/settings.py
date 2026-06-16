# -*- coding: utf-8 -*-
"""
Merkezi yapılandırma (configuration) dosyası.

Tüm yol (path), varsayılan değer ve davranış ayarları burada toplanır.
Kod içinde "sabit" (magic value) bırakmamak için her şey buradan okunur.

Parametreler ÖNEM SIRASINA göre dizilmiştir (yukarıdan aşağı):
  1) Bağlantı & kimlik (URL, API key, runas)        <- ortama göre MUTLAKA değişir
  2) Ortam / iş parametreleri (domain, workgroup, parola, AD bind)
  3) Functional account & auto-management
  4) Password policy
  5) Smart rule / role / access policy
  6) User / User Group create parametreleri
  7) Korelasyon & kolon/OS kuralları
  8) Dosya yolları
  9) Loglama
 10) Sabit create template'leri (nadiren dokunulur)

Not: Secret'lar (API key / parola) koda gömülmemeli; tümü os.environ ile override
edilebilir. Ortam değişkeni yoksa buradaki varsayılan kullanılır (test kolaylığı).
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Secret çözümü: önce env (BT_*), yoksa gitignore'lu config/secrets.py,
# o da yoksa boş. Böylece repoya hiçbir secret gömülü gitmez; lokal geliştirmede
# config/secrets.py (git'e ÇIKMAZ) gerçek değerleri tutar.
# ---------------------------------------------------------------------------
try:
    from config import secrets as _local_secrets  # gitignored; repoda yok
except Exception:
    _local_secrets = None


def _secret(env_name: str, attr: str) -> str:
    value = os.getenv(env_name)
    if value:
        return value
    if _local_secrets is not None:
        return str(getattr(_local_secrets, attr, "") or "")
    return ""


# ===========================================================================
# 1) BAĞLANTI & KİMLİK  (en kritik — her ortamda değişir)
# ===========================================================================
# PAM kök adresi (sonunda / olabilir; kod normalize eder)
PAM_URL: str = os.getenv("BT_PAM_URL", "https://pam.quasys.com.tr/")

# REST API taban adresi (PAM_URL'den türetilir)
API_BASE_URL: str = PAM_URL.rstrip("/") + "/BeyondTrust/api/public/v3"

# Uygulama anahtarı (PS-Auth key) — env BT_API_KEY veya config/secrets.py
API_KEY: str = _secret("BT_API_KEY", "API_KEY")

# runas kullanıcısı (PS-Auth header'ında)
RUNAS_USER: str = os.getenv("BT_RUNAS_USER", "SBM_MIGRATE")

# HTTP davranışı
VERIFY_SSL: bool = False          # Test ortamı self-signed sertifikası için False
HTTP_TIMEOUT_SECONDS: int = 30
HTTP_MAX_RETRIES: int = 2         # Geçici ağ hatalarında tekrar deneme

# ===========================================================================
# 2) ORTAM / İŞ PARAMETRELERİ  (domain, workgroup, parola, AD bind)
# ===========================================================================
# Domain bilgisi bulunamazsa kullanılacak varsayılan domain.
DEFAULT_DOMAIN: str = "quasys.com.tr"

# Managed System'lerin oluşturulacağı Workgroup ADI. ID, çalışma anında
# GET /Workgroups üzerinden ada göre dinamik bulunur (ad değişse de ID otomatik
# çözülür). Bulunamazsa migration durur.
WORKGROUP_NAME: str = os.getenv("BT_WORKGROUP_NAME", "BeyondTrust Workgroup")

# Domain (directory) Managed System eşleştirmesi: HostName/SystemName bu değere
# eşit olan managed system, AD managed account'ların açılacağı sistemdir.
DOMAIN_MANAGED_SYSTEM_NAME: str = os.getenv("BT_DOMAIN_MS_NAME", DEFAULT_DOMAIN)

# Managed Account parolası — env BT_MA_PASSWORD veya config/secrets.py
MANAGED_ACCOUNT_PASSWORD: str = _secret("BT_MA_PASSWORD", "MANAGED_ACCOUNT_PASSWORD")

# User create (ActiveDirectory) parametreleri. Sadece UserName excelden gelir;
# diğerleri buradan.
USER_TYPE: str = "ActiveDirectory"
AD_FOREST_NAME: str = os.getenv("BT_AD_FOREST", DEFAULT_DOMAIN)
AD_DOMAIN_NAME: str = os.getenv("BT_AD_DOMAIN", DEFAULT_DOMAIN)
AD_BIND_USER: str = os.getenv("BT_BIND_USER", "enes")
AD_BIND_PASSWORD: str = _secret("BT_BIND_PASSWORD", "AD_BIND_PASSWORD")
AD_USE_SSL: bool = False

# ===========================================================================
# 3) FUNCTIONAL ACCOUNT & AUTO-MANAGEMENT  (managed system create)
# ===========================================================================
# True ise managed system'ler functional account ile oluşturulur (ad ->
# FunctionalAccountID çözülür); False ise functional account hiç kullanılmaz.
FUNCTIONAL_ACCOUNT_USAGE: bool = (
    os.getenv("BT_FUNCTIONAL_ACCOUNT_USAGE", "true").strip().lower()
    in ("1", "true", "yes", "on")
)

# Managed system'ler AutoManagementFlag açık mı (True) oluşturulsun?
# FUNCTIONAL_ACCOUNT_USAGE'dan BAĞIMSIZ. DİKKAT (canlıda doğrulandı): BeyondTrust
# functional account'u yalnızca AutoManagementFlag=True iken kabul eder; False
# iken FunctionalAccountID sessizce düşürülür. FA'nın yapışması için ikisi de True.
AUTO_MANAGEMENT: bool = (
    os.getenv("BT_AUTO_MANAGEMENT", "false").strip().lower()
    in ("1", "true", "yes", "on")
)

# Functional account ADI (OS tipine göre). Çalışma anında GET /FunctionalAccounts
# üzerinden FunctionalAccountID'ye çözülür.
LINUX_FUNCTIONAL_ACCOUNT_NAME: str = os.getenv("BT_LINUX_FUNC_ACCOUNT", "BTFunctionalAccount")
WINDOWS_FUNCTIONAL_ACCOUNT_NAME: str = os.getenv("BT_WINDOWS_FUNC_ACCOUNT", "BTFunctionalAccount")

# OS tipi -> functional account adı eşlemesi (factory/system_processor okur).
FUNCTIONAL_ACCOUNT_NAMES = {
    "linux": LINUX_FUNCTIONAL_ACCOUNT_NAME,
    "windows": WINDOWS_FUNCTIONAL_ACCOUNT_NAME,
}

# ===========================================================================
# 4) PASSWORD POLICY  (managed system create)
# ===========================================================================
# Password policy ADI (OS tipine göre). Payload alanı PasswordRuleID; ad çalışma
# anında GET /PasswordRules ile id'ye çözülür. NOT: "Default Password Policy" id=0.
LINUX_PASSWORD_POLICY: str = os.getenv("BT_LINUX_PASSWORD_POLICY", "Default Password Policy")
WINDOWS_PASSWORD_POLICY: str = os.getenv("BT_WINDOWS_PASSWORD_POLICY", "Default Password Policy")

# OS tipi -> password policy adı eşlemesi.
PASSWORD_POLICY_NAMES = {
    "linux": LINUX_PASSWORD_POLICY,
    "windows": WINDOWS_PASSWORD_POLICY,
}

# ===========================================================================
# 5) SMART RULE / ROLE / ACCESS POLICY  (Part 4)
# ===========================================================================
# Managed account Quick Smart Rule adı: f"{PREFIX}_{safe name}".
# Örn: safe name = "sbmuser1" -> "SBM_MA_sbmuser1".
SMARTRULE_MA_PREFIX: str = os.getenv("BT_SMARTRULE_MA_PREFIX", "SBM_MA")

# Access policy ADI -> çalışma anında GET /AccessPolicies ile id'ye çözülür.
# Boş bırakılırsa role ataması yapılmaz; adım uyarı ile atlanır.
ACCESS_POLICY_NAME: str = os.getenv("BT_ACCESS_POLICY_NAME", "Default Auto-Approve Access Policy")

# SmartRule'e atanacak roller. 3 = "Requestor/Approver" (canlıda /Roles ile doğrulandı).
SMART_RULE_ROLE_IDS = [3]

# UserGroup <-> SmartRule erişim seviyesi. 3 = Read/Write (rol atamadan önce şart).
SMART_RULE_ACCESS_LEVEL_ID: int = 3

# QuickRule create sabitleri (managed account tabanlı quick rule).
SMART_RULE_CATEGORY: str = "Quick Rules"
SMART_RULE_TYPE: str = "ManagedAccount"

# ===========================================================================
# 6) USER / USER GROUP CREATE PARAMETRELERİ  (Part 2)
# ===========================================================================
# User Group create için sabit izinler.
USER_GROUP_PERMISSIONS = [
    {"PermissionID": 52, "AccessLevelID": 1},
    {"PermissionID": 76, "AccessLevelID": 3},
]
USER_GROUP_TYPE: str = "BeyondInsight"

# ===========================================================================
# 7) KORELASYON & KOLON / OS KURALLARI
# ===========================================================================
# remoteMachines alanındaki değerleri ayıran karakter:  ip1;ip2;hostname3
REMOTE_MACHINES_SEPARATOR: str = ";"

# OsEnvanter eşleşmesinde hostname boşsa, hostname kolonuna IP adresi yazılsın mı?
HOSTNAME_FALLBACK_TO_IP: bool = True

# Working.xlsx kolon adları (Part 1 çıktısının başlıkları).
COL_PAM_SATIR: str = "PamEnvanterSatır"
COL_USERNAME: str = "username"
COL_SAFE_NAME: str = "safe name"
COL_DOMAIN: str = "domain"

# Hesap tipi kolonu: satır LOCAL hesap mı yoksa AD/servis hesabı mı? Bu kolona
# göre Part 3 yönlendirilir (local / domain). Part 2 ve Part 4 her iki tip için aynı.
COL_ACCOUNT_TYPE: str = "type"
# Bu değerler (küçük harf, trim) LOCAL kabul edilir; geri kalan her şey
# (ad / domain / servis / boş) AD servis hesabı sayılır.
LOCAL_ACCOUNT_KEYS = ("local", "lokal")

# User Group adı VE User adı ikisi de 'safe name' kolonundan beslenir.
USER_GROUP_SOURCE_COLUMN: str = COL_SAFE_NAME   # User Group adı kaynağı
USER_SOURCE_COLUMN: str = COL_SAFE_NAME         # User adı kaynağı

# Platform eşlemesi (template'lerde de gömülü).
PLATFORM_ID_LINUX: int = 2
PLATFORM_ID_WINDOWS: int = 1

# OS tipini normalize ederken kullanılacak anahtarlar (küçük harf, 'içerir').
OS_LINUX_KEYS = ("linux", "unix", "redhat", "centos", "ubuntu", "suse")
OS_WINDOWS_KEYS = ("windows", "win")

# ===========================================================================
# 8) DOSYA YOLLARI
# ===========================================================================
# Proje kök dizini (config/ klasörünün bir üstü)
BASE_DIR: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = BASE_DIR / "data"        # Girdi excelleri + takip dosyası
OUTPUT_DIR: Path = BASE_DIR / "output"    # Üretilen Working.xlsx / sonuç
LOG_DIR: Path = BASE_DIR / "logs"         # Çalışma logları

# Girdi dosyaları
PAM_ENVANTER_FILE: Path = DATA_DIR / "PamEnvanter.xlsx"
OS_ENVANTER_FILE: Path = DATA_DIR / "OsEnvanter.xlsx"
# Okunacak sheet adı. None verilirse dosyadaki ilk (aktif) sheet kullanılır.
PAM_SHEET_NAME = None
OS_SHEET_NAME = None

# Part 1 çıktısı (korelasyon)
WORKING_FILE: Path = OUTPUT_DIR / "Working.xlsx"
WORKING_SHEET_NAME: str = "Working"
IGNORED_SHEET_NAME: str = "Ignored Rows"

# Part 2+3+4 çıktısı (migration sonucu)
WORKING_OUTPUT_FILE: Path = OUTPUT_DIR / "working_output.xlsx"
WORKING_OUTPUT_SHEET: str = "Result"
WORKING_OUTPUT_IGNORED_SHEET: str = "Ignored"

# Oluşturulan nesnelerin kaydı -> delete.py bunu okuyup temizler.
OBJECT_TRACKER_FILE: Path = DATA_DIR / "generated_objects.json"

# ===========================================================================
# 9) LOGLAMA
# ===========================================================================
CONSOLE_LOG_LEVEL: str = "INFO"   # Konsola basılacak en düşük seviye
FILE_LOG_LEVEL: str = "DEBUG"     # Dosyaya yazılacak en düşük seviye
USE_COLOR: bool = True            # Konsolda ANSI renk

# ===========================================================================
# 10) SABİT CREATE TEMPLATE'LERİ  (nadiren dokunulur)
# ===========================================================================
# Managed System — FunctionalAccountID/PasswordRuleID çalışma anında doldurulur.
LINUX_MANAGED_SYSTEM_TEMPLATE = {
    "EntityTypeID": 1,
    "HostName": "",
    "DnsName": "",
    "IPAddress": "",
    "SystemName": "",
    "PlatformID": PLATFORM_ID_LINUX,
    "FunctionalAccountID": None,   # çalışma anında ada göre doldurulur
    "PasswordRuleID": 0,           # çalışma anında policy adına göre doldurulur
    "Port": 22,
    "Timeout": 30,
    "ReleaseDuration": 120,
    "MaxReleaseDuration": 10079,
    "ISAReleaseDuration": 120,
    "AutoManagementFlag": False,
    "SshKeyEnforcementMode": 0,
    "CheckPasswordFlag": False,
    "ChangePasswordAfterAnyReleaseFlag": False,
    "ResetPasswordOnMismatchFlag": False,
    "ChangeFrequencyType": "first",
    "ChangeFrequencyDays": 30,
    "ChangeTime": "23:30",
    "AccountNameFormat": 2,
}

WINDOWS_MANAGED_SYSTEM_TEMPLATE = {
    "EntityTypeID": 1,
    "PlatformID": PLATFORM_ID_WINDOWS,
    "FunctionalAccountID": None,   # çalışma anında ada göre doldurulur
    "HostName": "",
    "DnsName": "",
    "IPAddress": "",
    "Port": 3389,
    "Timeout": 30,
    "SshKeyEnforcementMode": 0,
    "PasswordRuleID": 0,
    "ReleaseDuration": 120,
    "MaxReleaseDuration": 10079,
    "ISAReleaseDuration": 120,
    "AutoManagementFlag": False,
    "CheckPasswordFlag": False,
    "ChangePasswordAfterAnyReleaseFlag": False,
    "ResetPasswordOnMismatchFlag": False,
    "ChangeFrequencyType": "first",
    "ChangeFrequencyDays": 30,
    "ChangeTime": "23:30",
    "RemoteClientType": "None",
    "IsApplicationHost": False,
}

# Managed Account (AD) — AccountName/DomainName/Password çalışma anında doldurulur.
MANAGED_ACCOUNT_TEMPLATE = {
    "DomainName": "",
    "AccountName": "",
    "DistinguishedName": "None",
    "PasswordRuleID": 0,
    "Password": "",
    "WorkgroupID": None,           # çalışma anında WORKGROUP_NAME -> id ile doldurulur
    "ObjectID": "None",
    "UserPrincipalName": "",
    "SAMAccountName": "",
    "AutoManagementFlag": False,
    "MaxConcurrentRequests": 0,
}

# LOCAL Managed Account — row'un KENDİ managed system'i altında açılır, LİNKLENMEZ.
# Domain yok (DomainName="None"). AccountName/Password çalışma anında doldurulur.
LOCAL_MANAGED_ACCOUNT_TEMPLATE = {
    "AccountName": "",
    "Password": "",
    "DomainName": "None",
    "ObjectID": "None",
    "PasswordRuleID": 0,
    "WorkgroupID": None,           # çalışma anında WORKGROUP_NAME -> id ile doldurulur
    "AutoManagementFlag": False,
    "MaxConcurrentRequests": 0,
}
